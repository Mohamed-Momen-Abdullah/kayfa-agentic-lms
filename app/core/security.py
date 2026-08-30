import os
from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# Note: USER_INDEX will be created in app.data.connector in the next slicing phase
from app.data.connector import USER_INDEX

security = HTTPBearer(auto_error=True)

# Configuration
JWT_SECRET = "campusx-prototype-secret-2026"
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "elhosenyhassan007@gmail.com")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "123456789")
ADMIN_TOKEN_EXPIRE_MINUTES = int(os.getenv("ADMIN_TOKEN_EXPIRE_MINUTES", "120"))

def create_access_token(user_id: str, role: str):
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": str(role),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)).timestamp()),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("sub")
        role = payload.get("role")
        
        if not user_id or not role:
            raise HTTPException(status_code=401, detail="Invalid authentication token.")
            
        user_info = USER_INDEX.get(f"{role}:{user_id}")
        if user_info is None:
            raise HTTPException(status_code=401, detail="User is no longer valid.")
            
        return {"user_id": str(user_id), "role": str(role), "user_info": user_info}
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired authentication token.")

def create_admin_token(email: str):
    now = datetime.now(timezone.utc)
    payload = {
        "sub": email,
        "scope": "admin",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=ADMIN_TOKEN_EXPIRE_MINUTES)).timestamp()),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

async def get_current_admin(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if payload.get("scope") != "admin" or payload.get("sub") != ADMIN_EMAIL:
            raise HTTPException(status_code=403, detail="Admin access required.")
        return {"email": payload.get("sub")}
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired admin token.")
