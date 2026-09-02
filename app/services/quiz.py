import json
from groq import Groq
from app.agents.config import GROQ_API_KEY, GROQ_MODEL
from app.data.connector import save_lesson_content_for_course, add_quiz_grade

_client = Groq(api_key=GROQ_API_KEY)

QUIZ_SYSTEM_PROMPT = (
    "You generate short multiple choice quiz questions strictly based on the course "
    "material given to you. Return ONLY a JSON array, no preamble, no markdown fences. "
    "Each item must look exactly like: "
    '{"question": "...", "options": ["...", "...", "...", "..."], "correct_index": 0}. '
    "Never invent facts outside the given material."
)


def generate_quiz(course_title: str, material: str, n: int = 3):
    if not material.strip():
        raise ValueError("No lesson content available for this course yet.")

    prompt = f"Course: {course_title}\nMaterial:\n{material}\n\nGenerate exactly {n} multiple choice questions."
    resp = _client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": QUIZ_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
    )
    raw = resp.choices[0].message.content.strip()
    raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    questions = json.loads(raw)
    return questions


def generate_quiz_for_course(course_id: str, course_title: str, n: int = 3):
    material = save_lesson_content_for_course(course_id)
    return generate_quiz(course_title, material, n)


def grade_and_save_quiz(student_id: str, course_id: str, questions: list, answers: dict):
    total = len(questions)
    correct = sum(
        1 for i, q in enumerate(questions)
        if answers.get(str(i)) == q["correct_index"]
    )
    score = round((correct / total) * 10, 1) if total else 0
    add_quiz_grade(student_id, course_id, score)
    return correct, total, score
