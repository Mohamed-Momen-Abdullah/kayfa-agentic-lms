"""
MongoDB data access layer.

This now points at the SAME MongoDB database used in our earlier
kayfa-lms-v2 project (users/courses/lessons/enrollments/grades), so the
data you already seeded there is what this UI reads and writes.

Collections (existing, from kayfa-lms-v2)
------------------------------------------
users         { _id: ObjectId, full_name, email, username, password_hash,
                role: "student"|"instructor", department,
                enrolled_courses: [course_id str], teaching_courses: [course_id str] }
courses       { _id: ObjectId, code, title, description, category, level, instructor_id: str }
lessons       { _id: ObjectId, course_id: str, title, order, content }
enrollments   { student_id: str, course_id: str, progress_percent, status }
grades        { student_id: str, course_id: str, assignments: [...],
                attendance_percent, final_grade }

Collections (new, added by this app — safe to add to the same database)
-------------------------------------------------------------------------
quiz_grades   { student_id: str, course_id: str, score, correct, total, analysis, created_at }
chat_traces   { user_id, user_role, full_name, query, response, agent, sentiment,
                prompt_tokens, completion_tokens, latency_ms, cost_usd, created_at }
intervention_plans { student_id: str, signals: [...], steps: [...], summary, status, created_at }
instructor_alerts  { instructor_id: str, student_id: str, student_name, course_title,
                      message, severity, resolved: bool, created_at }
"""
import logging
from datetime import datetime, timezone

from app.core.config import settings

logger = logging.getLogger(__name__)

_client = None
_db = None


def get_db():
    global _client, _db
    if _db is not None:
        return _db
    try:
        from pymongo import MongoClient
        import certifi
        _client = MongoClient(settings.MONGO_URI, tlsCAFile=certifi.where(), serverSelectionTimeoutMS=5000)
        _client.admin.command("ping")
        _db = _client[settings.DATABASE_NAME]
        return _db
    except Exception as e:
        logger.warning(f"MongoDB connection failed ({e}). Running without a database.")
        return None


def _now():
    return datetime.now(timezone.utc)


def _oid(value):
    from bson import ObjectId
    try:
        return ObjectId(value)
    except Exception:
        return value


# ------------------------------------------------------------------ #
# Users / auth
# ------------------------------------------------------------------ #
def find_user_by_username(username: str, role: str = None):
    db = get_db()
    if db is None:
        return None
    query = {"username": username}
    if role:
        query["role"] = role.lower()
    user = db.users.find_one(query)
    if user:
        user["_id"] = str(user["_id"])
    return user


def get_user_by_id(user_id: str):
    db = get_db()
    if db is None:
        return None
    user = db.users.find_one({"_id": _oid(user_id)})
    if user:
        user["_id"] = str(user["_id"])
    return user


def get_user_full_name(user_id: str) -> str:
    if user_id == "admin":
        return "System Administrator"
    user = get_user_by_id(user_id)
    return user.get("full_name", user_id) if user else user_id


def build_login_profile(user: dict) -> dict:
    return {
        "id": user["_id"],
        "name": user.get("full_name", user.get("username", user["_id"])),
        "role": user.get("role", "student").capitalize(),
        "department": user.get("department", ""),
    }


# ------------------------------------------------------------------ #
# Courses
# ------------------------------------------------------------------ #
def get_course(course_id: str):
    """Fetches a course and attaches the material text used for grounded
    quiz generation.

    Material is built by retrieving the most relevant chunks from the
    course's `lessons` (see services/retrieval.py) instead of naively
    joining the first few lessons — this keeps the prompt small and
    on-topic regardless of how many lessons the course actually has.
    Falls back to a `material` field stored directly on the course
    document (used by demo/seed data) if no lessons exist.
    """
    db = get_db()
    if db is None:
        return None
    course = db.courses.find_one({"_id": _oid(course_id)})
    if not course:
        return None
    course["_id"] = str(course["_id"])

    lessons = list(db.lessons.find({"course_id": course["_id"]}).limit(50))
    if lessons:
        from app.services.retrieval import retrieve_course_material
        query = f"{course.get('title', '')} {course.get('description', '')}"
        course["material"] = retrieve_course_material(lessons, query)
    else:
        course["material"] = course.get("material", "")

    return course


