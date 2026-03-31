import json
import os
from datetime import datetime, timedelta
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "healthguard-dev-secret-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 480  # 8 hours

USERS_FILE = "users.json"

pwd_context = CryptContext(schemes=["sha256_crypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")


def load_users() -> list:
    if not os.path.exists(USERS_FILE):
        return []
    with open(USERS_FILE, "r") as f:
        content = f.read().strip()
        return json.loads(content) if content else []


def save_users(users: list):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)


def get_user(username: str) -> Optional[dict]:
    for user in load_users():
        if user["username"] == username:
            return user
    return None


def authenticate_user(username: str, password: str) -> Optional[dict]:
    user = get_user(username)
    if not user or not pwd_context.verify(password, user["hashed_password"]):
        return None
    return user


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode["exp"] = expire
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        sub: str = payload.get("sub")
        role: str = payload.get("role", "")
        if sub is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    if role == "patient":
        # Patient tokens carry patient_id as sub — no users.json lookup needed
        return {"sub": sub, "role": "patient", "name": payload.get("name", "")}

    # Caregiver tokens — verify against users.json
    user = get_user(sub)
    if user is None:
        raise credentials_exception
    return user


async def require_caregiver(current_user: dict = Depends(get_current_user)) -> dict:
    if current_user.get("role") != "caregiver":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Caregiver access required",
        )
    return current_user


async def require_patient_or_caregiver(current_user: dict = Depends(get_current_user)) -> dict:
    if current_user.get("role") not in ("patient", "caregiver"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Authentication required",
        )
    return current_user


def setup_default_users():
    """Create a default admin account on first run if none exists."""
    users = load_users()
    if not any(u["username"] == "admin" for u in users):
        default_password = "admin123"
        users.append({
            "username": "admin",
            "hashed_password": pwd_context.hash(default_password),
            "role": "caregiver",
            "full_name": "Admin Caregiver",
        })
        save_users(users)
        print("[AUTH] ✅ Default caregiver account created")
        print("[AUTH]    username: admin")
        print(f"[AUTH]    password: {default_password}")
        print("[AUTH] ⚠️  Change the default password in production!")
    else:
        print("[AUTH] ✅ User store loaded")
