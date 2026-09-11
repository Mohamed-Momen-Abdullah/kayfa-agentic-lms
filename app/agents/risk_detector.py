"""
Rule-based at-risk signal detection.

This intentionally does NOT use an LLM. Every signal here is a threshold
on numbers already returned by app.db.connector.get_student_report() —
attendance, grades, quiz score trend, progress. An LLM adds cost and
non-determinism without adding accuracy for "is 38% attendance low".

The LLM's job starts one layer up, in planner.py, where these signals
get turned into a personalized, prioritized intervention plan.
"""
from dataclasses import dataclass, asdict

# ---------------------------------------------------------------- #
# Thresholds — tune these against real cohort data once you have it.
# ---------------------------------------------------------------- #
LOW_ATTENDANCE = 60          # percent
CRITICAL_ATTENDANCE = 40     # percent
LOW_FINAL_GRADE = 5.0        # out of 10, matches grades collection scale
STALLED_PROGRESS = 25        # percent, with at least one quiz attempt already
QUIZ_TREND_WINDOW = 3        # compare the last attempt against N attempts ago


@dataclass
class RiskSignal:
    type: str          # "low_attendance" | "quiz_decline" | "stalled_progress" | "low_grade"
    course_id: str
    course_title: str
    severity: str       # "low" | "medium" | "high"
    detail: str

    def to_dict(self) -> dict:
        return asdict(self)


def _check_attendance(course: dict) -> RiskSignal | None:
    attendance = course.get("attendance_percent")
    if attendance is None or attendance >= LOW_ATTENDANCE:
        return None
    severity = "high" if attendance < CRITICAL_ATTENDANCE else "medium"
    return RiskSignal(
        type="low_attendance",
        course_id=course["id"],
        course_title=course["title"],
        severity=severity,
        detail=f"Attendance is {attendance}% in {course['title']}.",
    )


def _check_quiz_trend(course: dict) -> RiskSignal | None:
    attempts = course.get("quiz_attempts", [])
    scores = [a["score"] for a in attempts if a.get("score") is not None]
    if len(scores) < QUIZ_TREND_WINDOW:
        return None
    latest = scores[-1]
    earlier = scores[-QUIZ_TREND_WINDOW]
    if latest >= earlier:
        return None
    # Pull the most recent non-empty analysis text so the planner can
    # ground the remediation step in an actual weak concept instead of
    # just "scores are dropping".
    last_analysis = next(
        (a["analysis"] for a in reversed(attempts) if a.get("analysis")),
        "",
    )
    return RiskSignal(
        type="quiz_decline",
        course_id=course["id"],
        course_title=course["title"],
        severity="medium",
        detail=(
            f"Quiz scores trending down in {course['title']} "
            f"(last {QUIZ_TREND_WINDOW}: {scores[-QUIZ_TREND_WINDOW:]}). "
            f"Most recent weakness note: {last_analysis or 'none recorded'}."
        ),
    )


def _check_stalled_progress(course: dict) -> RiskSignal | None:
    progress = course.get("progress_percent", 0)
    has_activity = len(course.get("quiz_attempts", [])) > 0
    if progress >= STALLED_PROGRESS or not has_activity:
        return None
    return RiskSignal(
        type="stalled_progress",
        course_id=course["id"],
        course_title=course["title"],
        severity="medium",
        detail=(
            f"Progress stuck at {progress}% in {course['title']} despite "
            f"{len(course['quiz_attempts'])} quiz attempt(s) — engaged but not advancing."
        ),
    )


def _check_final_grade(course: dict) -> RiskSignal | None:
    grade = course.get("final_grade")
    if grade is None or grade >= LOW_FINAL_GRADE:
        return None
    return RiskSignal(
        type="low_grade",
        course_id=course["id"],
        course_title=course["title"],
        severity="high",
        detail=f"Final grade is {grade}/10 in {course['title']}.",
    )


_CHECKS = (_check_attendance, _check_quiz_trend, _check_stalled_progress, _check_final_grade)


def detect_risk_signals(report: dict) -> list[RiskSignal]:
    """
    report: the dict returned by app.db.connector.get_student_report().
    Returns one RiskSignal per (course, problem) pair found — a course
    with three problems produces three signals, on purpose, so the
    planner can see how concentrated the risk is.
    """
    if report.get("status") != "success":
        return []

    signals: list[RiskSignal] = []
    for course in report.get("courses", []):
        for check in _CHECKS:
            signal = check(course)
            if signal is not None:
                signals.append(signal)
    return signals
