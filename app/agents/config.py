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
    "Admin": {
        "allowed_agents": ["Course_Agent", "Policy_Agent"],
        "welcome_msg": "أهلاً أدمن، إزاي أقدر أساعدك؟",
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
DATA STRUCTURE (MongoDB - database: edumind):
- users(_id, full_name, email, username, password_hash, role[student|instructor], department, enrolled_courses[], teaching_courses[])
- courses(_id, code, title, description, category, level, instructor_id)
- lessons(_id, course_id, title, order, content)
- enrollments(student_id, course_id, progress_percent, status)
- grades(student_id, course_id, assignments[], attendance_percent, final_grade)
"""