from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from fastapi import HTTPException, status, Depends, Request
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import secrets
from backend.config import get_settings

settings = get_settings()
security = HTTPBasic()

# Простая сессия в памяти (для production нужно использовать Redis или БД)
active_sessions = {}

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 часа


def verify_password(password: str) -> bool:
    """Проверка пароля администратора"""
    return secrets.compare_digest(password, settings.admin_password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Создание JWT токена"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=ALGORITHM)
    return encoded_jwt


def verify_token(token: str) -> Optional[dict]:
    """Верификация JWT токена"""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


def get_current_admin(request: Request) -> bool:
    """
    Проверка авторизации администратора.
    Проверяет токен в заголовке Authorization или в cookie.
    """
    # Проверяем заголовок Authorization
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
        payload = verify_token(token)
        if payload and payload.get("admin") == True:
            return True
    
    # Проверяем cookie
    token = request.cookies.get("admin_token")
    if token:
        payload = verify_token(token)
        if payload and payload.get("admin") == True:
            return True
    
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Требуется авторизация",
        headers={"WWW-Authenticate": "Bearer"},
    )


def authenticate_admin(password: str) -> Optional[str]:
    """
    Аутентификация администратора.
    Возвращает токен при успешной аутентификации.
    """
    if verify_password(password):
        access_token = create_access_token(
            data={"admin": True, "created_at": datetime.utcnow().isoformat()}
        )
        return access_token
    return None

