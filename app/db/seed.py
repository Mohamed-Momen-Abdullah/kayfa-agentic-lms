"""
Seed MongoDB with demo data so the platform is usable right after setup.

Run with:  python -m app.db.seed

This is idempotent-ish: it clears the demo collections first, so re-running
it just resets you back to a clean demo state.
"""
from app.core.security import hash_password
from app.db.connector import get_db


def seed():
    db = get_db()
    if db is None:
        print("Could not connect to MongoDB. Check MONGO_URI in your .env file.")
        return

    print(f"Seeding database '{db.name}'...")
    db.users.delete_many({})
    db.courses.delete_many({})
    db.lessons.delete_many({})
    db.enrollments.delete_many({})
    db.quiz_grades.delete_many({})
    db.chat_traces.delete_many({})

    users = [
        {"_id": "I001", "username": "sarah.ahmed", "password_hash": hash_password("teach123"),
         "role": "Instructor", "full_name": "Dr. Sarah Ahmed", "department": "Computer Science"},
        {"_id": "I002", "username": "omar.khaled", "password_hash": hash_password("teach123"),
         "role": "Instructor", "full_name": "Dr. Omar Khaled", "department": "Mathematics"},
        {"_id": "S001", "username": "layla.hassan", "password_hash": hash_password("study123"),
         "role": "Student", "full_name": "Layla Hassan", "department": "Computer Science", "average_attendance": 92},
        {"_id": "S002", "username": "youssef.ali", "password_hash": hash_password("study123"),
         "role": "Student", "full_name": "Youssef Ali", "department": "Computer Science", "average_attendance": 85},
        {"_id": "S003", "username": "mona.said", "password_hash": hash_password("study123"),
         "role": "Student", "full_name": "Mona Said", "department": "Mathematics", "average_attendance": 97},
    ]
    db.users.insert_many(users)

    courses = [
        {
            "_id": "CS101", "code": "CS101", "title": "Introduction to Programming",
            "description": "Foundations of programming: variables, control flow, functions, and basic data structures.",
            "department": "Computer Science", "instructor_id": "I001",
            "material": (
                "Programming is the process of writing instructions for a computer to follow. "
                "A variable stores a value in memory under a name. Control flow statements like "
                "if/else and loops (for, while) let a program make decisions and repeat actions. "
                "A function is a reusable block of code that takes inputs (parameters) and can "
                "return an output. Basic data structures include lists (ordered, changeable "
                "collections) and dictionaries (key-value pairs)."
            ),
        },
        {
            "_id": "CS201", "code": "CS201", "title": "Data Structures & Algorithms",
            "description": "Arrays, linked lists, stacks, queues, trees, and algorithmic complexity.",
            "department": "Computer Science", "instructor_id": "I001",
            "material": (
                "A stack is a Last-In-First-Out (LIFO) structure: the last item added is the "
                "first removed, with push and pop operations. A queue is First-In-First-Out "
                "(FIFO), with enqueue and dequeue operations. A linked list stores elements as "
                "nodes, each pointing to the next, allowing efficient insertion/removal. Big-O "
                "notation describes how an algorithm's run time or memory use grows with input "
                "size, e.g. O(n) is linear time, O(log n) is logarithmic, O(n^2) is quadratic."
            ),
        },
        {
            "_id": "MATH101", "code": "MATH101", "title": "Calculus I",
            "description": "Limits, derivatives, and an introduction to integrals.",
            "department": "Mathematics", "instructor_id": "I002",
            "material": (
                "A limit describes the value a function approaches as its input approaches some "
                "point. The derivative of a function measures its instantaneous rate of change "
                "and is the slope of the tangent line at a point. Common derivative rules include "
                "the power rule, product rule, quotient rule, and chain rule. An integral can be "
                "thought of as the area under a curve, and is the reverse operation of "
                "differentiation (the Fundamental Theorem of Calculus)."
            ),
        },
    ]
    db.courses.insert_many(courses)

    # Real per-lesson content, several lessons per course, so quiz
    # generation has something meaningful to retrieve from instead of one
    # short paragraph. One "logistics" lesson per course is deliberately
    # off-topic/administrative — a good check that retrieval filters it
    # out of quiz material rather than blindly including it.
    lessons = [
        # -- CS101 --------------------------------------------------- #
        {"course_id": "CS101", "order": 1, "title": "Course Logistics",
         "content": (
             "Welcome to Introduction to Programming. Office hours are Tuesdays "
             "and Thursdays from 2 to 4 PM. Grading is 40% assignments, 30% "
             "midterm, 30% final project. Late submissions lose 10% per day. "
             "Please join the course forum for announcements and use the "
             "posted email format for any questions to the teaching staff."
         )},
        {"course_id": "CS101", "order": 2, "title": "Variables and Data Types",
         "content": (
             "A variable stores a value in memory under a name so a program can "
             "refer to it later. Common data types include integers (whole "
             "numbers), floats (decimal numbers), strings (text), and booleans "
             "(True/False). Assignment binds a name to a value with the = "
             "operator. Variables can be reassigned to new values of the same "
             "or a different type in dynamically typed languages like Python. "
             "Choosing descriptive variable names makes code easier to read "
             "and maintain."
         )},
        {"course_id": "CS101", "order": 3, "title": "Control Flow",
         "content": (
             "Control flow statements let a program make decisions and repeat "
             "actions instead of running every line top to bottom. An if/else "
             "statement runs one block of code or another depending on a "
             "condition. A for loop repeats a block a fixed number of times or "
             "once per item in a collection. A while loop repeats a block as "
             "long as a condition stays true. break exits a loop early, and "
             "continue skips to the next iteration."
         )},
        {"course_id": "CS101", "order": 4, "title": "Functions",
         "content": (
             "A function is a reusable, named block of code that takes inputs "
             "called parameters and can return an output. Defining a function "
             "once and calling it many times avoids repeating the same logic. "
             "Parameters can have default values, and a function without an "
             "explicit return statement returns None. Breaking a program into "
             "small functions, each doing one clear thing, makes code easier "
             "to test and debug."
         )},
        {"course_id": "CS101", "order": 5, "title": "Basic Data Structures",
         "content": (
             "A list is an ordered, changeable collection of items, accessed "
             "by index starting at 0. A dictionary stores key-value pairs and "
             "looks values up by key rather than position. Lists are useful "
             "when order matters or duplicates are allowed; dictionaries are "
             "useful for fast lookups by a unique identifier. Both can be "
             "nested inside each other to represent more complex data."
         )},

        # -- CS201 --------------------------------------------------- #
        {"course_id": "CS201", "order": 1, "title": "Course Logistics",
         "content": (
             "Welcome to Data Structures & Algorithms. This course builds "
             "directly on CS101. Assignments are submitted through the course "
             "portal by 11:59 PM on the due date. There are two exams and a "
             "final coding project implementing a data structure from scratch."
         )},
        {"course_id": "CS201", "order": 2, "title": "Stacks and Queues",
         "content": (
             "A stack is a Last-In-First-Out (LIFO) structure: the last item "
             "added is the first removed, using push and pop operations. A "
             "queue is First-In-First-Out (FIFO), using enqueue and dequeue "
             "operations. Stacks are used for undo history and function call "
             "tracking; queues are used for task scheduling and breadth-first "
             "traversal."
         )},
        {"course_id": "CS201", "order": 3, "title": "Linked Lists",
         "content": (
             "A linked list stores elements as nodes, each holding a value and "
             "a pointer to the next node, allowing efficient insertion and "
             "removal without shifting other elements (unlike an array). A "
             "singly linked list only points forward; a doubly linked list "
             "also points to the previous node, allowing traversal in both "
             "directions at the cost of extra memory per node."
         )},
        {"course_id": "CS201", "order": 4, "title": "Big-O Notation",
         "content": (
             "Big-O notation describes how an algorithm's run time or memory "
             "use grows as input size grows. O(1) is constant time — it "
             "doesn't depend on input size. O(n) is linear time. O(log n) is "
             "logarithmic, common in binary search. O(n^2) is quadratic, "
             "common in simple nested-loop algorithms. Big-O describes the "
             "worst case, ignoring constant factors, so an algorithm can be "
             "compared independent of hardware speed."
         )},

        # -- MATH101 --------------------------------------------------#
        {"course_id": "MATH101", "order": 1, "title": "Course Logistics",
         "content": (
             "Welcome to Calculus I. Homework is assigned weekly and is not "
             "graded for correctness but for completion; the midterm and "
             "final make up most of the grade. A scientific calculator is "
             "allowed on exams; graphing calculators are not."
         )},
        {"course_id": "MATH101", "order": 2, "title": "Limits",
         "content": (
             "A limit describes the value a function approaches as its input "
             "approaches some point, even if the function isn't defined "
             "exactly at that point. Limits can be evaluated from the left or "
             "right; if both one-sided limits agree, the two-sided limit "
             "exists. Limits are the foundation for defining both derivatives "
             "and integrals rigorously."
         )},
        {"course_id": "MATH101", "order": 3, "title": "Derivatives",
         "content": (
             "The derivative of a function measures its instantaneous rate of "
             "change and equals the slope of the tangent line at a point. "
             "Common derivative rules include the power rule (bring down the "
             "exponent and reduce it by one), the product rule, the quotient "
             "rule, and the chain rule for composed functions."
         )},
        {"course_id": "MATH101", "order": 4, "title": "Introduction to Integrals",
         "content": (
             "An integral can be thought of as the area under a curve between "
             "two points, and is the reverse operation of differentiation. "
             "The Fundamental Theorem of Calculus connects derivatives and "
             "integrals: it states that integrating a function's derivative "
             "over an interval returns the net change in the function over "
             "that interval."
         )},
    ]
    db.lessons.insert_many(lessons)

    enrollments = [
        {"student_id": "S001", "course_id": "CS101", "progress_percent": 80, "final_grade": 8.7},
        {"student_id": "S001", "course_id": "CS201", "progress_percent": 45, "final_grade": None},
        {"student_id": "S002", "course_id": "CS101", "progress_percent": 60, "final_grade": 7.2},
        {"student_id": "S003", "course_id": "MATH101", "progress_percent": 90, "final_grade": 9.1},
    ]
    db.enrollments.insert_many(enrollments)

    db.quiz_grades.insert_many([
        {"student_id": "S001", "course_id": "CS101", "score": 8.0, "correct": 4, "total": 5},
        {"student_id": "S001", "course_id": "CS101", "score": 9.0, "correct": 9, "total": 10},
        {"student_id": "S002", "course_id": "CS101", "score": 6.5, "correct": 13, "total": 20},
    ])

    print("Seed complete:")
    print(f"  users:       {db.users.count_documents({})}")
    print(f"  courses:     {db.courses.count_documents({})}")
    print(f"  lessons:     {db.lessons.count_documents({})}")
    print(f"  enrollments: {db.enrollments.count_documents({})}")
    print(f"  quiz_grades: {db.quiz_grades.count_documents({})}")
    print()
    print("Demo logins (password shown, role required at login):")
    print("  Student    | layla.hassan / study123")
    print("  Student    | youssef.ali  / study123")
    print("  Instructor | sarah.ahmed  / teach123")
    print("  Admin      | uses ADMIN_USERNAME / ADMIN_PASSWORD from your .env")


if __name__ == "__main__":
    seed()