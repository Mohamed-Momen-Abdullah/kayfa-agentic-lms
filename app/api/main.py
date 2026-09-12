import logging
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, BackgroundTasks
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.agents.quiz_agent import (
    generate_quiz_from_material,
    grade_quiz,
    generate_improvement_plan,
    refine_quiz_experience,
    quiz_memory,
    quiz_refiner,
)
from app.agents.academic_agent import academic_memory, academic_refiner
from app.agents.supervisor import route_chat_message
from app.agents.planner import build_intervention_plan, execute_intervention_plan
from app.core.config import settings
from app.core.security import authenticate, create_access_token, get_current_user
from app.db.connector import (
    get_course,
    get_courses_for_student,
    get_instructor_report,
    get_student_report,
    get_personal_records,
    add_quiz_grade,
    get_admin_overview,
    get_chat_history,
    update_chat_trace_feedback,
    get_latest_intervention_plan,
    get_instructor_alerts,
)
from app.services.tracing import log_chat_trace
from app.services.voice import transcribe_audio


BASE_DIR = Path(__file__).resolve().parent.parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"

app = FastAPI(title=settings.PROJECT_NAME)


# In-memory store for "currently open" quizzes, keyed by a one-time token.
# Final scored results are persisted to MongoDB via add_quiz_grade —
# this cache only needs to survive between "generate" and "submit"
# for one quiz.
_ACTIVE_QUIZZES: dict[str, dict] = {}


# ------------------------------------------------------------------ #
# Schemas
# ------------------------------------------------------------------ #
class LoginRequest(BaseModel):
    username: str
    password: str


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    query: str
    history: list[ChatMessage] = []


class ChatFeedbackRequest(BaseModel):
    experience_id: str
    feedback: str  # "up" | "down"


class QuizGenerateRequest(BaseModel):
    course_id: str


class QuizSubmitRequest(BaseModel):
    quiz_token: str
    answers: dict


# ------------------------------------------------------------------ #
# Auth
# ------------------------------------------------------------------ #
@app.post("/api/auth/login")
def login(payload: LoginRequest):
    user = authenticate(
        payload.username,
        payload.password,
    )

    if not user:
        raise HTTPException(
            status_code=401,
            detail="Invalid username, password, or role.",
        )

    token = create_access_token(
        user["id"],
        user["role"],
    )

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": user,
    }


@app.get("/api/auth/me")
def me(current=Depends(get_current_user)):
    return current["user_info"]


@app.post("/api/auth/logout")
def logout(current=Depends(get_current_user)):
    # JWTs are stateless here; logout is handled client-side by discarding
    # the token. This endpoint exists so the frontend has a clean call to
    # make and a natural place to add token revocation later if needed.
    return {"status": "ok"}


# ------------------------------------------------------------------ #
# Reports (role-aware)
# ------------------------------------------------------------------ #
def _self_refining_stats() -> dict:
    """Diagnostics for the admin dashboard: how much each self-refining
    agent has learned from, how often refinement has actually fired, what
    it currently believes, how much of that came from real user feedback
    vs. the LLM grading itself, and a peek at the actual recent
    experiences driving it — so it's not a black box."""
    def _agent_stats(memory, refiner):
        recent = [
            {
                "query": e.get("query", ""),
                "answer": e.get("answer", ""),
                "score": e.get("evaluation", {}).get("score"),
                # Academic uses "weaknesses" (LLM judge); quiz uses "missed"
                # (actual missed questions) — same concept, different key.
                "weaknesses": e.get("evaluation", {}).get("weaknesses")
                    or e.get("evaluation", {}).get("missed", []),
                "user_feedback": e.get("user_feedback"),
                "timestamp": e.get("timestamp"),
            }
            for e in reversed(memory.get_recent(10))  # newest first
        ]
        return {
            "experiences_recorded": memory.total_seen,
            "refinements_triggered": refiner.refinement_count,
            "last_refined_at": refiner.last_refined_at,
            "current_strategy": refiner.get_strategy(),
            "feedback_counts": memory.get_feedback_counts(),
            "recent_experiences": recent,
        }

    return {
        "academic_agent": _agent_stats(academic_memory, academic_refiner),
        "quiz_agent": _agent_stats(quiz_memory, quiz_refiner),
    }


@app.get("/api/report")
def report(current=Depends(get_current_user)):
    role = current["role"]
    user_id = current["user_id"]

    if role == "Student":
        return get_student_report(user_id)

    if role == "Instructor":
        return get_instructor_report(user_id)

    if role == "Admin":
        overview = get_admin_overview()
        overview["self_refining"] = _self_refining_stats()
        return overview

    raise HTTPException(
        status_code=400,
        detail="Unknown role.",
    )


@app.get("/api/courses")
def my_courses(current=Depends(get_current_user)):
    if current["role"] != "Student":
        raise HTTPException(
            status_code=403,
            detail="Only students have enrolled courses.",
        )

    courses = get_courses_for_student(
        current["user_id"]
    )

    return [
        {
            "id": c["_id"],
            "code": c.get("code", ""),
            "title": c.get("title", ""),
        }
        for c in courses
    ]