def get_courses_for_student(student_id: str):
    db = get_db()
    if db is None:
        return []
    user = db.users.find_one({"_id": _oid(student_id)})
    if not user:
        return []
    course_ids = user.get("enrolled_courses", [])
    courses = list(db.courses.find({"_id": {"$in": [_oid(c) for c in course_ids]}}))
    for c in courses:
        c["_id"] = str(c["_id"])
    return courses


# ------------------------------------------------------------------ #
# Student report
# ------------------------------------------------------------------ #
def get_student_report(student_id: str) -> dict:
    db = get_db()
    if db is None:
        return {"status": "error", "error": "Database unavailable."}

    user = db.users.find_one({"_id": _oid(student_id)})
    if not user:
        return {"status": "error", "error": "Student not found."}

    course_ids = user.get("enrolled_courses", [])
    courses_by_id = {str(c["_id"]): c for c in db.courses.find({"_id": {"$in": [_oid(c) for c in course_ids]}})}
    enrollments = list(db.enrollments.find({"student_id": student_id}))
    grades = list(db.grades.find({"student_id": student_id}))
    grade_by_course = {g["course_id"]: g for g in grades}
    enr_by_course = {e["course_id"]: e for e in enrollments}

    courses = []
    all_final_grades = []
    all_attendance = []
    for cid, c in courses_by_id.items():
        enr = enr_by_course.get(cid, {})
        g = grade_by_course.get(cid, {})
        final_grade = g.get("final_grade")
        if final_grade is not None:
            all_final_grades.append(final_grade)
        if g.get("attendance_percent") is not None:
            all_attendance.append(g["attendance_percent"])

        attempts = list(db.quiz_grades.find({"student_id": student_id, "course_id": cid}).sort("created_at", 1))
        quiz_attempts = [{
            "created_at": a["created_at"].isoformat() if a.get("created_at") else None,
            "score": a.get("score"),
            "correct": a.get("correct"),
            "total": a.get("total"),
            "analysis": a.get("analysis", ""),
            "improvement_plan": a.get("improvement_plan", {}),
        } for a in attempts]

        courses.append({
            "id": cid,
            "code": c.get("code", ""),
            "title": c.get("title", ""),
            "description": c.get("description", ""),
            "instructor_id": c.get("instructor_id", ""),
            "progress_percent": enr.get("progress_percent", 0),
            "final_grade": final_grade,
            "attendance_percent": g.get("attendance_percent"),
            "quiz_attempts": quiz_attempts,
        })

    quiz_grades = list(db.quiz_grades.find({"student_id": student_id}))
    quiz_scores = [q["score"] for q in quiz_grades if "score" in q]

    return {
        "status": "success",
        "full_name": user.get("full_name", ""),
        "department": user.get("department", ""),
        "enrolled_courses_count": len(courses),
        "average_grade": round(sum(all_final_grades) / len(all_final_grades), 1) if all_final_grades else 0,
        "average_attendance": round(sum(all_attendance) / len(all_attendance), 1) if all_attendance else 0,
        "quizzes_taken": len(quiz_scores),
        "average_quiz_score": round(sum(quiz_scores) / len(quiz_scores), 1) if quiz_scores else 0,
        "courses": courses,
    }


# ------------------------------------------------------------------ #
# Instructor report
# ------------------------------------------------------------------ #
def _last_quiz_attempt(db, student_id: str, course_id: str):
    """Most recent quiz attempt for this student in this course, or None."""
    return db.quiz_grades.find_one(
        {"student_id": student_id, "course_id": course_id},
        sort=[("created_at", -1)],
    )


