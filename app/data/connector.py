import os
from typing import Optional
from datetime import datetime, timezone
from pymongo import MongoClient
from bson import ObjectId
import certifi

MONGO_URI = os.getenv("MONGO_URI", "")
DB_NAME = os.getenv("DB_NAME", "edumind")
DATA_FOLDER_PATH = os.getenv("DATA_FOLDER_PATH", "app/data")

_client = MongoClient(MONGO_URI, tlsCAFile=certifi.where()) if MONGO_URI else None
db = _client[DB_NAME] if _client is not None else None

users_col = db["users"] if db is not None else None
courses_col = db["courses"] if db is not None else None
lessons_col = db["lessons"] if db is not None else None
enrollments_col = db["enrollments"] if db is not None else None
grades_col = db["grades"] if db is not None else None
chat_logs_col = db["chat_logs"] if db is not None else None


def _oid(value):
    try:
        return ObjectId(value)
    except Exception:
        return value


def find_user_by_username(username: str, role: str) -> Optional[dict]:
    if users_col is None:
        return None
    user = users_col.find_one({"username": username, "role": role.lower()})
    if user:
        user["_id"] = str(user["_id"])
    return user


def get_user_by_id(user_id: str) -> Optional[dict]:
    if users_col is None:
        return None
    user = users_col.find_one({"_id": _oid(user_id)})
    if user:
        user["_id"] = str(user["_id"])
    return user


def build_login_profile(user: dict) -> dict:
    role = user["role"]
    profile = {
        "id": user["_id"],
        "name": user.get("full_name"),
        "role": role.capitalize(),
        "department": user.get("department"),
    }

    if role == "student":
        grades = list(grades_col.find({"student_id": user["_id"]}))
        gpa = round(sum(g["final_grade"] for g in grades) / len(grades) / 10, 2) if grades else 0
        enrolled = user.get("enrolled_courses", [])
        profile["gpa"] = gpa
        profile["tot_cred"] = len(enrolled) * 3
        profile["enrolled_courses_count"] = len(enrolled)

    elif role == "instructor":
        taught = list(courses_col.find({"instructor_id": user["_id"]}))
        profile["courses_teaching"] = len(taught)

    return profile


def get_student_report(user_id: str) -> dict:
    user = get_user_by_id(user_id)
    if not user:
        return {}
    course_ids = user.get("enrolled_courses", [])
    courses = list(courses_col.find({"_id": {"$in": [_oid(c) for c in course_ids]}}))
    grades = list(grades_col.find({"student_id": user_id}))
    enrollments = list(enrollments_col.find({"student_id": user_id}))

    grade_by_course = {g["course_id"]: g for g in grades}
    enr_by_course = {e["course_id"]: e for e in enrollments}

    course_rows = []
    for c in courses:
        cid = str(c["_id"])
        enr = enr_by_course.get(cid, {})
        g = grade_by_course.get(cid, {})
        course_rows.append({
            "id": cid,
            "code": c["code"],
            "title": c["title"],
            "description": c.get("description", ""),
            "progress_percent": enr.get("progress_percent", 0),
            "final_grade": g.get("final_grade"),
            "attendance_percent": g.get("attendance_percent"),
        })

    avg_grade = round(sum(g["final_grade"] for g in grades) / len(grades), 1) if grades else 0
    avg_att = round(sum(g["attendance_percent"] for g in grades) / len(grades), 1) if grades else 0

    return {
        "full_name": user.get("full_name"),
        "department": user.get("department"),
        "enrolled_courses_count": len(courses),
        "average_grade": avg_grade,
        "average_attendance": avg_att,
        "courses": course_rows,
    }


def get_instructor_report(user_id: str) -> dict:
    user = get_user_by_id(user_id)
    if not user:
        return {}
    courses = list(courses_col.find({"instructor_id": user_id}))
    course_ids = [str(c["_id"]) for c in courses]
    all_grades = list(grades_col.find({"course_id": {"$in": course_ids}}))
    avg_grade = round(sum(g["final_grade"] for g in all_grades) / len(all_grades), 1) if all_grades else 0

    course_rows = []
    for c in courses:
        cid = str(c["_id"])
        enrolled = list(enrollments_col.find({"course_id": cid}))
        course_grades = [g for g in all_grades if g["course_id"] == cid]
        course_avg = round(sum(g["final_grade"] for g in course_grades) / len(course_grades), 1) if course_grades else 0

        student_ids = [e["student_id"] for e in enrolled]
        students = {
            str(u["_id"]): u["full_name"]
            for u in users_col.find({"_id": {"$in": [_oid(s) for s in student_ids]}})
        }
        grade_map = {g["student_id"]: g["final_grade"] for g in course_grades}
        roster = sorted(
            [{"name": students.get(sid, "Unknown"), "final_grade": grade_map.get(sid)} for sid in student_ids],
            key=lambda r: (r["final_grade"] is None, r["final_grade"] or 0),
        )

        course_rows.append({
            "id": cid,
            "code": c["code"],
            "title": c["title"],
            "enrolled_count": len(enrolled),
            "average_grade": course_avg,
            "roster": roster,
        })

    return {
        "full_name": user.get("full_name"),
        "department": user.get("department"),
        "courses_teaching": len(courses),
        "total_students": enrollments_col.count_documents({"course_id": {"$in": course_ids}}),
        "average_class_grade": avg_grade,
        "courses": course_rows,
    }


def get_personal_records(user_role: str, user_id: Optional[str], max_items: int = 20) -> str:
    if not user_id:
        return ""
    role = user_role.lower()
    try:
        if role == "student":
            report = get_student_report(user_id)
            if not report:
                return ""
            lines = [f"STUDENT PROFILE: {report['full_name']} - {report['department']}"]
            lines.append(f"Average grade: {report['average_grade']}/100, Average attendance: {report['average_attendance']}%")
            for c in report["courses"][:max_items]:
                lines.append(f"- {c['code']} {c['title']}: progress {c['progress_percent']}%, grade {c['final_grade']}")
            return "\n".join(lines)

        if role == "instructor":
            report = get_instructor_report(user_id)
            if not report:
                return ""
            lines = [f"INSTRUCTOR PROFILE: {report['full_name']} - {report['department']}"]
            lines.append(f"Teaching {report['courses_teaching']} courses, {report['total_students']} students total.")
            for c in report["courses"][:max_items]:
                lines.append(f"- {c['code']} {c['title']}: {c['enrolled_count']} students, avg grade {c['average_grade']}")
            return "\n".join(lines)
        return ""
    except Exception as e:
        print(f"Personal-record retrieval error: {e}")
        return ""


def save_lesson_content_for_course(course_id: str, limit: int = 4) -> str:
    lessons = list(lessons_col.find({"course_id": course_id}).limit(limit))
    return "\n".join(l["content"][:300] for l in lessons)


def add_quiz_grade(student_id: str, course_id: str, score_out_of_10: float):
    entry = {
        "name": f"Practice Quiz {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}",
        "score": score_out_of_10,
        "max_score": 10,
    }
    existing = grades_col.find_one({"student_id": student_id, "course_id": course_id})
    if existing:
        assignments = existing["assignments"] + [entry]
        final_grade = round(sum(a["score"] for a in assignments) / len(assignments) * 10, 1)
        grades_col.update_one({"_id": existing["_id"]}, {"$set": {"assignments": assignments, "final_grade": final_grade}})
    else:
        final_grade = round(score_out_of_10 * 10, 1)
        grades_col.insert_one({
            "student_id": student_id, "course_id": course_id,
            "assignments": [entry], "attendance_percent": 100, "final_grade": final_grade,
        })