# ------------------------------------------------------------------ #
# Chat (Academic Help Agent + Quiz Agent, routed by the supervisor)
# ------------------------------------------------------------------ #
@app.post("/api/chat")
async def chat(
    payload: ChatRequest,
    current=Depends(get_current_user),
):
    role = current["role"]
    user_id = current["user_id"]

    course_context = get_personal_records(
        role,
        user_id,
    )

    history = [
        m.model_dump()
        for m in payload.history
    ]

    result = await route_chat_message(
        payload.query,
        role,
        course_context=course_context,
        history=history,
        user_id=user_id,
    )

    log_chat_trace(
        user_id=user_id,
        user_role=role,
        query=payload.query,
        response=result["response"],
        agent=result["agent"],
        sentiment=result["sentiment"],
        usage=result.get("usage"),
    )

    return {
        "response": result["response"],
        "agent": result["agent"],
        "sentiment": result["sentiment"],
        # Only present for academic_agent answers — that's the only agent
        # currently running through the self-refining/evaluation loop.
        "experience_id": result.get("usage", {}).get("experience_id"),
    }


@app.post("/api/chat/feedback")
def chat_feedback(payload: ChatFeedbackRequest, current=Depends(get_current_user)):
    """Records an explicit thumbs up/down on a past academic_agent answer.
    This is real human signal, as opposed to the LLM judging its own
    answer — StrategyRefiner treats a "down" as significant on its own,
    even if the automated evaluator scored the answer fine."""
    if payload.feedback not in ("up", "down"):
        raise HTTPException(status_code=400, detail="feedback must be 'up' or 'down'.")

    found_in_memory = academic_memory.set_feedback(payload.experience_id, payload.feedback)
    # Also mirror onto the trace row so a reloaded chat history shows the
    # same feedback state instead of resetting the buttons.
    found_in_trace = update_chat_trace_feedback(payload.experience_id, payload.feedback)

    if not found_in_memory and not found_in_trace:
        # Most likely: feedback arrived before the background evaluation
        # task finished writing the experience (a race that's realistically
        # only possible if the student reacts within a second or so).
        raise HTTPException(
            status_code=404,
            detail="This response isn't ready to receive feedback yet — try again in a moment.",
        )

    return {"status": "ok"}


@app.get("/api/chat/history")
def chat_history(current=Depends(get_current_user)):
    """Returns this signed-in user's own past conversation with the chat
    agents (never anyone else's), so the frontend can restore it after a
    fresh login instead of starting empty every time."""
    return {"messages": get_chat_history(current["user_id"])}


# ------------------------------------------------------------------ #
# Intervention planner (at-risk students)
# ------------------------------------------------------------------ #
async def _run_planner_background(student_id: str):
    """Fired after events that can reveal a new risk signal (currently:
    quiz submission). Detects, plans, AND executes — so instructor
    alerts and the persisted plan are ready by the time anyone looks,
    without making the triggering request wait on it."""
    try:
        plan = await build_intervention_plan(student_id)
        if plan.get("steps"):
            await execute_intervention_plan(student_id, plan)
    except Exception:
        logging.getLogger(__name__).error(
            "Background intervention planner run failed for %s", student_id, exc_info=True
        )


@app.post("/api/planner/run")
async def planner_run(current=Depends(get_current_user)):
    """On-demand: student (or something acting on their behalf) asks
    'am I falling behind, and if so what should I do about it' and
    gets the plan run synchronously, with results included."""
    if current["role"] != "Student":
        raise HTTPException(status_code=403, detail="Only students have an intervention plan.")

    plan = await build_intervention_plan(current["user_id"])
    result = await execute_intervention_plan(current["user_id"], plan)
    return result


@app.get("/api/planner/latest")
def planner_latest(current=Depends(get_current_user)):
    if current["role"] != "Student":
        raise HTTPException(status_code=403, detail="Only students have an intervention plan.")

    plan = get_latest_intervention_plan(current["user_id"])
    return plan or {"status": "none", "signals": [], "steps": [], "summary": "No plan run yet."}


@app.get("/api/planner/alerts")
def planner_alerts(current=Depends(get_current_user)):
    """Unresolved at-risk alerts the planner raised for this
    instructor's students."""
    if current["role"] != "Instructor":
        raise HTTPException(status_code=403, detail="Only instructors have student alerts.")

    return {"alerts": get_instructor_alerts(current["user_id"])}


