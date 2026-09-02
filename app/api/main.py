import io
import os
import sqlite3
import pandas as pd
from typing import Optional, List
from fastapi import FastAPI, HTTPException, Depends, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from pydub import AudioSegment
from app.core.security import (
    create_access_token, get_current_user,
    create_admin_token, get_current_admin,
    ADMIN_EMAIL, ADMIN_PASSWORD, ACCESS_TOKEN_EXPIRE_MINUTES, ADMIN_TOKEN_EXPIRE_MINUTES
)
from app.data.connector import USER_INDEX, DB_PATH
from app.agents.supervisor import MCPClient
from app.observability.tracing import _fetch_langfuse_dashboard_data
from app.services.speech import transcribe_audio_bytes
import subprocess
import imageio_ffmpeg

def convert_webm_to_wav(audio_bytes: bytes) -> bytes:
    ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
    
    # Run ffmpeg as a subprocess reading from stdin and writing to stdout
    process = subprocess.Popen(
        [
            ffmpeg_path,
            "-i", "pipe:0",          # Read from stdin
            "-f", "wav",             # Force WAV container
            "-acodec", "pcm_s16le",  # 16-bit PCM codec
            "-ar", "16000",          # 16kHz sample rate
            "-ac", "1",              # Mono
            "pipe:1"                 # Output to stdout
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    wav_bytes, stderr = process.communicate(input=audio_bytes)
    
    if process.returncode != 0:
        raise RuntimeError(f"FFmpeg conversion error: {stderr.decode()}")
        
    return wav_bytes

app = FastAPI(title="Kayfa Agentic LMS API", version="2.0.0")

# 1. FIX: Avoid combining '*' origins with allow_credentials=True
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "http://127.0.0.1:8000", "*"],
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

# -------------------------------------------------------------------
# Authentication & User Endpoints
# -------------------------------------------------------------------
# FIX: Changed to standard 'def' so blocking SQLite calls run in threadpool
@app.post("/api/auth/login")
def login(req: LoginRequest):
    user_id = req.user_id.strip()
    role = req.role.strip()

    user_info = USER_INDEX.get(f"{role}:{user_id}")
    if not user_info:
        raise HTTPException(status_code=401, detail="User ID not found in database.")

    # Calculate actual GPA from takes table using direct cursor
    gpa = 3.4
    if os.path.exists(DB_PATH):
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            grade_map = {"A": 4.0, "A-": 3.7, "B+": 3.3, "B": 3.0, "B-": 2.7, "C+": 2.3, "C": 2.0, "F": 0.0}
            cursor.execute("SELECT grade FROM takes WHERE ID = ?", (user_id,))
            rows = cursor.fetchall()
            conn.close()

            valid_grades = [grade_map[row[0]] for row in rows if row[0] in grade_map]
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

# -------------------------------------------------------------------
# Chat & Audio Endpoints
# -------------------------------------------------------------------

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

@app.post("/api/chat/audio")
async def chat_audio(
    file: UploadFile = File(...),
    current_user=Depends(get_current_user)
):
    user_id = current_user["user_id"]
    user_role = current_user["role"]
    print(f"Received audio file: {file.filename} from user {user_id} ({user_role})")
    
    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="Audio file is required.")

    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Uploaded audio is empty.")

    # Step 1: Auto-convert incoming audio to 16kHz mono WAV
    try:
        processed_audio_bytes = convert_webm_to_wav(audio_bytes)
    except Exception as conv_exc:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to process or convert audio file format: {conv_exc}"
        ) from conv_exc
    # Step 2: Pass converted 16kHz WAV bytes to your transcription pipeline
    try:
        transcript = transcribe_audio_bytes(processed_audio_bytes, sample_rate=16000)
    except Exception as exc:
        raise HTTPException(
            status_code=400, 
            detail=f"Audio transcription failed. Details: {exc}"
        ) from exc

    if not transcript.strip():
        raise HTTPException(status_code=400, detail="No text was recognized from the audio.")

    return await client.process_query_for_api(
        query=transcript.strip(),
        user_id=user_id,
        user_role=user_role,
        history=[]
    )
# -------------------------------------------------------------------
# Direct Academic Data Endpoints
# -------------------------------------------------------------------

# FIX: Changed route signatures to standard 'def' to handle DB I/O off-thread
@app.get("/api/academic/grades")
def get_grades(current_user=Depends(get_current_user)):
    user_id = current_user["user_id"]
    if not os.path.exists(DB_PATH):
        return {"grades": []}
    
    conn = sqlite3.connect(DB_PATH)
    query = """
        SELECT t.course_id, c.title, c.credits, t.semester, t.year, t.grade
        FROM takes t
        JOIN course c ON t.course_id = c.course_id
        WHERE t.ID = ?
        ORDER BY t.year DESC, t.semester
    """
    df = pd.read_sql_query(query, conn, params=(user_id,))
    conn.close()
    return {"grades": df.to_dict(orient="records")}

@app.get("/api/academic/schedule")
def get_schedule(current_user=Depends(get_current_user)):
    user_id = current_user["user_id"]
    if not os.path.exists(DB_PATH):
        return {"schedule": []}
    
    conn = sqlite3.connect(DB_PATH)
    query = """
        SELECT t.course_id, c.title, s.building, s.room_number, ts.day, ts.start_hr, ts.start_min, ts.end_hr, ts.end_min
        FROM takes t
        JOIN course c ON t.course_id = c.course_id
        JOIN section s ON t.course_id = s.course_id AND t.sec_id = s.sec_id AND t.semester = s.semester AND t.year = s.year
        LEFT JOIN time_slot ts ON s.time_slot_id = ts.time_slot_id
        WHERE t.ID = ?
    """
    df = pd.read_sql_query(query, conn, params=(user_id,))
    conn.close()
    return {"schedule": df.to_dict(orient="records")}

@app.get("/api/academic/courses")
def get_courses(current_user=Depends(get_current_user)):
    if not os.path.exists(DB_PATH):
        return {"courses": []}
    
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT course_id, title, dept_name, credits FROM course LIMIT 50", conn)
    conn.close()
    return {"courses": df.to_dict(orient="records")}

# -------------------------------------------------------------------
# Admin Endpoints & Static Files
# -------------------------------------------------------------------

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

app.mount("/static", StaticFiles(directory="frontend/static"), name="static")

@app.get("/")
async def serve_portal():
    return FileResponse(os.path.join("frontend", "templates", "aou_html.html"))

@app.get("/aou_admin.html")
async def serve_admin():
    return FileResponse(os.path.join("frontend", "templates", "aou_admin.html"))