def _build_student_note(fg, course_grades: list, last_quiz) -> str:
    """Plain-language note on how this student is doing relative to their
    classmates' grades in this course, plus their most recent quiz score.
    course_grades is the list of every *other* graded student's final_grade
    in the same course (self excluded)."""
    parts = []

    if fg is None:
        parts.append("No final grade recorded yet.")
    elif not course_grades:
        parts.append("Only graded student in this course so far.")
    else:
        avg = sum(course_grades) / len(course_grades)
        diff = fg - avg
        if diff >= 0.5:
            parts.append(f"Above the class average ({avg:.1f}/10) by {diff:.1f} points.")
        elif diff <= -0.5:
            parts.append(f"Below the class average ({avg:.1f}/10) by {abs(diff):.1f} points.")
        else:
            parts.append(f"Right around the class average ({avg:.1f}/10).")

    if last_quiz is not None:
        parts.append(f"Last quiz score: {last_quiz.get('score')}/10.")
    else:
        parts.append("No quizzes taken yet.")

    return " ".join(parts)


def get_instructor_report(instructor_id: str) -> dict:
    db = get_db()
    if db is None:
        return {"status": "error", "error": "Database unavailable."}

    user = db.users.find_one({"_id": _oid(instructor_id)})
    if not user:
        return {"status": "error", "error": "Instructor not found."}

    courses = list(db.courses.find({"instructor_id": instructor_id}))
    course_list = []
    all_grades = []
    total_students = 0

    for c in courses:
        cid = str(c["_id"])
        enrollments = list(db.enrollments.find({"course_id": cid}))
        student_ids = [e["student_id"] for e in enrollments]
        students_by_id = {str(s["_id"]): s for s in db.users.find({"_id": {"$in": [_oid(s) for s in student_ids]}})}
        grades_by_student = {g["student_id"]: g for g in db.grades.find({"course_id": cid})}

        roster = []
        course_grades = []
        for sid in student_ids:
            s = students_by_id.get(sid)
            if not s:
                continue
            fg = grades_by_student.get(sid, {}).get("final_grade")
            if fg is not None:
                course_grades.append(fg)
                all_grades.append(fg)
            roster.append({
                "student_id": sid,
                "name": s.get("full_name", ""),
                "final_grade": fg,
            })

        # Report column: each student compared against everyone *else*
        # graded in the course, plus their most recent quiz attempt.
        for r in roster:
            if r["final_grade"] is not None:
                peers = [g for g in course_grades]
                peers.remove(r["final_grade"])
            else:
                peers = course_grades
            last_quiz = _last_quiz_attempt(db, r["student_id"], cid)
            r["report"] = _build_student_note(r["final_grade"], peers, last_quiz)
            del r["student_id"]

        # Highest grade first; students without a final grade sink to the bottom.
        roster.sort(key=lambda r: (r["final_grade"] is None, -(r["final_grade"] or 0)))

        total_students += len(roster)
        course_list.append({
            "id": cid,
            "code": c.get("code", ""),
            "title": c.get("title", ""),
            "enrolled_count": len(roster),
            "average_grade": round(sum(course_grades) / len(course_grades), 1) if course_grades else 0,
            "roster": roster,
        })

    return {
        "status": "success",
        "full_name": user.get("full_name", ""),
        "department": user.get("department", ""),
        "courses_teaching": len(course_list),
        "total_students": total_students,
        "average_class_grade": round(sum(all_grades) / len(all_grades), 1) if all_grades else 0,
        "courses": course_list,
    }


