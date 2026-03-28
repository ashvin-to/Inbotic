#!/usr/bin/env python3
"""
Inbotic Web Interface - Gmail-First Multi-User System
A web interface that starts with Gmail OAuth2, then handles user registration
"""
import os
import sys
import logging
import json
import re
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import asyncio
from pathlib import Path
from dotenv import load_dotenv

from fastapi import FastAPI, Request, HTTPException, Depends, Form, Cookie, Response, Body, File, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
from urllib.parse import urlencode
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
# Load environment variables
load_dotenv()

# Import our services
from database import get_db, create_tables, SessionLocal, User, Email, Task, GmailToken, ChatHistory
from user_service import create_user, authenticate_user, get_user_by_username, save_gmail_token, get_gmail_token
from auth import create_access_token, verify_token, get_password_hash
from gmail_service import GmailService
from google_tasks_service import GoogleTasksService
from google_oauth_config import resolve_google_oauth_client_config
import pickle
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import random
import string

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('inbox_agent.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Inbotic",
    description="Gmail-first multi-user web interface for email to tasks automation",
    version="3.0.0"
)
# Initialize Rate Limiter
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Add Middleware
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    TrustedHostMiddleware, 
    allowed_hosts=["localhost", "127.0.0.1", "0.0.0.0"]
)

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173", 
        "http://127.0.0.1:5173",
        os.getenv("FRONTEND_URL", "").rstrip("/")
    ] if os.getenv("FRONTEND_URL") else ["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Initialize database
create_tables()

# Session management
sessions = {}
auto_process_task = None
auto_process_running = False


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _is_production_deployment() -> bool:
    # Treat common hosting envs as production defaults.
    return any([
        _env_bool("INBOTIC_PRODUCTION", False),
        bool(os.getenv("VERCEL")),
        bool(os.getenv("NETLIFY")),
    ])


def _manual_oauth_allowed() -> bool:
    # Default: enabled for local/dev, disabled for production/hosted deployments.
    manual_default = not _is_production_deployment()
    return _env_bool("INBOTIC_ALLOW_MANUAL_OAUTH", manual_default)


def _post_auth_redirect_url() -> str:
    """Return where users should land after OAuth callback succeeds."""
    frontend_url = (os.getenv("FRONTEND_URL") or "").strip()
    if frontend_url:
        return frontend_url.rstrip("/") + "/"
    return "/"


def _has_shared_oauth_credentials() -> bool:
    client_id, client_secret = resolve_google_oauth_client_config()
    return bool(client_id and client_secret)


def get_current_user_from_session(request: Request):
    """Get current user from session cookie"""
    session_id = request.cookies.get("session_id")
    if session_id and session_id in sessions:
        return sessions[session_id]
    return None

def create_session(user_id: int, username: str, email: str = None):
    """Create a new session"""
    session_id = f"session_{user_id}_{datetime.now().timestamp()}"
    sessions[session_id] = {
        "user_id": user_id,
        "username": username,
        "email": email,
        "created_at": datetime.now()
    }
    return session_id

def get_user_services(user_id: int):
    """Get Gmail and Tasks services for a user"""
    db = SessionLocal()
    try:
        gmail_token = get_gmail_token(db, user_id)
        if not gmail_token:
            return None, None

        # Create Gmail service
        gmail_service = GmailService.from_user_token({
            'access_token': gmail_token.access_token,
            'refresh_token': gmail_token.refresh_token
        })

        # Create Tasks service (reuse same credentials)
        tasks_service = GoogleTasksService.from_user_token({
            'access_token': gmail_token.access_token,
            'refresh_token': gmail_token.refresh_token
        })

        return gmail_service, tasks_service
    finally:
        db.close()


def _list_users_with_gmail_tokens() -> List[User]:
    """Return users who have connected Gmail tokens."""
    db = SessionLocal()
    try:
        return (
            db.query(User)
            .join(GmailToken, GmailToken.user_id == User.id)
            .distinct(User.id)
            .all()
        )
    finally:
        db.close()


def _process_user_emails_once(
    user_id: int,
    username: str,
    days_back: int,
    max_emails: int,
    pre_reminder_days: int,
    pre_reminder_hours: int,
    max_days_ahead: int,
) -> Dict[str, int]:
    """Process recent emails for one user and create deadline tasks."""
    gmail_svc, tasks_svc = get_user_services(user_id)
    if not gmail_svc or not tasks_svc:
        return {"processed": 0, "total": 0}

    emails = gmail_svc.get_recent_emails(max_results=max_emails, days_back=days_back)
    if not emails:
        return {"processed": 0, "total": 0}

    task_list = tasks_svc.get_or_create_task_list(f"Inbotic - {username}")
    if not task_list:
        return {"processed": 0, "total": len(emails)}

    processed_count = 0
    task_list_id = task_list['id']
    
    db = SessionLocal()
    try:
        for email in emails:
            email_id = email.get('id')
            if not email_id:
                continue
                
            # 1. Check if email was already processed in our DB
            existing_email = db.query(Email).filter(
                Email.user_id == user_id,
                Email.gmail_message_id == email_id
            ).first()
            
            if existing_email and existing_email.processed:
                logger.debug(f"Email {email_id} already processed for {username}; skipping.")
                continue
            
            # If it exists but not processed, we'll try now.
            # If it doesn't exist, we'll create it now.
            if not existing_email:
                existing_email = Email(
                    user_id=user_id,
                    gmail_message_id=email_id,
                    subject=email.get('subject', 'No Subject'),
                    sender=email.get('sender', 'Unknown'),
                    body=email.get('body', ''),
                    received_at=datetime.now(), # Approximate if parsing fails
                    processed=False
                )
                db.add(existing_email)
                db.commit()
                db.refresh(existing_email)

            try:
                tasks = tasks_svc.create_tasks_from_email(
                    task_list_id=task_list_id,
                    email_data=email,
                    extract_deadlines=True,
                    max_days_ahead=max_days_ahead,
                    default_due_time_utc="09:00:00.000Z",
                    create_action_tasks=False,
                    pre_reminder_days=pre_reminder_days,
                    pre_reminder_hours=pre_reminder_hours,
                    create_pre_reminder=True,
                    dedupe=True,
                )
                
                # Mark as processed in our DB regardless of whether tasks were created
                # (if no tasks found, we don't want to keep checking every time)
                existing_email.processed = True
                db.commit()
                
                is_dedupe = tasks and len(tasks) == 1 and tasks[0].get('dedupe')
                if tasks and not is_dedupe:
                    processed_count += 1
                    
            except Exception as e:
                logger.error(f"Error processing email {email_id} for user {username}: {e}")
                # Don't mark as processed on error so we can retry
                db.rollback()

    finally:
        db.close()

    return {"processed": processed_count, "total": len(emails)}


def _run_auto_process_once():
    """Process new emails for all connected users once."""
    days_back = int(os.getenv("INBOTIC_AUTO_PROCESS_DAYS_BACK", "1"))
    max_emails = int(os.getenv("INBOTIC_AUTO_PROCESS_MAX_EMAILS", "20"))
    pre_reminder_days = int(os.getenv("INBOTIC_AUTO_PROCESS_PRE_REMINDER_DAYS", "1"))
    pre_reminder_hours = int(os.getenv("INBOTIC_AUTO_PROCESS_PRE_REMINDER_HOURS", "0"))
    max_days_ahead = int(os.getenv("INBOTIC_AUTO_PROCESS_MAX_DAYS_AHEAD", "60"))

    users = _list_users_with_gmail_tokens()
    if not users:
        logger.info("Auto process: no users with Gmail tokens found")
        return

    total_users = 0
    total_emails = 0
    total_created = 0
    for u in users:
        total_users += 1
        result = _process_user_emails_once(
            user_id=u.id,
            username=u.username,
            days_back=days_back,
            max_emails=max_emails,
            pre_reminder_days=pre_reminder_days,
            pre_reminder_hours=pre_reminder_hours,
            max_days_ahead=max_days_ahead,
        )
        total_created += result["processed"]
        total_emails += result["total"]

    logger.info(
        f"Auto process done: users={total_users}, emails_scanned={total_emails}, emails_created={total_created}"
    )


async def _auto_process_loop():
    """Background loop: periodically process newly arrived emails."""
    global auto_process_running
    interval_seconds = max(30, int(os.getenv("INBOTIC_AUTO_PROCESS_INTERVAL_SECONDS", "120")))

    while auto_process_running:
        try:
            await asyncio.to_thread(_run_auto_process_once)
        except Exception as e:
            logger.error(f"Auto process loop error: {e}")
        await asyncio.sleep(interval_seconds)


@app.on_event("startup")
async def startup_auto_process():
    """Start optional background processing for new mail."""
    global auto_process_task, auto_process_running
    enabled = _env_bool("INBOTIC_AUTO_PROCESS_NEW_MAIL", False)
    if not enabled:
        logger.info("Auto process disabled (INBOTIC_AUTO_PROCESS_NEW_MAIL=false)")
        return
    if auto_process_task and not auto_process_task.done():
        return

    auto_process_running = True
    auto_process_task = asyncio.create_task(_auto_process_loop())
    logger.info("Auto process enabled: background new-mail polling started")


@app.on_event("shutdown")
async def shutdown_auto_process():
    """Stop optional background processing task."""
    global auto_process_task, auto_process_running
    auto_process_running = False
    if auto_process_task:
        auto_process_task.cancel()
        try:
            await auto_process_task
        except asyncio.CancelledError:
            pass
        auto_process_task = None

@app.get("/")
async def root(request: Request):
    user = get_current_user_from_session(request)
    if user:
        return JSONResponse({
            "message": f"Inbotic API is running. Hello {user['username']}!",
            "status": "authenticated",
            "frontend": os.getenv("FRONTEND_URL", "http://localhost:5173")
        })
    return JSONResponse({
        "message": "Inbotic API is running. Please connect via Gmail.",
        "status": "guest",
        "auth_url": "/auth/gmail"
    })

@app.get("/auth/gmail")
async def auth_gmail(request: Request, mode: str = None):
    """Initiate Gmail OAuth2 authentication"""
    allow_manual = _manual_oauth_allowed()
    shared_available = _has_shared_oauth_credentials()

    if mode not in {"shared", "manual"}:
        if shared_available:
            mode = "shared"
        elif allow_manual:
            return RedirectResponse("/setup/google-credentials", status_code=302)
        else:
            return JSONResponse({"error": "OAuth not configured. Set CLIENT_ID/CLIENT_SECRET."}, status_code=500)

    if mode == "manual":
        if not allow_manual:
            return JSONResponse({"error": "Manual setup disabled"}, status_code=403)
        return RedirectResponse("/setup/google-credentials", status_code=302)

    if mode == "shared" and not shared_available:
        return RedirectResponse("/setup/google-credentials", status_code=302)

    import uuid
    temp_state = str(uuid.uuid4())
    sessions[temp_state] = {"temp_state": True, "created_at": datetime.now()}

    client_id, _ = resolve_google_oauth_client_config()
    redirect_uri = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/callback")
    if not client_id:
        return RedirectResponse("/setup/google-credentials", status_code=302)
    scopes = [
        'https://www.googleapis.com/auth/gmail.readonly',
        'https://www.googleapis.com/auth/tasks'
    ]

    params = {
        'response_type': 'code',
        'client_id': client_id,
        'redirect_uri': redirect_uri,
        'scope': ' '.join(scopes),
        'prompt': 'consent',
        'access_type': 'offline',
        'state': temp_state
    }

    auth_url = f"https://accounts.google.com/o/oauth2/auth?{urlencode(params)}"
    return RedirectResponse(auth_url)


@app.get("/setup/google-credentials")
async def setup_google_credentials_page():
    return JSONResponse({"message": "Please POST to /setup/google-credentials with credentials"})


@app.post("/setup/google-credentials")
async def setup_google_credentials(
    credentials_file: UploadFile = File(None),
    client_id: str = Form(""),
    client_secret: str = Form(""),
):
    """Save Google OAuth credentials."""
    client_id = (client_id or "").strip()
    client_secret = (client_secret or "").strip()

    if credentials_file and credentials_file.filename:
        try:
            raw_bytes = await credentials_file.read()
            payload = json.loads(raw_bytes.decode("utf-8"))
            secrets_dir = Path(".secrets")
            secrets_dir.mkdir(parents=True, exist_ok=True)
            output_path = secrets_dir / "google-credentials.json"
            output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            os.environ["GOOGLE_CREDENTIALS_PATH"] = str(output_path)
        except Exception as e:
            return JSONResponse({"error": f"Could not read JSON: {e}"}, status_code=400)

    if not client_id or not client_secret:
        return JSONResponse({"error": "Missing credentials"}, status_code=400)

    os.environ["CLIENT_ID"] = client_id
    os.environ["CLIENT_SECRET"] = client_secret
    return RedirectResponse("/auth/gmail?mode=shared", status_code=302)

@app.get("/auth/callback")
async def auth_callback(code: str = None, state: str = None, error: str = None):
    """Handle OAuth2 callback"""
    if error:
        return JSONResponse({"error": error}, status_code=400)
    if not code or not state:
        return JSONResponse({"error": "Missing code or state"}, status_code=400)

    if state in sessions and sessions[state].get("temp_state"):
        return await handle_gmail_first_auth(code, state)
    return RedirectResponse("/auth/gmail", status_code=302)

async def handle_gmail_first_auth(code: str, temp_state: str):
    """Handle Gmail-first authentication and user registration"""
    try:
        token_url = "https://oauth2.googleapis.com/token"
        client_id, client_secret = resolve_google_oauth_client_config()
        redirect_uri = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/callback")

        if not client_id or not client_secret:
            return JSONResponse({"error": "Configuration error"}, status_code=500)

        data = {
            'code': code,
            'client_id': client_id,
            'client_secret': client_secret,
            'redirect_uri': redirect_uri,
            'grant_type': 'authorization_code'
        }

        import requests
        response = requests.post(token_url, data=data)
        response.raise_for_status()

        tokens = response.json()
        gmail_service = GmailService.from_user_token(tokens)
        profile = gmail_service.service.users().getProfile(userId='me').execute()
        user_email = profile['emailAddress']

        db = SessionLocal()
        try:
            existing_user = db.query(User).filter(User.email == user_email).first()
            if existing_user:
                save_gmail_token(db, existing_user.id, tokens)
                session_id = create_session(existing_user.id, existing_user.username, user_email)
                response_redirect = RedirectResponse(_post_auth_redirect_url(), status_code=302)
                response_redirect.set_cookie(key="session_id", value=session_id, max_age=86400, httponly=True, samesite="lax")
                return response_redirect
            else:
                base_username = user_email.split("@")[0]
                username = base_username
                suffix = 1
                while db.query(User).filter(User.username == username).first() is not None:
                    suffix += 1
                    username = f"{base_username}{suffix}"

                random_password = __import__("secrets").token_urlsafe(12)
                new_user = User(email=user_email, username=username, hashed_password=get_password_hash(random_password))
                db.add(new_user)
                db.commit()
                db.refresh(new_user)
                save_gmail_token(db, new_user.id, tokens)
                session_id = create_session(new_user.id, new_user.username, user_email)
                response_redirect = RedirectResponse(_post_auth_redirect_url(), status_code=302)
                response_redirect.set_cookie(key="session_id", value=session_id, max_age=86400, httponly=True, samesite="lax")
                return response_redirect
        finally:
            db.close()
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/register")
@app.post("/api/register")
async def register(request: Request):
    return JSONResponse({"error": "Manual registration disabled. Please use Gmail login."}, status_code=401)

@app.post("/login")
@app.post("/api/login")
async def login(request: Request):
    return JSONResponse({"error": "Manual login disabled. Please use Gmail login."}, status_code=401)

@app.get("/logout")
async def logout(response: Response):
    redirect_resp = RedirectResponse("/", status_code=302)
    redirect_resp.delete_cookie(key="session_id")
    return redirect_resp

@app.post("/process-emails")
@app.post("/api/process-emails")
async def process_emails(
    request: Request,
    days_back: int = Form(7),
    max_emails: int = Form(10),
    pre_reminder_days: int = Form(1),
    pre_reminder_hours: int = Form(0),
    max_days_ahead: int = Form(60)
):
    user = get_current_user_from_session(request)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    gmail_svc, tasks_svc = get_user_services(user["user_id"])
    if not gmail_svc or not tasks_svc:
        return JSONResponse({"error": "Gmail not connected"}, status_code=400)

    try:
        result = _process_user_emails_once(
            user_id=user["user_id"],
            username=user["username"],
            days_back=days_back,
            max_emails=max_emails,
            pre_reminder_days=pre_reminder_days,
            pre_reminder_hours=pre_reminder_hours,
            max_days_ahead=max_days_ahead,
        )
        
        message = f"Successfully processed {result['processed']} out of {result['total']} emails"
        return JSONResponse({
            "message": message,
            "processed_count": result['processed'],
            "total_emails": result['total']
        })

    except Exception as e:
        logger.error(f"Error processing emails: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

    return JSONResponse({"error": "AI Review is disabled."}, status_code=404)

# Removed Jinja2 routes: /, /emails, /profile to support React frontend
# These paths should be handled by the frontend router, with data fetched from API endpoints.

@app.post("/profile/update-username")
@app.post("/api/profile/update-username")
async def update_username(request: Request, new_username: str = Form(...)):
    """Allow a logged-in user to change their username"""
    user_session = get_current_user_from_session(request)
    if not user_session:
        return RedirectResponse("/auth/gmail", status_code=302)

    new_username = new_username.strip()
    # Basic validation
    import re
    if len(new_username) < 3 or len(new_username) > 30 or not re.match(r"^[A-Za-z0-9_.-]+$", new_username):
        return RedirectResponse("/profile?error=Invalid+username+format", status_code=302)

    db = SessionLocal()
    try:
        # Check uniqueness
        existing = db.query(User).filter(User.username == new_username).first()
        if existing and existing.id != user_session["user_id"]:
            return RedirectResponse("/profile?error=Username+already+taken", status_code=302)

        db_user = db.query(User).filter(User.id == user_session["user_id"]).first()
        if not db_user:
            return RedirectResponse("/login", status_code=302)

        old_username = db_user.username
        db_user.username = new_username
        db.commit()

        # Update session username
        session_id = request.cookies.get("session_id")
        if session_id and session_id in sessions:
            sessions[session_id]["username"] = new_username

        if "application/json" in request.headers.get("accept", ""):
            return JSONResponse({"message": "Username updated", "username": new_username})
        return RedirectResponse("/profile?message=Username+updated", status_code=302)
    except Exception as e:
        logger.error(f"Error updating username: {e}")
        db.rollback()
        if "application/json" in request.headers.get("accept", ""):
            return JSONResponse({"error": "Failed to update username"}, status_code=500)
        return RedirectResponse("/profile?error=Failed+to+update+username", status_code=302)
    finally:
        db.close()

@app.post("/profile/update-password")
@app.post("/api/profile/update-password")
async def update_password(request: Request, new_password: str = Form(...), confirm_password: str = Form(...)):
    """Allow a logged-in user to set or change their password.

    For simplicity and to support Gmail-connected users who don't know a current password,
    this does not require the current password while the user is already authenticated.
    """
    user_session = get_current_user_from_session(request)
    if not user_session:
        return RedirectResponse("/login", status_code=302)

    if new_password != confirm_password:
        return RedirectResponse("/profile?error=Passwords+do+not+match", status_code=302)
    if len(new_password) < 6:
        return RedirectResponse("/profile?error=Password+must+be+at+least+6+characters", status_code=302)

    db = SessionLocal()
    try:
        db_user = db.query(User).filter(User.id == user_session["user_id"]).first()
        if not db_user:
            return RedirectResponse("/login", status_code=302)

        # Hash and save new password
        hashed = get_password_hash(new_password)
        db_user.hashed_password = hashed
        db.commit()

        if "application/json" in request.headers.get("accept", ""):
            return JSONResponse({"message": "Password updated"})
        return RedirectResponse("/profile?message=Password+updated", status_code=302)
    except Exception as e:
        logger.error(f"Error updating password: {e}")
        db.rollback()
        if "application/json" in request.headers.get("accept", ""):
            return JSONResponse({"error": "Failed to update password"}, status_code=500)
        return RedirectResponse("/profile?error=Failed+to+update+password", status_code=302)
    finally:
        db.close()

@app.post("/profile/update-photo")
@app.post("/api/profile/update-photo")
async def update_photo(request: Request, file: UploadFile = File(...)):
    """Allow a logged-in user to upload a profile photo"""
    user_session = get_current_user_from_session(request)
    if not user_session:
        if "application/json" in request.headers.get("accept", ""):
            return JSONResponse({"error": "Not authenticated"}, status_code=401)
        return RedirectResponse("/login", status_code=302)

    # Validate file type and size (max 5MB)
    if not file.content_type or not file.content_type.startswith("image/"):
        if "application/json" in request.headers.get("accept", ""):
            return JSONResponse({"error": "Only image files are allowed"}, status_code=400)
        return RedirectResponse("/profile?error=Invalid+file+type", status_code=302)
    
    # Read file content to check size
    file_content = await file.read()
    if len(file_content) > 5 * 1024 * 1024:  # 5MB max
        if "application/json" in request.headers.get("accept", ""):
            return JSONResponse({"error": "File size too large. Maximum 5MB allowed."}, status_code=400)
        return RedirectResponse("/profile?error=File+too+large", status_code=302)

    # Create uploads directory if it doesn't exist
    upload_dir = "static/uploads"
    os.makedirs(upload_dir, exist_ok=True)

    # Generate unique filename with user ID and timestamp
    import uuid
    from datetime import datetime
    file_extension = os.path.splitext(file.filename)[1].lower()
    filename = f"{user_session['user_id']}_{int(datetime.now().timestamp())}{file_extension}"
    file_path = os.path.join(upload_dir, filename)

    try:
        # Save the file
        with open(file_path, "wb") as buffer:
            buffer.write(file_content)
    except Exception as e:
        logger.error(f"Error saving file: {e}")
        if "application/json" in request.headers.get("accept", ""):
            return JSONResponse({"error": "Failed to save file"}, status_code=500)
        return RedirectResponse("/profile?error=Failed+to+save+file", status_code=302)

    db = SessionLocal()
    try:
        db_user = db.query(User).filter(User.id == user_session["user_id"]).first()
        if not db_user:
            if "application/json" in request.headers.get("accept", ""):
                return JSONResponse({"error": "User not found"}, status_code=404)
            return RedirectResponse("/login", status_code=302)

        # Store relative path for serving
        profile_photo_path = f"/static/uploads/{filename}"
        
        # Update user profile photo path in database
        db_user.profile_photo = profile_photo_path
        db.commit()
        db.refresh(db_user)

        # Update session with new photo
        if user_session:
            user_session["profile_photo"] = profile_photo_path

        # Return the full URL for the frontend
        base_url = str(request.base_url).rstrip('/')
        full_photo_url = f"{base_url}{profile_photo_path}"

        if "application/json" in request.headers.get("accept", ""):
            return JSONResponse({
                "message": "Profile photo updated",
                "profile_photo": profile_photo_path,
                "full_photo_url": full_photo_url
            })
            
        return RedirectResponse("/profile?message=Profile+photo+updated", status_code=302)
    except Exception as e:
        logger.error(f"Error updating profile photo: {e}")
        db.rollback()
        # Clean up the uploaded file if database update failed
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception as cleanup_error:
            logger.error(f"Error cleaning up file: {cleanup_error}")
            
        if "application/json" in request.headers.get("accept", ""):
            return JSONResponse({"error": "Failed to update profile photo"}, status_code=500)
        return RedirectResponse("/profile?error=Failed+to+update+profile+photo", status_code=302)
    finally:
        db.close()

# Forgot Password Endpoints

@app.post("/api/forgot-password")
async def forgot_password(request: Request, email: str = Form(...)):
    """Initiate password reset flow"""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            # Don't reveal if user exists
            return JSONResponse({"message": "If an account exists, an OTP has been sent."})

        # Generate OTP
        otp = ''.join(random.choices(string.digits, k=6))
        user.reset_token = otp
        user.reset_token_expires = datetime.utcnow() + timedelta(minutes=15)
        db.commit()

        # Send Email
        smtp_email = os.getenv("SMTP_EMAIL")
        smtp_password = os.getenv("SMTP_PASSWORD")
        smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
        smtp_port = int(os.getenv("SMTP_PORT", "587"))

        if smtp_email and smtp_password:
            try:
                msg = MIMEMultipart()
                msg['From'] = smtp_email
                msg['To'] = email
                msg['Subject'] = "Inbotic - Password Reset OTP"

                body = f"Your OTP for password reset is: {otp}\n\nThis OTP is valid for 15 minutes."
                msg.attach(MIMEText(body, 'plain'))

                server = smtplib.SMTP(smtp_server, smtp_port)
                server.starttls()
                server.login(smtp_email, smtp_password)
                text = msg.as_string()
                server.sendmail(smtp_email, email, text)
                server.quit()
                logger.info(f"Sent OTP to {email}")
            except Exception as e:
                logger.error(f"Failed to send email: {e}")
                # Fallback logging for testing
                logger.info(f"DEV MODE OTP for {email}: {otp}")
        else:
            logger.warning("SMTP not configured. Logging OTP.")
            logger.info(f"DEV MODE OTP for {email}: {otp}")

        return JSONResponse({"message": "If an account exists, an OTP has been sent."})
    except Exception as e:
        logger.error(f"Error in forgot password: {e}")
        return JSONResponse({"error": "An error occurred"}, status_code=500)
    finally:
        db.close()

@app.post("/api/reset-password")
async def reset_password(
    request: Request, 
    email: str = Form(...), 
    otp: str = Form(...), 
    new_password: str = Form(...)
):
    """Reset password using OTP"""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            return JSONResponse({"error": "Invalid request"}, status_code=400)

        # Check OTP and Expiry
        if not user.reset_token or user.reset_token != otp:
            return JSONResponse({"error": "Invalid OTP"}, status_code=400)
        
        if user.reset_token_expires < datetime.utcnow():
            return JSONResponse({"error": "OTP expired"}, status_code=400)

        # Update Password
        hashed = get_password_hash(new_password)
        user.hashed_password = hashed
        user.reset_token = None
        user.reset_token_expires = None
        db.commit()

        return JSONResponse({"success": True, "message": "Password reset successfully"})
    except Exception as e:
        logger.error(f"Error resetting password: {e}")
        return JSONResponse({"error": "Failed to reset password"}, status_code=500)
    finally:
        db.close()


@app.get("/debug-session", response_class=HTMLResponse)
async def debug_session(request: Request):
    """Debug endpoint to check session and cookies"""
    session_id = request.cookies.get("session_id")
    user = get_current_user_from_session(request)

    debug_info = {
        "session_id": session_id,
        "user": user,
        "all_sessions": list(sessions.keys()),
        "all_cookies": dict(request.cookies)
    }

    return HTMLResponse(f"""
    <h1>Session Debug Info</h1>
    <pre>{debug_info}</pre>
    <p><a href="/">Go to Home</a></p>
    <p><a href="/auth/gmail">Go to Login</a></p>
    """)

if __name__ == "__main__":
    uvicorn.run("web_app:app", host="0.0.0.0", port=8000, reload=True)

# API Endpoints

@app.get("/api/me")
async def api_me(request: Request):
    user = get_current_user_from_session(request)
    if not user:
        return JSONResponse({"authenticated": False}, status_code=401)
    
    # Make user dict JSON serializable
    user_data = user.copy()
    if "created_at" in user_data and hasattr(user_data["created_at"], "isoformat"):
        user_data["created_at"] = user_data["created_at"].isoformat()
        
    # Check for connected Gmail tokens
    db = SessionLocal()
    try:
        has_tokens = db.query(GmailToken).filter(GmailToken.user_id == user["user_id"]).first() is not None
        user_data["gmail_tokens_connected"] = has_tokens
    finally:
        db.close()

    return JSONResponse({"authenticated": True, "user": user_data})


@app.post("/api/logout")
async def api_logout():
    resp = JSONResponse({"success": True})
    resp.delete_cookie(key="session_id")
    return resp

@app.get("/api/dashboard")
async def api_dashboard(request: Request):
    user = get_current_user_from_session(request)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
        
    gmail_svc, tasks_svc = get_user_services(user["user_id"])
    
    # Make user dict JSON serializable
    user_data = user.copy()
    if "created_at" in user_data and hasattr(user_data["created_at"], "isoformat"):
        user_data["created_at"] = user_data["created_at"].isoformat()

    data = {
        "user": user_data,
        "gmail_connected": False,
        "ia_tasks_count": 0,
        "task_lists": [],
        "emails_this_week": 0,
        "pending_tasks": 0
    }
    
    if gmail_svc and tasks_svc:
        data["gmail_connected"] = True
        try:
            task_lists = tasks_svc.get_task_lists()
            data["task_lists"] = task_lists
            
            ia_title = f"Inbotic - {user['username']}"
            ia_list = next((tl for tl in task_lists if tl.get('title') == ia_title), None)
            if ia_list:
                ia_tasks = tasks_svc.get_tasks(ia_list['id'], max_results=50)
                data["ia_tasks_count"] = len(ia_tasks or [])
                
                # Count pending tasks only from IA list (faster)
                pending_count = sum(1 for t in (ia_tasks or []) if t.get('status') == 'needsAction')
                data["pending_tasks"] = pending_count
            
        except Exception as e:
            error_str = str(e)
            if "invalid_grant" in error_str or "Token has been expired" in error_str:
                logger.warning(f"Token expired for user {user['username']}: {e}")
                data["needs_reauth"] = True
                data["error"] = "Your Google connection has expired. Please reconnect."
            else:
                logger.error(f"Error loading dashboard data: {e}")
        
        # Count emails this week (limit to 20 for speed)
        if not data.get("needs_reauth"):
            try:
                recent_emails = gmail_svc.get_recent_emails(max_results=20, days_back=7)
                data["emails_this_week"] = len(recent_emails) if recent_emails else 0
            except Exception as e:
                error_str = str(e)
                if "invalid_grant" in error_str or "Token has been expired" in error_str:
                    data["needs_reauth"] = True
                    data["error"] = "Your Google connection has expired. Please reconnect."
                logger.error(f"Error counting emails: {e}")
            
    return JSONResponse(data)

@app.post("/api/register")
@limiter.limit("5/minute")
async def api_register(
    request: Request,
    response: Response,
    data: dict = Body(...)
):
    return JSONResponse({"error": "Manual registration disabled. Please use Gmail login."}, status_code=401)

    db = SessionLocal()
    try:
        existing_user = db.query(User).filter(
            (User.email == email) | (User.username == username)
        ).first()

        if existing_user:
            return JSONResponse({"error": "Username or email already exists"}, status_code=400)

        hashed_password = get_password_hash(password)
        new_user = User(
            email=email,
            username=username,
            hashed_password=hashed_password
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)

        session_id = create_session(new_user.id, new_user.username, email)
        
        resp = JSONResponse({"success": True, "user": {"username": new_user.username, "email": new_user.email}})
        resp.set_cookie(
            key="session_id",
            value=session_id,
            max_age=86400,
            httponly=True,
            samesite="lax"
        )
        return resp
    finally:
        db.close()
@app.get("/api/emails")
async def api_emails(request: Request, days_back: int = 7):
    user = get_current_user_from_session(request)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    gmail_svc, tasks_svc = get_user_services(user["user_id"])
    
    db = SessionLocal()
    try:
        # 1. Try to get from local DB first (fast load)
        db_emails = db.query(Email).filter(Email.user_id == user["user_id"]).order_by(Email.received_at.desc()).limit(50).all()
        
        if db_emails and len(db_emails) > 0:
            # Convert to dicts
            results = []
            for e in db_emails:
                results.append({
                    "id": e.gmail_message_id,
                    "subject": e.subject,
                    "sender": e.sender,
                    "body": e.body,
                    "date": e.received_at.strftime("%Y-%m-%d") if e.received_at else "",
                    "processed": e.processed,
                    "extracted_data": e.extracted_data
                })
            return JSONResponse({"emails": results})

        # 2. If no local data, fetch from Google (slow but necessary first time)
        if not gmail_svc:
            return JSONResponse({"emails": []})

        emails = gmail_svc.get_recent_emails(max_results=20, days_back=days_back)
        
        # Save to DB for next time
        for email_data in emails:
            # Check if exists
            exists = db.query(Email).filter(
                Email.user_id == user["user_id"], 
                Email.gmail_message_id == email_data['id']
            ).first()
            
            if not exists:
                new_email = Email(
                    user_id=user["user_id"],
                    gmail_message_id=email_data['id'],
                    subject=email_data.get('subject', 'No Subject'),
                    sender=email_data.get('sender', 'Unknown'),
                    body=email_data.get('body', ''),
                    # Parse date if possible, else now
                    received_at=datetime.now(), 
                    processed=False
                )
                db.add(new_email)
        
        db.commit()
        return JSONResponse({"emails": emails})
        
    except Exception as e:
        logger.error(f"Error fetching emails: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)
    finally:
        db.close()

@app.get("/api/tasks")
async def api_tasks(request: Request, refresh: bool = False):
    user = get_current_user_from_session(request)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    gmail_svc, tasks_svc = get_user_services(user["user_id"])
    if not tasks_svc:
        return JSONResponse({"task_lists": [], "tasks": []})

    def _normalize_time_hms_for_api(time_value: str) -> str:
        if not time_value:
            return ""
        text = str(time_value).strip()
        if 'T' in text:
            text = text.split('T', 1)[1]
        text = text.replace('Z', '')
        text = text.split('.', 1)[0]
        # Handle timezone offsets if they exist.
        text = re.sub(r'([+-]\d{2}:?\d{2})$', '', text).strip()
        parts = text.split(':')
        if len(parts) == 2:
            text = f"{parts[0]}:{parts[1]}:00"
        if re.fullmatch(r'([01]?\d|2[0-3]):([0-5]\d):([0-5]\d)', text):
            h, m, s = text.split(':')
            return f"{int(h):02d}:{int(m):02d}:{int(s):02d}"
        return ""

    db = SessionLocal()
    try:
        # 1. Get task lists (usually fast, 1 API call)
        task_lists = tasks_svc.get_task_lists()
        
        # 2. Try to get tasks from local DB (unless refreshing)
        if not refresh:
            db_tasks = db.query(Task).filter(Task.user_id == user["user_id"]).all()
            
            if db_tasks and len(db_tasks) > 0:
                # Convert to dicts
                all_tasks = []
                local_task_lists = {}
                for t in db_tasks:
                    # Find list title
                    list_title = "Unknown List"
                    for tl in task_lists:
                        if tl['id'] == t.gmail_task_list_id:
                            list_title = tl['title']
                            break

                    if t.gmail_task_list_id:
                        local_task_lists[t.gmail_task_list_id] = {
                            "id": t.gmail_task_list_id,
                            "title": list_title,
                        }

                    due_value = None
                    if t.due_date:
                        date_part = t.due_date.strftime("%Y-%m-%d")
                        time_part = _normalize_time_hms_for_api(t.due_time)
                        if not time_part:
                            # Fallback to datetime component if available.
                            time_part = t.due_date.strftime("%H:%M:%S") if hasattr(t.due_date, "strftime") else "00:00:00"
                        due_value = f"{date_part}T{time_part}.000Z"
                    
                    all_tasks.append({
                        "id": t.gmail_task_id,
                        "title": t.title,
                        "notes": t.description,
                        "due": due_value,
                        "updated": t.updated_at.isoformat() if t.updated_at else None,
                        "status": t.status,
                        "list_id": t.gmail_task_list_id,
                        "list_name": list_title
                    })

                response_task_lists = task_lists if task_lists else list(local_task_lists.values())
                return JSONResponse({"task_lists": response_task_lists, "tasks": all_tasks})
        
        # If refreshing, clear local tasks first
        if refresh:
            db.query(Task).filter(Task.user_id == user["user_id"]).delete()
            db.commit()

        # 3. If no local data, fetch from Google (slow N+1 calls)
        all_tasks = []
        for task_list in task_lists:
            tasks = tasks_svc.get_tasks(task_list['id'], max_results=50)
            for task in tasks:
                task['list_name'] = task_list['title']
                task['list_id'] = task_list['id']
                all_tasks.append(task)
                
                # Save to DB
                exists = db.query(Task).filter(
                    Task.user_id == user["user_id"],
                    Task.gmail_task_id == task['id']
                ).first()
                
                if not exists:
                    # Parse due date and extract time if available
                    due_date = None
                    due_time = None
                    if task.get('due'):
                        try:
                            due_str = task.get('due')
                            if 'T' in due_str:
                                date_part, time_part = due_str.split('T', 1)
                                due_date = datetime.strptime(date_part, "%Y-%m-%d")
                                time_cleaned = time_part.replace('Z', '').split('.')[0]
                                # If Google zeroed it out, try to recover from notes
                                if time_cleaned == "00:00:00":
                                    notes = task.get('notes', '')
                                    # Look for "⏰ Time: HH:MM UTC"
                                    time_match = re.search(r'⏰ Time: (\d{2}:\d{2})', notes)
                                    if time_match:
                                        due_time = f"{time_match.group(1)}:00"
                                    else:
                                        due_time = time_cleaned
                                else:
                                    due_time = time_cleaned
                            else:
                                due_date = datetime.strptime(due_str, "%Y-%m-%d")
                        except Exception as e:
                            logger.debug(f"Failed to parse due date '{task.get('due')}': {e}")
                    
                    # Fallback check for time in notes even if due date is different
                    if not due_time:
                        notes = task.get('notes', '')
                        time_match = re.search(r'⏰ Time: (\d{2}:\d{2})', notes)
                        if time_match:
                            due_time = f"{time_match.group(1)}:00"

                    # Correctly set the recovered time back into the task object for the API response
                    if due_time and task.get('due'):
                         date_part = task['due'].split('T')[0]
                         task['due'] = f"{date_part}T{due_time}.000Z"

                    new_task = Task(
                        user_id=user["user_id"],
                        gmail_task_id=task['id'],
                        gmail_task_list_id=task_list['id'],
                        title=task.get('title', 'Untitled'),
                        description=task.get('notes', ''),
                        status=task.get('status', 'needsAction'),
                        due_date=due_date,
                        due_time=due_time
                    )
                    db.add(new_task)
        
        db.commit()
        return JSONResponse({"task_lists": task_lists, "tasks": all_tasks})
        
    except Exception as e:
        logger.error(f"Error fetching tasks: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)
    finally:
        db.close()

@app.put("/api/tasks/{task_id}")
async def api_update_task(task_id: str, request: Request, data: dict = Body(...)):
    user = get_current_user_from_session(request)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    gmail_svc, tasks_svc = get_user_services(user["user_id"])
    if not tasks_svc:
        return JSONResponse({"error": "Tasks service not connected"}, status_code=400)

    task_list_id = data.get("list_id")
    if not task_list_id:
        return JSONResponse({"error": "Missing task_list_id"}, status_code=400)

    try:
        # Prepare updates
        updates = {}
        if "title" in data:
            updates["title"] = data["title"]
        if "notes" in data:
            updates["notes"] = data["notes"]
        if "status" in data:
            updates["status"] = data["status"]
        if "due" in data:
            updates["due"] = data["due"]  # Expecting YYYY-MM-DD or ISO string

        updated_task = tasks_svc.update_task(task_list_id, task_id, updates)
        if updated_task:
            return JSONResponse({"task": updated_task})
        else:
            return JSONResponse({"error": "Failed to update task"}, status_code=500)
    except Exception as e:
        logger.error(f"Error updating task: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.delete("/api/tasks/{task_id}")
async def api_delete_task(task_id: str, request: Request, list_id: str):
    user = get_current_user_from_session(request)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    gmail_svc, tasks_svc = get_user_services(user["user_id"])
    if not tasks_svc:
        return JSONResponse({"error": "Tasks service not connected"}, status_code=400)

    try:
        # Delete from Google Tasks
        success = tasks_svc.delete_task(list_id, task_id)
        
        if success:
            # Also delete from local DB to prevent ghosting
            db = SessionLocal()
            try:
                db.query(Task).filter(
                    Task.user_id == user["user_id"],
                    Task.gmail_task_id == task_id
                ).delete()
                db.commit()
            except Exception as db_e:
                logger.error(f"Error deleting task from DB: {db_e}")
            finally:
                db.close()
                
            return JSONResponse({"success": True})
        else:
            return JSONResponse({"error": "Failed to delete task"}, status_code=500)
    except Exception as e:
        logger.error(f"Error deleting task: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/api/profile")
async def api_profile(request: Request):
    user_session = get_current_user_from_session(request)
    if not user_session:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    db = SessionLocal()
    try:
        db_user = db.query(User).filter(User.id == user_session["user_id"]).first()
        if not db_user:
            return JSONResponse({"error": "User not found"}, status_code=404)

        profile_user = {
            "username": db_user.username,
            "email": db_user.email,
            "profile_photo": db_user.profile_photo,
            "created_at": db_user.created_at.isoformat() if db_user.created_at else None,
            "updated_at": db_user.updated_at.isoformat() if db_user.updated_at else None,
            "emails_count": len(db_user.emails) if db_user.emails else 0,
            "tasks_count": len(db_user.tasks) if db_user.tasks else 0,
            "gmail_tokens_count": len(db_user.gmail_tokens) if db_user.gmail_tokens else 0,
            "gmail_tokens_connected": bool(db_user.gmail_tokens and len(db_user.gmail_tokens) > 0),
        }
        
        # Calculate days active
        if db_user.created_at and db_user.updated_at:
            days_active = (db_user.updated_at - db_user.created_at).days
        else:
            days_active = 0
        profile_user["days_active"] = days_active

        return JSONResponse({"user": profile_user})
    finally:
        db.close()

@app.post("/api/chat/send")
async def api_chat_send(request: Request):
    """Disable chat entirely"""
    return JSONResponse({"error": "AI Chat is disabled."}, status_code=404)
