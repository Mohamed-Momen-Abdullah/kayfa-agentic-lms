from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError

from app.core.config import settings
from app.db.connector import find_user_by_username, get_user_by_id, build_login_profile

security = HTTPBearer(auto_error=True)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except (ValueError, AttributeError, TypeError):
        return False


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def authenticate(username: str, password: str):
    # Role is no longer supplied by the client — it's looked up from the
    # account itself. The username is expected to be unique across roles
    # (student/instructor accounts are separate from the single admin
    # account, which is checked first via env credentials).
    if username == settings.ADMIN_USERNAME and password == settings.ADMIN_PASSWORD:
        return {"id": "admin", "name": "System Administrator", "role": "Admin", "department": ""}

    user = find_user_by_username(username)
    if user and verify_password(password, user.get("password_hash", "")):
        return build_login_profile(user)
    return None


def create_access_token(user_id: str, role: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": str(role),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)).timestamp()),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        user_id = payload.get("sub")
        role = payload.get("role")

        if not user_id or not role:
            raise HTTPException(status_code=401, detail="Invalid authentication token.")

        if role == "Admin":
            user_info = {"id": "admin", "name": "System Administrator", "role": "Admin", "department": ""}
        else:
            mongo_user = get_user_by_id(user_id)
            if mongo_user is None:
                raise HTTPException(status_code=401, detail="User is no longer valid.")
            user_info = build_login_profile(mongo_user)

        return {"user_id": str(user_id), "role": str(role), "user_info": user_info}
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired authentication token.")