def get_personal_records(role: str, user_id: str, max_items: int = 20) -> str:
    """Builds a compact, factual summary of the signed-in user's own academic
    data (grades, courses, roster counts) to inject into the agent's prompt,
    so it can answer questions like 'how many students do I have' or
    'what's my grade in X' directly instead of deflecting."""
    role = role.lower()
    try:
        if role == "student":
            report = get_student_report(user_id)
            if report.get("status") != "success":
                return ""
            lines = [f"STUDENT PROFILE: {report['full_name']} - {report['department']}"]
            lines.append(f"Average grade: {report['average_grade']}/10, Average attendance: {report['average_attendance']}%")
            for c in report["courses"][:max_items]:
                lines.append(f"- {c['code']} {c['title']}: progress {c['progress_percent']}%, grade {c['final_grade']}")
            return "\n".join(lines)

        if role == "instructor":
            report = get_instructor_report(user_id)
            if report.get("status") != "success":
                return ""
            lines = [f"INSTRUCTOR PROFILE: {report['full_name']} - {report['department']}"]
            lines.append(f"Teaching {report['courses_teaching']} courses, {report['total_students']} students total.")
            for c in report["courses"][:max_items]:
                lines.append(f"- {c['code']} {c['title']}: {c['enrolled_count']} students, avg grade {c['average_grade']}")
                # Roster is already sorted highest grade first, so the agent
                # can answer "who's my top/bottom student" directly.
                for r in c["roster"]:
                    grade_txt = f"{r['final_grade']}/10" if r["final_grade"] is not None else "no grade yet"
                    lines.append(f"    * {r['name']}: {grade_txt} — {r['report']}")
            return "\n".join(lines)
        return ""
    except Exception as e:
        logger.warning(f"Personal-record retrieval error: {e}")
        return ""


# ------------------------------------------------------------------ #
# Quizzes
# ------------------------------------------------------------------ #
def add_quiz_grade(
    student_id: str,
    course_id: str,
    score: float,
    correct: int,
    total: int,
    analysis: str = "",
    improvement_plan: dict | None = None,
):
    db = get_db()
    if db is None:
        return
    db.quiz_grades.insert_one({
        "student_id": student_id,
        "course_id": course_id,
        "score": score,
        "correct": correct,
        "total": total,
        "analysis": analysis,
        "improvement_plan": improvement_plan or {},
        "created_at": _now(),
    })


def get_system_counts() -> dict:
    db = get_db()
    if db is None:
        return {"students": 0, "instructors": 0, "courses": 0}
    return {
        "students": db.users.count_documents({"role": "student"}),
        "instructors": db.users.count_documents({"role": "instructor"}),
        "courses": db.courses.count_documents({}),
    }


# ------------------------------------------------------------------ #
# Chat traces (admin observability)
# ------------------------------------------------------------------ #
def insert_chat_trace(doc: dict):
    db = get_db()
    if db is None:
        return
    doc = dict(doc)
    doc["created_at"] = _now()
    db.chat_traces.insert_one(doc)


def get_chat_history(user_id: str, limit: int = 200) -> list[dict]:
    """Rebuilds this user's own conversation with the chat agents, oldest
    first, so it can be restored when they log back in. Only real chat
    turns are replayed — quiz bookkeeping events (kind="quiz_event") are
    logged for observability but were never a bubble in the chat window,
    so they're skipped. Older traces recorded before this field existed
    have no `kind` at all; they're treated as chat too rather than
    silently dropped."""
    db = get_db()
    if db is None:
        return []

    traces = list(
        db.chat_traces.find({"user_id": user_id})
        .sort("created_at", 1)
        .limit(limit)
    )

    messages = []
    for t in traces:
        if t.get("kind") == "quiz_event":
            continue
        messages.append({
            "role": "user",
            "content": t.get("query", ""),
            "sentiment": t.get("sentiment"),
        })
        messages.append({
            "role": "assistant",
            "content": t.get("response", ""),
            "agent": t.get("agent", "academic_agent"),
        })
    return messages


def save_intervention_plan(student_id: str, plan: dict):
    """Persists the outcome of a risk-detector + planner run so the
    student's dashboard and the instructor alert feed both have a
    record of it, not just the in-memory response returned to the
    caller."""
    db = get_db()
    if db is None:
        return
    db.intervention_plans.insert_one({
        "student_id": student_id,
        "signals": plan.get("signals", []),
        "steps": plan.get("steps", []),
        "summary": plan.get("summary", ""),
        "status": plan.get("status", "ok"),
        "created_at": _now(),
    })


def get_latest_intervention_plan(student_id: str) -> dict | None:
    db = get_db()
    if db is None:
        return None
    doc = db.intervention_plans.find_one(
        {"student_id": student_id},
        sort=[("created_at", -1)],
    )
    if not doc:
        return None
    doc["id"] = str(doc.pop("_id"))
    if doc.get("created_at"):
        doc["created_at"] = doc["created_at"].isoformat()
    return doc


