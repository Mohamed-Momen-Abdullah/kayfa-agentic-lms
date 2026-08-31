import os
import sqlite3
import pandas as pd
from typing import Optional, List
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.core.security import (
    create_access_token, get_current_user,
    create_admin_token, get_current_admin,
    ADMIN_EMAIL, ADMIN_PASSWORD, ACCESS_TOKEN_EXPIRE_MINUTES, ADMIN_TOKEN_EXPIRE_MINUTES
)
from app.data.connector import USER_INDEX, DB_PATH
from app.agents.supervisor import MCPClient
from app.observability.tracing import _fetch_langfuse_dashboard_data


app = FastAPI(title="Kayfa Agentic LMS API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

client = MCPClient()

# Request Models
class LoginRequest(BaseModel):
    user_id: str
    password: str
    role: str

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    query: str
    history: Optional[List[ChatMessage]] = None

class AdminLoginRequest(BaseModel):
    email: str
    password: str

# Authentication
@app.post("/api/auth/login")
async def login(req: LoginRequest):
    user_id = req.user_id.strip()
    role = req.role.strip()

    user_info = USER_INDEX.get(f"{role}:{user_id}")
    if not user_info:
        raise HTTPException(status_code=401, detail="User ID not found in database.")

    # Calculate actual GPA from takes table
    gpa = 3.4
    if os.path.exists(DB_PATH):
        try:
            conn = sqlite3.connect(DB_PATH)
            grade_map = {"A": 4.0, "A-": 3.7, "B+": 3.3, "B": 3.0, "B-": 2.7, "C+": 2.3, "C": 2.0, "F": 0.0}
            df_g = pd.read_sql("SELECT grade FROM takes WHERE ID = ?", conn, params=[user_id])
            conn.close()
            valid_grades = [grade_map[g] for g in df_g['grade'].dropna() if g in grade_map]
            if valid_grades:
                gpa = round(sum(valid_grades) / len(valid_grades), 2)
        except Exception:
            pass

    token = create_access_token(user_id=user_id, role=role)
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "user": {
            "id": user_id,
            "role": role,
            "name": user_info.get("name"),
            "dept_name": user_info.get("dept_name"),
            "tot_cred": user_info.get("tot_cred", 0),
            "gpa": gpa,
            "advisor": "Dr. Ahmed Mansour",
            "semester": "Fall 2026"
        },
    }

@app.get("/api/auth/me")
async def me(current_user=Depends(get_current_user)):
    return {"user": current_user["user_info"]}

@app.post("/api/chat")
async def chat(req: ChatRequest, current_user=Depends(get_current_user)):
    user_id = current_user["user_id"]
    user_role = current_user["role"]
    query = req.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    clean_history = [{"role": m.role, "content": m.content} for m in (req.history or [])]
    return await client.process_query_for_api(
        query=query,
        user_id=user_id,
        user_role=user_role,
        history=clean_history
    )

# Direct Academic Data Endpoints for UI Tabs
@app.get("/api/academic/grades")
async def get_grades(current_user=Depends(get_current_user)):
    user_id = current_user["user_id"]
    if not os.path.exists(DB_PATH):
        return {"grades": []}
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql("""
        SELECT t.course_id, c.title, c.credits, t.semester, t.year, t.grade
        FROM takes t
        JOIN course c ON t.course_id = c.course_id
        WHERE t.ID = ?
        ORDER BY t.year DESC, t.semester
    """, conn, params=[user_id])
    conn.close()
    return {"grades": df.to_dict(orient="records")}

@app.get("/api/academic/schedule")
async def get_schedule(current_user=Depends(get_current_user)):
    user_id = current_user["user_id"]
    if not os.path.exists(DB_PATH):
        return {"schedule": []}
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql("""
        SELECT t.course_id, c.title, s.building, s.room_number, ts.day, ts.start_hr, ts.start_min, ts.end_hr, ts.end_min
        FROM takes t
        JOIN course c ON t.course_id = c.course_id
        JOIN section s ON t.course_id = s.course_id AND t.sec_id = s.sec_id AND t.semester = s.semester AND t.year = s.year
        LEFT JOIN time_slot ts ON s.time_slot_id = ts.time_slot_id
        WHERE t.ID = ?
    """, conn, params=[user_id])
    conn.close()
    return {"schedule": df.to_dict(orient="records")}

@app.get("/api/academic/courses")
async def get_courses(current_user=Depends(get_current_user)):
    if not os.path.exists(DB_PATH):
        return {"courses": []}
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql("SELECT course_id, title, dept_name, credits FROM course LIMIT 50", conn)
    conn.close()
    return {"courses": df.to_dict(orient="records")}

# Admin Observability
@app.post("/api/admin/login")
async def admin_login(req: AdminLoginRequest):
    if req.email.strip().lower() != ADMIN_EMAIL.lower() or req.password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid admin credentials.")
    return {
        "access_token": create_admin_token(ADMIN_EMAIL),
        "token_type": "bearer",
        "expires_in": ADMIN_TOKEN_EXPIRE_MINUTES * 60,
    }

@app.get("/api/admin/dashboard")
async def admin_dashboard(current_admin=Depends(get_current_admin)):
    data = _fetch_langfuse_dashboard_data(limit=100)
    return data

# Static Mounts & HTML Templates
app.mount("/static", StaticFiles(directory="frontend/static"), name="static")

@app.get("/")
async def serve_portal():
    return FileResponse(os.path.join("frontend", "templates", "aou_html.html"))

@app.get("/aou_admin.html")
async def serve_admin():
    return FileResponse(os.path.join("frontend", "templates", "aou_admin.html"))