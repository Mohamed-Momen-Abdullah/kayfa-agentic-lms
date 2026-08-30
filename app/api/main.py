import os
import time
from typing import Optional, List
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

# Local Application Imports (from the new modular structure)
from app.core.security import (
    create_access_token, get_current_user,
    create_admin_token, get_current_admin,
    ADMIN_EMAIL, ADMIN_PASSWORD, ACCESS_TOKEN_EXPIRE_MINUTES, ADMIN_TOKEN_EXPIRE_MINUTES
)

# Note: These modules will be populated in the next slicing phase
from app.data.connector import USER_INDEX
from app.agents.supervisor import MCPClient
from app.observability.tracing import _fetch_langfuse_dashboard_data

# Configuration
APP_NAME = "CampusX AI Secure API"
ALLOWED_ORIGINS = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://localhost:5500",
    "http://127.0.0.1:5500",
]

MAX_QUERY_LENGTH = int(os.getenv("MAX_QUERY_LENGTH", "4000"))
MAX_HISTORY_MESSAGES = int(os.getenv("MAX_HISTORY_MESSAGES", "6"))

MCP_KAYFA_TOOL_PATH = os.getenv("MCP_KAYFA_TOOL_PATH", r"C:\Users\ELZAHBIA\Vs_code\LLM\mcp_multi_agent_kayfa.py")
MCP_HUBSPOT_PATH = os.getenv("MCP_HUBSPOT_PATH", r"C:\Users\ELZAHBIA\Vs_code\MCP_Servers\hubspot_server.js")

app = FastAPI(title=APP_NAME, version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

client = MCPClient()

# Request Models
class LoginRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)
    role: str = Field(min_length=1, max_length=50)

class ChatMessage(BaseModel):
    role: str = Field(max_length=20)
    content: str = Field(max_length=4000)

class ChatRequest(BaseModel):
    query: str = Field(min_length=1, max_length=MAX_QUERY_LENGTH)
    history: Optional[List[ChatMessage]] = None

class AdminLoginRequest(BaseModel):
    email: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=1, max_length=200)

# Rate Limiting
login_attempts = {}

def check_login_rate_limit(request: Request):
    ip = request.client.host if request.client else "unknown"
    now = time.time()
    attempts = login_attempts.get(ip, [])
    attempts = [timestamp for timestamp in attempts if now - timestamp < 300]
    
    if len(attempts) >= 20:
        raise HTTPException(status_code=429, detail="Too many login attempts. Try again later.")
        
    attempts.append(now)
    login_attempts[ip] = attempts

# Application Lifecycle
@app.on_event("startup")
async def startup_event():
    if MCP_KAYFA_TOOL_PATH and os.path.exists(MCP_KAYFA_TOOL_PATH):
        try:
            await client.connect_to_server(MCP_KAYFA_TOOL_PATH)
        except Exception as e:
            print(f"⚠️ Kayfa MCP connect error: {e}")
            
    if MCP_HUBSPOT_PATH and os.path.exists(MCP_HUBSPOT_PATH):
        try:
            await client.connect_to_server(MCP_HUBSPOT_PATH)
        except Exception as e:
            print(f"⚠️ HubSpot MCP connect error: {e}")

@app.on_event("shutdown")
async def shutdown_event():
    await client.cleanup()

# Endpoints
@app.post("/api/auth/login")
async def login(req: LoginRequest, request: Request):
    check_login_rate_limit(request)
    
    user_id = req.user_id.strip()
    role = req.role.strip()
    generic_error = "Invalid credentials."

    if role not in ("Student", "Instructor"):
        raise HTTPException(status_code=401, detail=generic_error)

    user_info = USER_INDEX.get(f"{role}:{user_id}")
    if user_info is None:
        raise HTTPException(status_code=401, detail=generic_error)

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
            "student_id": user_info.get("student_id"),
            "instructor_id": user_info.get("instructor_id"),
            "tot_cred": user_info.get("tot_cred"),
        },
    }

@app.post("/api/auth/logout")
async def logout(current_user=Depends(get_current_user)):
    return {"status": "ok", "message": "Logged out successfully."}

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

    history = req.history or []
    history = history[-MAX_HISTORY_MESSAGES:]
    
    clean_history = []
    for message in history:
        if message.role not in ("user", "assistant"):
            continue
        clean_history.append({"role": message.role, "content": message.content[:4000]})

    result = await client.process_query_for_api(
        query=query,
        user_id=user_id,
        user_role=user_role,
        history=clean_history,
    )

    if isinstance(result, dict):
        response_text = result.get("response", "")
        sentiment = result.get("sentiment", None)
    else:
        response_text = str(result)
        sentiment = None

    return {
        "response": response_text,
        "sentiment": sentiment,
        "user": {"id": user_id, "role": user_role},
    }

@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "users_loaded": len(USER_INDEX),
        "authentication": "jwt",
        "authorization": "rbac",
    }

@app.post("/api/admin/login")
async def admin_login(req: AdminLoginRequest, request: Request):
    check_login_rate_limit(request)
    
    if req.email.strip().lower() != ADMIN_EMAIL.lower() or req.password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid admin credentials.")
        
    token = create_admin_token(ADMIN_EMAIL)
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": ADMIN_TOKEN_EXPIRE_MINUTES * 60,
    }

@app.get("/api/admin/dashboard")
async def admin_dashboard(current_admin=Depends(get_current_admin)):
    data = _fetch_langfuse_dashboard_data(limit=100)
    if data["status"] != "success":
        raise HTTPException(status_code=502, detail=data.get("error", "Failed to load Langfuse data."))
    return data

# Mount static files (CSS, JS, Images)
app.mount("/static", StaticFiles(directory="frontend/static"), name="static")

# Serve the HTML templates directly
@app.get("/")
async def serve_portal():
    return FileResponse(os.path.join("frontend", "templates", "aou_html.html"))

@app.get("/aou_admin.html")
async def serve_admin():
    return FileResponse(os.path.join("frontend", "templates", "aou_admin.html"))