def save_instructor_alert(
    instructor_id: str,
    student_id: str,
    student_name: str,
    course_title: str,
    message: str,
    severity: str,
):
    db = get_db()
    if db is None or not instructor_id:
        return
    db.instructor_alerts.insert_one({
        "instructor_id": instructor_id,
        "student_id": student_id,
        "student_name": student_name,
        "course_title": course_title,
        "message": message,
        "severity": severity,
        "resolved": False,
        "created_at": _now(),
    })


def get_instructor_alerts(instructor_id: str, limit: int = 50) -> list[dict]:
    """Unresolved at-risk alerts raised by the planner for this
    instructor's students, most recent first."""
    db = get_db()
    if db is None:
        return []
    alerts = list(
        db.instructor_alerts.find({"instructor_id": instructor_id, "resolved": False})
        .sort("created_at", -1)
        .limit(limit)
    )
    for a in alerts:
        a["id"] = str(a.pop("_id"))
        if a.get("created_at"):
            a["created_at"] = a["created_at"].isoformat()
    return alerts


def get_admin_overview(limit: int = 200) -> dict:
    db = get_db()
    if db is None:
        return {"status": "error", "error": "Database unavailable.", "traces": [], "kpi": {}}

    traces = list(db.chat_traces.find().sort("created_at", -1).limit(limit))
    for t in traces:
        t["id"] = str(t.pop("_id"))
        if t.get("created_at"):
            t["timestamp"] = t["created_at"].isoformat()
            del t["created_at"]

    unique_users = sorted({t.get("user_id") for t in traces if t.get("user_id")})
    total_tokens = sum((t.get("prompt_tokens", 0) or 0) + (t.get("completion_tokens", 0) or 0) for t in traces)
    total_cost = sum(t.get("cost_usd", 0) or 0 for t in traces)
    latencies = [t["latency_ms"] for t in traces if t.get("latency_ms") is not None]
    avg_response_time_ms = round(sum(latencies) / len(latencies), 1) if latencies else 0

    tokens_by_day = {}
    tokens_by_user = {}
    tokens_by_role = {}
    for t in traces:
        day = (t.get("timestamp") or "")[:10] or "unknown"
        tokens = (t.get("prompt_tokens", 0) or 0) + (t.get("completion_tokens", 0) or 0)
        tokens_by_day[day] = tokens_by_day.get(day, 0) + tokens

        role_key = t.get("user_role") or "Unknown"
        tokens_by_role[role_key] = tokens_by_role.get(role_key, 0) + tokens

        key = (t.get("full_name") or t.get("user_id") or "Unknown", t.get("user_role") or "Unknown")
        entry = tokens_by_user.setdefault(key, {"conversations": 0, "total_tokens": 0, "latencies": []})
        entry["conversations"] += 1
        entry["total_tokens"] += tokens
        if t.get("latency_ms") is not None:
            entry["latencies"].append(t["latency_ms"])

    usage_over_time = [{"date": d, "tokens": tk} for d, tk in sorted(tokens_by_day.items()) if d != "unknown"]
    usage_by_role = [{"role": r, "tokens": tk} for r, tk in tokens_by_role.items()]
    usage_by_user = [
        {
            "full_name": name, "role": role,
            "conversations": v["conversations"], "total_tokens": v["total_tokens"],
            "avg_latency_ms": round(sum(v["latencies"]) / len(v["latencies"]), 1) if v["latencies"] else 0,
        }
        for (name, role), v in tokens_by_user.items()
    ]
    usage_by_user.sort(key=lambda r: r["conversations"], reverse=True)

    system = get_system_counts()
    system["model"] = settings.GROQ_MODEL

    return {
        "status": "success",
        "traces": traces,
        "kpi": {
            "calls_count": len(traces),
            "total_tokens": total_tokens,
            "total_cost": total_cost,
            "avg_response_time_ms": avg_response_time_ms,
            "unique_users": unique_users,
        },
        "usage_over_time": usage_over_time,
        "usage_by_role": usage_by_role,
        "usage_by_user": usage_by_user,
        "system": system,
    }