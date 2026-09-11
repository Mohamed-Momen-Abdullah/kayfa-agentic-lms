"""
Intervention planner for at-risk students.

    get_student_report()
            |
            v
    detect_risk_signals()   <- risk_detector.py, rule-based, no LLM
            |
            v
    build_intervention_plan()   <- turns signals into an ordered list
            |                       of steps with dependencies
            v
    execute_intervention_plan() <- runs each step against the real
            |                       agents (academic_agent / quiz_agent)
            v
    save_intervention_plan() + save_instructor_alert()   <- persisted
"""
import logging
import traceback
from dataclasses import dataclass, field

from app.agents.risk_detector import RiskSignal, detect_risk_signals
from app.agents.academic_agent import answer_academic_question
from app.agents.quiz_agent import generate_quiz_from_topic
from app.db.connector import (
    get_student_report,
    get_course,
    get_user_full_name,
    save_intervention_plan,
    save_instructor_alert,
)

logger = logging.getLogger(__name__)


# =========================================================
# PLAN STRUCTURE
# =========================================================

@dataclass
class PlanStep:
    id: str
    agent: str              # "academic_agent" | "quiz_agent" | "notify_student" | "notify_instructor"
    course_id: str
    course_title: str
    input: str
    depends_on: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "agent": self.agent,
            "course_id": self.course_id,
            "course_title": self.course_title,
            "input": self.input,
            "depends_on": self.depends_on,
        }


# =========================================================
# 1. BUILD PLAN FROM SIGNALS
# =========================================================

def _steps_for_signal(signal: RiskSignal) -> list[PlanStep]:
    cid = signal.course_id

    if signal.type in ("quiz_decline", "low_grade"):
        explain_id = f"explain_{cid}"
        quiz_id = f"quiz_{cid}"
        return [
            PlanStep(
                id=explain_id,
                agent="academic_agent",
                course_id=cid,
                course_title=signal.course_title,
                input=(
                    f"The student is struggling in {signal.course_title}. "
                    f"Signal: {signal.detail} "
                    "Give a short, encouraging explanation of the concept(s) "
                    "they seem to be missing, with a simple example."
                ),
            ),
            PlanStep(
                id=quiz_id,
                agent="quiz_agent",
                course_id=cid,
                course_title=signal.course_title,
                input=signal.course_title,
                depends_on=[explain_id],
            ),
        ]

    if signal.type == "low_attendance":
        return [
            PlanStep(
                id=f"nudge_{cid}",
                agent="notify_student",
                course_id=cid,
                course_title=signal.course_title,
                input=signal.detail,
            )
        ]

    if signal.type == "stalled_progress":
        return [
            PlanStep(
                id=f"checkin_{cid}",
                agent="notify_instructor",
                course_id=cid,
                course_title=signal.course_title,
                input=signal.detail,
            )
        ]

    return []


async def build_intervention_plan(student_id: str) -> dict:
    """
    Runs the full detect -> plan pipeline for one student and persists
    the result. Returns a dict with status/signals/steps/summary —
    same shape whether or not signals were found, so callers don't
    need to branch on it.
    """
    report = get_student_report(student_id)
    if report.get("status") != "success":
        return {"status": "error", "signals": [], "steps": [], "summary": report.get("error", "Student report unavailable.")}

    signals = detect_risk_signals(report)
    if not signals:
        plan = {
            "status": "ok",
            "signals": [],
            "steps": [],
            "summary": "No risk signals detected — student is on track.",
        }
        save_intervention_plan(student_id, plan)
        return plan

    # High-severity signals crowd out noise: if any exist, plan only
    # around those first. Everything else waits for the next run.
    high = [s for s in signals if s.severity == "high"]
    priority_signals = high or signals

    steps: list[PlanStep] = []
    seen_course_high_grade_or_quiz = set()
    for signal in priority_signals:
        # Avoid stacking both an "explain" and a duplicate "explain" for
        # the same course if it triggered both low_grade and quiz_decline.
        if signal.type in ("quiz_decline", "low_grade"):
            if signal.course_id in seen_course_high_grade_or_quiz:
                continue
            seen_course_high_grade_or_quiz.add(signal.course_id)
        steps.extend(_steps_for_signal(signal))

    plan = {
        "status": "at_risk",
        "signals": [s.to_dict() for s in signals],
        "steps": [s.to_dict() for s in steps],
        "summary": f"{len(signals)} risk signal(s) across {len({s.course_id for s in signals})} course(s).",
    }
    save_intervention_plan(student_id, plan)
    return plan


# =========================================================
# 2. EXECUTE PLAN
# =========================================================

def _topological_order(steps: list[dict]) -> list[dict]:
    """Kahn's algorithm — steps come in small (<=6 typical), no need
    for anything fancier. Falls back to input order on a cycle, which
    shouldn't happen given how _steps_for_signal builds dependencies."""
    by_id = {s["id"]: s for s in steps}
    remaining = dict(by_id)
    ordered = []

    while remaining:
        ready = [
            s for s in remaining.values()
            if all(dep not in remaining for dep in s["depends_on"])
        ]
        if not ready:
            # cycle guard — just drain whatever's left in original order
            ordered.extend(remaining.values())
            break
        for s in ready:
            ordered.append(s)
            del remaining[s["id"]]

    return ordered


async def _run_step(step: dict, student_id: str, results: dict) -> dict:
    course = get_course(step["course_id"])
    course_context = (course or {}).get("material", "")

    if step["agent"] == "academic_agent":
        answer, usage = await answer_academic_question(
            step["input"], course_context=course_context
        )
        return {"status": "done", "output": answer, "usage": usage}

    if step["agent"] == "quiz_agent":
        # If this step depends on an explanation step, fold that answer
        # in as extra context so the quiz targets the same concept.
        prior = next(
            (results[dep]["output"] for dep in step["depends_on"] if dep in results),
            "",
        )
        topic = step["course_title"] if not prior else f"{step['course_title']} — focus: {prior[:200]}"
        questions, usage = await generate_quiz_from_topic(topic, n=3)
        return {"status": "done", "output": questions, "usage": usage}

    if step["agent"] == "notify_student":
        # No LLM call needed — this is a flagged nudge for the student's
        # dashboard/notification feed, kept as plain data.
        return {"status": "done", "output": step["input"], "usage": {}}

    if step["agent"] == "notify_instructor":
        instructor_id = (course or {}).get("instructor_id", "")
        save_instructor_alert(
            instructor_id=instructor_id,
            student_id=student_id,
            student_name=get_user_full_name(student_id),
            course_title=step["course_title"],
            message=step["input"],
            severity="medium",
        )
        return {"status": "done", "output": step["input"], "usage": {}}

    return {"status": "skipped", "output": None, "usage": {}}


async def execute_intervention_plan(student_id: str, plan: dict) -> dict:
    """
    Runs every step in plan["steps"] in dependency order and returns
    the same plan dict with a "results" key added: {step_id: {status,
    output, usage}}. Safe to call with an empty-steps plan (no-op).
    """
    steps = plan.get("steps", [])
    if not steps:
        return {**plan, "results": {}}

    ordered = _topological_order(steps)
    results: dict = {}

    for step in ordered:
        try:
            results[step["id"]] = await _run_step(step, student_id, results)
        except Exception:
            logger.error(
                "Intervention plan step %s failed:\n%s",
                step["id"],
                traceback.format_exc(),
            )
            results[step["id"]] = {"status": "error", "output": None, "usage": {}}

    return {**plan, "results": results}
