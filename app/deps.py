from datetime import datetime

from fastapi import Request

from app.config import sessions
from database import SessionLocal
from gmail_service import GmailService
from google_tasks_service import GoogleTasksService
from user_service import get_all_gmail_tokens


def get_current_user_from_session(request: Request):
    session_id = request.cookies.get("session_id")
    if not session_id:
        auth_header = (request.headers.get("Authorization") or "").strip()
        if auth_header.lower().startswith("bearer "):
            token = auth_header[7:].strip()
            if token:
                session_id = token
    if session_id and session_id in sessions:
        return sessions[session_id]
    return None


def create_session(user_id: int, username: str, email: str = None):
    session_id = f"session_{user_id}_{datetime.now().timestamp()}"
    sessions[session_id] = {
        "user_id": user_id,
        "username": username,
        "email": email,
        "created_at": datetime.now(),
    }
    return session_id


def get_user_services(user_id: int):
    """Get the first Gmail+Tasks service pair for a user (backward compat)."""
    db = SessionLocal()
    try:
        tokens = get_all_gmail_tokens(db, user_id)
        if not tokens:
            return None, None
        token = tokens[0]
        gmail_service = GmailService.from_user_token({
            'access_token': token.access_token,
            'refresh_token': token.refresh_token,
        })
        tasks_service = GoogleTasksService.from_user_token({
            'access_token': token.access_token,
            'refresh_token': token.refresh_token,
        })
        return gmail_service, tasks_service
    finally:
        db.close()


def get_all_user_services(user_id: int):
    """Get a list of (GmailService, GoogleTasksService, email_account) for all connected accounts."""
    db = SessionLocal()
    try:
        tokens = get_all_gmail_tokens(db, user_id)
        services = []
        for token in tokens:
            try:
                gmail_service = GmailService.from_user_token({
                    'access_token': token.access_token,
                    'refresh_token': token.refresh_token,
                })
                tasks_service = GoogleTasksService.from_user_token({
                    'access_token': token.access_token,
                    'refresh_token': token.refresh_token,
                })
                services.append((gmail_service, tasks_service, token.email_account, token.id))
            except Exception as e:
                from app.config import logger
                logger.error(f"Failed to create service for token {token.id}: {e}")
        return services
    finally:
        db.close()