# ------------------------------------------------------------------ #
# Quiz Agent (formal, per-course quizzes)
# ------------------------------------------------------------------ #
@app.post("/api/quiz/generate")
async def quiz_generate(
    payload: QuizGenerateRequest,
    current=Depends(get_current_user),
):
    if current["role"] != "Student":
        raise HTTPException(
            status_code=403,
            detail="Only students can take quizzes.",
        )

    course = get_course(
        payload.course_id
    )

    if not course:
        raise HTTPException(
            status_code=404,
            detail="Course not found.",
        )

    questions, usage = await generate_quiz_from_material(
        course.get("title", ""),
        course.get("material", ""),
        n=4,
    )

    quiz_token = str(uuid.uuid4())

    _ACTIVE_QUIZZES[quiz_token] = {
        "student_id": current["user_id"],
        "course_id": payload.course_id,
        "questions": questions,
    }

    log_chat_trace(
        user_id=current["user_id"],
        user_role="Student",
        query=f"[quiz generated for {course.get('title')}]",
        response=f"{len(questions)} questions generated.",
        agent="quiz_agent",
        sentiment=None,
        usage=usage,
        kind="quiz_event",
    )

    # Never send correct_index to the client before grading.
    safe_questions = [
        {
            "question": q["question"],
            "options": q["options"],
        }
        for q in questions
    ]

    return {
        "quiz_token": quiz_token,
        "course_title": course.get("title", ""),
        "questions": safe_questions,
    }


@app.post("/api/quiz/submit")
async def quiz_submit(
    payload: QuizSubmitRequest,
    background_tasks: BackgroundTasks,
    current=Depends(get_current_user),
):
    # -------------------------------------------------------------- #
    # 1. Retrieve and invalidate the active quiz
    # -------------------------------------------------------------- #
    quiz = _ACTIVE_QUIZZES.pop(
        payload.quiz_token,
        None,
    )

    if not quiz or quiz["student_id"] != current["user_id"]:
        raise HTTPException(
            status_code=404,
            detail="Quiz not found or already submitted.",
        )

    # -------------------------------------------------------------- #
    # 2. Get course information
    # -------------------------------------------------------------- #
    course = get_course(
        quiz["course_id"]
    )

    course_title = (
        course.get("title", "this course")
        if course
        else "this course"
    )

    # -------------------------------------------------------------- #
    # 3. Grade the quiz
    # -------------------------------------------------------------- #
    correct, total, score, missed = grade_quiz(
        quiz["questions"],
        payload.answers,
    )

    # -------------------------------------------------------------- #
    # 4. Generate improvement plan (diagnosis + steps + project +
    #    concepts to look into), grounded in the course's own material
    # -------------------------------------------------------------- #
    plan = generate_improvement_plan(
        course_title,
        missed,
        score,
        course_material=course.get("material", "") if course else "",
    )
    analysis = plan.get("diagnosis", "")


    # Runs after the response is sent — this is an extra Groq call every
    # 10th quiz, no reason to make the student wait on it.
    background_tasks.add_task(
        refine_quiz_experience,
        topic=course_title,
        questions=quiz["questions"],
        score=score,
        missed=missed,
    )

    # A quiz submission is exactly the moment a new risk signal (a
    # declining score, a low grade) can appear — check right away
    # instead of waiting for a scheduled sweep.
    background_tasks.add_task(_run_planner_background, current["user_id"])

    # -------------------------------------------------------------- #
    # 6. Persist final quiz result
    # -------------------------------------------------------------- #
    add_quiz_grade(
        current["user_id"],
        quiz["course_id"],
        score,
        correct,
        total,
        analysis=analysis,
        improvement_plan=plan,
    )

    # -------------------------------------------------------------- #
    # 7. Trace the quiz submission
    # -------------------------------------------------------------- #
    log_chat_trace(
        user_id=current["user_id"],
        user_role="Student",
        query=f"[quiz submitted for {course_title}]",
        response=analysis,
        agent="quiz_agent",
        sentiment=None,
        usage={},
        kind="quiz_event",
    )

    # -------------------------------------------------------------- #
    # 8. Return result to frontend
    # -------------------------------------------------------------- #
    return {
        "correct": correct,
        "total": total,
        "score": score,
        "analysis": analysis,
        "improvement_plan": plan,
        "correct_answers": [
            q["correct_index"]
            for q in quiz["questions"]
        ],
    }

# ------------------------------------------------------------------ #
# Voice
# ------------------------------------------------------------------ #
@app.post("/api/voice/transcribe")
async def voice_transcribe(
    file: UploadFile = File(...),
    current=Depends(get_current_user),
):
    audio_bytes = await file.read()

    try:
        text = transcribe_audio(
            audio_bytes,
            filename=file.filename or "audio.webm",
        )
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=str(e),
        )

    return {"text": text}

# ------------------------------------------------------------------ #
# Frontend (single-page dashboard + static assets)
# ------------------------------------------------------------------ #
app.mount(
    "/static",
    StaticFiles(
        directory=FRONTEND_DIR / "static"
    ),
    name="static",
)

@app.get("/")
def index():
    return FileResponse(
        FRONTEND_DIR / "templates" / "portal.html"
    )

@app.get("/health")
def health():
    return {"status": "ok"}

# ------------------------------------------------------------------ #
# Debug — Academic Self-Refining Strategy
# ------------------------------------------------------------------ #
@app.get("/api/debug/strategy")
def debug_strategy():
    from app.agents.academic_agent import (
        academic_refiner,
        academic_memory,
    )

    return {
        "experiences_count": len(
            academic_memory.get_all()
        ),
        "current_strategy": academic_refiner.get_strategy(),
    }