from dotenv import load_dotenv
load_dotenv()

import os
from bson import ObjectId
from typing import Optional, List
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.core.security import authenticate, create_access_token, get_current_user
from app.agents.supervisor import MCPClient
from app.observability.tracing import _fetch_langfuse_dashboard_data
from app.data.connector import get_student_report, get_instructor_report, courses_col
from app.services.quiz import generate_quiz_for_course, grade_and_save_quiz

app = FastAPI(title="Kayfa Agentic LMS API", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

client = MCPClient()

_quiz_sessions = {}


class LoginRequest(BaseModel):
    username: str
    password: str
    role: str

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    query: str
    history: Optional[List[ChatMessage]] = None

class QuizGenerateRequest(BaseModel):
    course_id: str

class QuizSubmitRequest(BaseModel):
    course_id: str
    answers: dict


@app.post("/api/auth/login")
async def login(req: LoginRequest):
    user = authenticate(req.username.strip(), req.password, req.role.strip())
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username, password, or role.")
    token = create_access_token(user_id=user["id"], role=user["role"])
    return {"access_token": token, "token_type": "bearer", "user": user}


@app.get("/api/auth/me")
async def me(current_user=Depends(get_current_user)):
    return {"user": current_user["user_info"]}


@app.post("/api/auth/logout")
async def logout(current_user=Depends(get_current_user)):
    return {"ok": True}


@app.get("/api/report")
async def report(current_user=Depends(get_current_user)):
    role = current_user["role"]
    user_id = current_user["user_id"]
    if role == "Student":
        return get_student_report(user_id)
    if role == "Instructor":
        return get_instructor_report(user_id)
    if role == "Admin":
        return _fetch_langfuse_dashboard_data(limit=100)
    raise HTTPException(status_code=403, detail="Unknown role.")


@app.post("/api/chat")
async def chat(req: ChatRequest, current_user=Depends(get_current_user)):
    user_id = current_user["user_id"]
    user_role = current_user["role"]
    query = req.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    clean_history = [{"role": m.role, "content": m.content} for m in (req.history or [])]
    return await client.process_query_for_api(
        query=query, user_id=user_id, user_role=user_role, history=clean_history
    )


@app.post("/api/quiz/generate")
async def quiz_generate(req: QuizGenerateRequest, current_user=Depends(get_current_user)):
    if current_user["role"] != "Student":
        raise HTTPException(status_code=403, detail="Quizzes are only available to students.")
    try:
        course = courses_col.find_one({"_id": ObjectId(req.course_id)})
    except Exception:
        course = None
    if not course:
        raise HTTPException(status_code=404, detail="Course not found.")
    try:
        questions = generate_quiz_for_course(req.course_id, course["title"], n=3)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

    session_key = f"{current_user['user_id']}:{req.course_id}"
    _quiz_sessions[session_key] = questions

    return {
        "course_id": req.course_id,
        "questions": [{"question": q["question"], "options": q["options"]} for q in questions],
    }


@app.post("/api/quiz/submit")
async def quiz_submit(req: QuizSubmitRequest, current_user=Depends(get_current_user)):
    if current_user["role"] != "Student":
        raise HTTPException(status_code=403, detail="Quizzes are only available to students.")
    session_key = f"{current_user['user_id']}:{req.course_id}"
    questions = _quiz_sessions.get(session_key)
    if not questions:
        raise HTTPException(status_code=400, detail="No active quiz for this course. Generate one first.")

    correct, total, score = grade_and_save_quiz(current_user["user_id"], req.course_id, questions, req.answers)
    del _quiz_sessions[session_key]
    return {"correct": correct, "total": total, "score": score}


app.mount("/static", StaticFiles(directory="frontend/static"), name="static")

@app.get("/")
async def serve_portal():
    return FileResponse(os.path.join("frontend", "templates", "aou_html.html"))
