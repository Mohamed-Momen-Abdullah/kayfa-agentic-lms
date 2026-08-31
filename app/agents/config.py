import os
from dotenv import load_dotenv

load_dotenv()

# Groq Models & Hyperparameters
GROQ_API_KEY = os.getenv("Groq_api_key")
GROQ_MODEL = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")

ROUTER_TEMPERATURE = float(os.getenv("ROUTER_TEMPERATURE", "0.1"))
AGENT_TEMPERATURE = float(os.getenv("AGENT_TEMPERATURE", "0.2"))
FINAL_TEMPERATURE = float(os.getenv("FINAL_TEMPERATURE", "0.3"))

PRICE_PER_INPUT_TOKEN = 0.00000059
PRICE_PER_OUTPUT_TOKEN = 0.00000079

ROLE_PERMISSIONS = {
    "Student": {
        "allowed_agents": [
            "Course_Agent", "Academic_Agent", "Schedule_Agent",
            "Policy_Agent", "Attendance_Agent"
        ],
        "welcome_msg": "أهلاً بك في منصة كيف! 👋 كيف يمكنني مساعدتك اليوم في دراستك؟",
    },
    "Instructor": {
        "allowed_agents": [
            "Instructor_Agent", "Course_Agent", "Academic_Agent",
            "Schedule_Agent", "Policy_Agent"
        ],
        "welcome_msg": "مرحباً يا دكتور! 👨‍🏫 كيف يمكنني دعم مقرراتك وجدولك الأكاديمي اليوم؟",
    },
}

AGENT_DESCRIPTIONS = {
    "Academic_Agent": "Handles grades, GPA calculation, transcript auditing, and academic performance.",
    "Course_Agent": "Provides course descriptions, prerequisites, syllabi, and departmental offerings.",
    "Schedule_Agent": "Accesses class timetables, lecture halls, time slots, and academic calendars.",
    "Policy_Agent": "Answers institutional rules, graduation conditions, and university policies.",
    "Instructor_Agent": "Manages faculty teaching loads, assigned sections, and instructor profiles.",
    "Attendance_Agent": "Inquires about lecture attendance rules and absence policies.",
}

DATABASE_CONTEXT = """
DATA STRUCTURE (university.db):
- student(ID, name, dept_name, tot_cred)
- instructor(ID, name, dept_name, salary)
- department(dept_name, building, budget)
- course(course_id, title, dept_name, credits)
- classroom(building, room_number, capacity)
- section(course_id, sec_id, semester, year, building, room_number, time_slot_id)
- takes(ID, course_id, sec_id, semester, year, grade)
- teaches(ID, course_id, sec_id, semester, year)
- advisor(s_ID, i_ID)
- prereq(course_id, prereq_id)
- time_slot(time_slot_id, day, start_hr, start_min, end_hr, end_min)
"""