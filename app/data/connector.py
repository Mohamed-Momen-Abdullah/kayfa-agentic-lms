import os
import sqlite3
import pandas as pd
from typing import List, Optional
import certifi
import uuid
from datetime import datetime
from pymongo import MongoClient

DB_PATH = os.getenv("DB_PATH", "app/data/university.db")
DATA_FOLDER_PATH = os.getenv("DATA_FOLDER_PATH", os.path.dirname(DB_PATH) or "app/data")
MONGO_URI = os.getenv("MONGO_URI", "")

def load_users(db_path: str) -> dict:
    users = {}
    if not os.path.exists(db_path):
        print(f"⚠️ University DB not found at: {db_path}")
        return users
    
    conn = sqlite3.connect(db_path)
    try:
        df_students = pd.read_sql("SELECT ID AS student_id, name AS full_name, dept_name, tot_cred FROM student", conn)
        for _, row in df_students.iterrows():
            if pd.isna(row["student_id"]): continue
            sid = str(row["student_id"]).strip()
            users[f"Student:{sid}"] = {
                "role": "Student",
                "name": str(row["full_name"]) if pd.notna(row["full_name"]) else f"Student {sid}",
                "student_id": sid,
                "dept_name": str(row["dept_name"]) if pd.notna(row["dept_name"]) else None,
                "tot_cred": float(row["tot_cred"]) if pd.notna(row["tot_cred"]) else None,
            }

        df_instructors = pd.read_sql("SELECT ID AS instructor_id, name AS full_name, dept_name FROM instructor", conn)
        for _, row in df_instructors.iterrows():
            if pd.isna(row["instructor_id"]): continue
            iid = str(row["instructor_id"]).strip()
            users[f"Instructor:{iid}"] = {
                "role": "Instructor",
                "name": str(row["full_name"]) if pd.notna(row["full_name"]) else f"Instructor {iid}",
                "instructor_id": iid,
                "dept_name": str(row["dept_name"]) if pd.notna(row["dept_name"]) else None,
            }
    finally:
        conn.close()
    return users

USER_INDEX = load_users(DB_PATH)

def find_user_matches(user_id: str) -> List[dict]:
    suffix = f":{user_id}"
    return [info for key, info in USER_INDEX.items() if key.endswith(suffix)]

def get_personal_records(user_role: str, user_id: Optional[str], max_items: int = 100) -> str:
    if not user_id or not os.path.exists(DB_PATH):
        return ""
    conn = sqlite3.connect(DB_PATH)
    try:
        if user_role == "Student":
            student = pd.read_sql("SELECT ID, name, dept_name, tot_cred FROM student WHERE ID = ?", conn, params=[str(user_id)])
            enrollments = pd.read_sql("""SELECT t.ID AS student_id, t.course_id, c.title AS course_title, c.dept_name AS course_department, c.credits, t.sec_id AS section_id, t.semester, t.year, t.grade, s.building, s.room_number, s.time_slot_id FROM takes t LEFT JOIN course c ON c.course_id = t.course_id LEFT JOIN section s ON s.course_id = t.course_id AND s.sec_id = t.sec_id AND s.semester = t.semester AND s.year = t.year WHERE t.ID = ? ORDER BY t.year DESC, t.semester, t.course_id LIMIT ?""", conn, params=[str(user_id), max_items])
            advisor = pd.read_sql("SELECT a.s_ID AS student_id, a.i_ID AS instructor_id, i.name AS instructor_name FROM advisor a LEFT JOIN instructor i ON i.ID = a.i_ID WHERE a.s_ID = ?", conn, params=[str(user_id)])
            chunks = []
            if not student.empty: chunks.append("STUDENT PROFILE:\n" + student.to_string(index=False))
            if not enrollments.empty: chunks.append("STUDENT ENROLLMENTS / GRADES / SECTIONS:\n" + enrollments.to_string(index=False))
            if not advisor.empty: chunks.append("STUDENT ADVISOR:\n" + advisor.to_string(index=False))
            return "\n\n".join(chunks)

        if user_role == "Instructor":
            instructor = pd.read_sql("SELECT ID, name, dept_name, salary FROM instructor WHERE ID = ?", conn, params=[str(user_id)])
            teaching = pd.read_sql("""SELECT t.ID AS instructor_id, t.course_id, c.title AS course_title, c.dept_name AS course_department, c.credits, t.sec_id AS section_id, t.semester, t.year, s.building, s.room_number, s.time_slot_id FROM teaches t LEFT JOIN course c ON c.course_id = t.course_id LEFT JOIN section s ON s.course_id = t.course_id AND s.sec_id = t.sec_id AND s.semester = t.semester AND s.year = t.year WHERE t.ID = ? ORDER BY t.year DESC, t.semester, t.course_id LIMIT ?""", conn, params=[str(user_id), max_items])
            chunks = []
            if not instructor.empty: chunks.append("INSTRUCTOR PROFILE:\n" + instructor.to_string(index=False))
            if not teaching.empty: chunks.append("TEACHING ASSIGNMENTS / SECTIONS:\n" + teaching.to_string(index=False))
            return "\n\n".join(chunks)
        return ""
    except Exception as e:
        print(f"⚠️ Personal-record retrieval error: {e}")
        return ""
    finally:
        conn.close()

def save_crm_ticket(customer_name, phone, current_level, email="لم يذكر بعد", city="غير محدد", products_of_interest="منصة كيف التعليمية", goal="تطوير المهارات التقنية", conversation_summary="استفسار أولي", intent_status="hot"):
    if not MONGO_URI: return False, "MONGO_URI missing"
    try:
        client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
        db = client["kayfa_crm"]
        ticket = {
            "ticket_id": f"LEAD-{datetime.now().year}-{uuid.uuid4().hex[:4].upper()}",
            "customer_info": {"name": customer_name, "phone": phone, "email": email, "city_country": city},
            "educational_profile": {"current_level": current_level, "products_of_interest": products_of_interest, "goal_motivation": goal},
            "sales_signals": {"lead_temperature": intent_status, "buying_signals": "استفسر عن طرق الدفع والتسجيل وأدخل بياناته الأساسية", "objections_handled": "تم توضيح الخيارات المبدئية وحفظ الليد بنجاح"},
            "conversation_metadata": {"summary_ar": conversation_summary, "next_action": "يتواصل أحد مندوبي المبيعات عبر واتساب", "timestamp": datetime.now()},
        }
        db["crm_tickets"].insert_one(ticket)
        return True, ticket["ticket_id"]
    except Exception as e:
        return False, str(e)
