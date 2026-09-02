import os
import bcrypt
from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.data.connector import find_user_by_username, get_user_by_id, build_login_profile

security = HTTPBearer(auto_error=True)

JWT_SECRET = "campusx-prototype-secret-2026"
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except (ValueError, AttributeError):
        return False


def authenticate(username: str, password: str, role: str):
    role = role.lower()
    if role == "admin":
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            return {"id": "admin", "name": "System Administrator", "role": "Admin"}
        return None

    user = find_user_by_username(username, role)
    if user and verify_password(password, user["password_hash"]):
        return build_login_profile(user)
    return None


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

        if role == "Admin":
            user_info = {"id": "admin", "name": "System Administrator", "role": "Admin"}
        else:
            mongo_user = get_user_by_id(user_id)
            if mongo_user is None:
                raise HTTPException(status_code=401, detail="User is no longer valid.")
            user_info = build_login_profile(mongo_user)

        return {"user_id": str(user_id), "role": str(role), "user_info": user_info}
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired authentication token.")
