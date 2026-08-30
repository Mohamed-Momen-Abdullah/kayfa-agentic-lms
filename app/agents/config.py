import os
from dotenv import load_dotenv

load_dotenv()

# Models & Generation Settings
GROQ_API_KEY = os.getenv("Groq_api_key")
GROQ_MODEL = os.getenv("GROQ_MODEL", "qwen/qwen3.6-27b")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")

ROUTER_TEMPERATURE = float(os.getenv("ROUTER_TEMPERATURE", "0.1"))
AGENT_TEMPERATURE = float(os.getenv("AGENT_TEMPERATURE", "0.2"))
FINAL_TEMPERATURE = float(os.getenv("FINAL_TEMPERATURE", "0.4"))
WEB_SEARCH_TEMPERATURE = float(os.getenv("WEB_SEARCH_TEMPERATURE", "0.3"))
WEB_SEARCH_MODEL = os.getenv("WEB_SEARCH_MODEL", "openai/gpt-oss-20b")
WEB_SEARCH_MAX_RESULTS = int(os.getenv("WEB_SEARCH_MAX_RESULTS", "5"))

# Agent RBAC Configurations
ROLE_PERMISSIONS = {
    "Student": {
        "allowed_agents": [
            "Course_Agent", "Attendance_Agent", "Schedule_Agent",
            "Analytics_Agent", "Recommendation_Agent", "Assessment_Agent",
        ],
        "welcome_msg": "🎓 Welcome to CampusX AI!\n\n",
    },
    "Instructor": {
        "allowed_agents": [
            "Instructor_Agent", "Course_Agent", "Attendance_Agent",
            "Analytics_Agent", "Assessment_Agent", "Policy_Agent",
        ],
        "welcome_msg": "👨‍🏫 Welcome to UAX AI!\n\n",
    },
}

AGENT_DESCRIPTIONS = {
    "Instructor_Agent": "Manage instructor information, teaching assignments, and faculty-related services.",
    "Course_Agent": "Retrieve course information, curriculum, materials, and academic content.",
    "Graduation_Agent": "Check graduation requirements, eligibility, and degree progress.",
    "Attendance_Agent": "Handle attendance requests, but the current database contains no attendance records.",
    "Schedule_Agent": "Access class schedules, exam timetables, and academic calendar events.",
    "Policy_Agent": "Answer questions about university regulations, certificates, and academic policies.",
    "Analytics_Agent": "Analyze grades, academic performance, KPIs, and student progress.",
    "Recommendation_Agent": "Provide personalized learning recommendations and academic guidance.",
    "Assessment_Agent": "Handle assessment requests, quizzes, practice exams, and evaluations.",
}

AGENT_CONTEXTS = {
    "Instructor_Agent": "You are responsible for instructor-related services, including instructor profiles, teaching assignments, office hours, and faculty information. Use tools as needed.",
    "Course_Agent": "You are responsible for course-related services, including course information, curriculum, learning materials, prerequisites, and academic content. Use tools as needed.",
    "Graduation_Agent": "You are responsible for graduation services, including graduation requirements, credit eligibility, degree progress, and graduation status. Use tools as needed.",
    "Attendance_Agent": "You are responsible for attendance services, including attendance records, absence tracking, attendance analytics, and attendance-related requests. Use tools as needed.",
    "Schedule_Agent": "You are responsible for academic scheduling, including class timetables, exam schedules, academic calendar events, and lecture sessions. Use tools as needed.",
    "Policy_Agent": "You are responsible for answering questions about university regulations, academic policies, certificates, enrollment rules, and institutional procedures. Use tools as needed.",
    "Analytics_Agent": "You are responsible for academic analytics, including grades, GPA, student performance, course statistics, and academic insights. Use tools as needed.",
    "Recommendation_Agent": "You are responsible for providing personalized academic recommendations, learning paths, course suggestions, and study guidance. Use tools as needed.",
    "Assessment_Agent": "You are responsible for assessments, including quizzes, practice exams, IQ tests, programming assessments, automated evaluation, and AI-generated feedback. Use tools as needed.",
}

DATABASE_CONTEXT = """
CURRENT UNIVERSITY DATABASE (university.db):
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
There is NO attendance table, NO assessment table, NO policy table, and NO admin table in this database.
Never invent attendance, assessment, policy, or admin records. If a request needs data that does not exist in this database, say that the current dataset does not contain it.
Grades are available through takes.grade. Student credit totals are available through student.tot_cred.
"""

AGENT_TOOLS = {
    "Instructor_Agent": ["get_instructor_profile", "assign_course_instructor", "get_instructor_load", "update_office_hours"],
    "Course_Agent": ["get_course_details", "validate_course_prerequisites", "update_course_syllabus", "check_course_capacity", "search_courses"],
    "Graduation_Agent": ["check_graduation_eligibility", "calculate_gpa", "audit_remaining_credits", "issue_graduation_clearance"],
    "Attendance_Agent": ["register_attendance", "get_student_attendance", "get_attendance_summary", "request_attendance_excuse", "get_absence_warnings"],
    "Schedule_Agent": ["find_available_room", "create_class_slot", "generate_student_schedule", "resolve_schedule_conflict"],
    "Policy_Agent": ["query_university_policy", "validate_action_against_policy", "get_certificate_requirements", "get_grading_policy", "get_registration_policy"],
    "Analytics_Agent": ["get_failures_and_success_rates", "track_student_performance_trend", "generate_enrollment_report", "student_grade_report"],
    "Recommendation_Agent": ["recommend_courses", "suggest_academic_plan", "career_path_recommendation", "student_grade_report", "recommend_learning_resources", "identify_at_risk_students", "department_kpis"],
    "Assessment_Agent": ["generate_practice_quiz", "evaluate_student_answers", "generate_iq_test", "recommend_learning_resources_from_assessment", "get_assessment_history"],
}
