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
import hmac
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import asyncio
from pathlib import Path
from dotenv import load_dotenv

from fastapi import FastAPI, Request, HTTPException, Depends, Form, Cookie, Response, Body, File, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
# Load environment variables
load_dotenv()

# Import our services
from database import get_db, create_tables, SessionLocal, User, Email, Task, GmailToken
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


def _build_allowed_hosts() -> List[str]:
    hosts = {
        "localhost",
        "127.0.0.1",
        "0.0.0.0",
    }

    render_url = (os.getenv("RENDER_EXTERNAL_URL") or "").strip()
    if render_url:
        parts = urlsplit(render_url)
        if parts.netloc:
            hosts.add(parts.netloc)

    frontend_url = (os.getenv("FRONTEND_URL") or "").strip()
    if frontend_url:
        parts = urlsplit(frontend_url)
        if parts.netloc:
            hosts.add(parts.netloc)

    extra = (os.getenv("ALLOWED_HOSTS") or "").strip()
    if extra:
        for host in extra.split(","):
            clean = host.strip()
            if clean:
                hosts.add(clean)

    return sorted(hosts)

app.add_middleware(
    TrustedHostMiddleware, 
    allowed_hosts=_build_allowed_hosts()
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


def _build_cors_origins() -> List[str]:
    origins = {
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    }

    frontend_url = (os.getenv("FRONTEND_URL") or "").strip()
    if frontend_url:
        parts = urlsplit(frontend_url)
        if parts.scheme and parts.netloc:
            origins.add(f"{parts.scheme}://{parts.netloc}")

    extra = (os.getenv("CORS_ALLOW_ORIGINS") or "").strip()
    if extra:
        for origin in extra.split(","):
            clean = origin.strip()
            if clean:
                origins.add(clean)

    return sorted(origins)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_build_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files and templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")
templates.env.globals["now"] = datetime.now

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
        bool(os.getenv("RENDER")),
        bool(os.getenv("RENDER_EXTERNAL_URL")),
    ])


def _manual_oauth_allowed() -> bool:
    # Default: enabled for local/dev, disabled for production/hosted deployments.
    manual_default = not _is_production_deployment()
    return _env_bool("INBOTIC_ALLOW_MANUAL_OAUTH", manual_default)


def _oauth_state_secret() -> str:
    return (os.getenv("OAUTH_STATE_SECRET") or os.getenv("SECRET_KEY") or "inbotic-dev-secret").strip()


def _create_oauth_state() -> str:
    ts = int(datetime.utcnow().timestamp())
    nonce = secrets.token_urlsafe(16)
    payload = f"{ts}:{nonce}"
    signature = hmac.new(_oauth_state_secret().encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}:{signature}"


def _is_valid_oauth_state(state: str, *, max_age_seconds: int = 900) -> bool:
    if not state:
        return False

    parts = state.split(":")
    if len(parts) != 3:
        return False

    ts_raw, nonce, signature = parts
    if not ts_raw.isdigit() or not nonce or not signature:
        return False

    payload = f"{ts_raw}:{nonce}"
    expected = hmac.new(_oauth_state_secret().encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        return False

    ts = int(ts_raw)
    age = int(datetime.utcnow().timestamp()) - ts
    return 0 <= age <= max_age_seconds


def _session_cookie_settings() -> Dict[str, Any]:
    default_prod = _is_production_deployment()
    default_samesite = "none" if default_prod else "lax"
    samesite = (os.getenv("SESSION_COOKIE_SAMESITE") or default_samesite).strip().lower()
    if samesite not in {"lax", "strict", "none"}:
        samesite = default_samesite

    secure_default = default_prod or samesite == "none"
    secure = _env_bool("SESSION_COOKIE_SECURE", secure_default)

    return {
        "max_age": 86400,
        "httponly": True,
        "samesite": samesite,
        "secure": secure,
    }


def _set_session_cookie(response: Response, session_id: str) -> None:
    response.set_cookie(
        key="session_id",
        value=session_id,
        **_session_cookie_settings(),
    )


def _delete_session_cookie(response: Response) -> None:
    settings = _session_cookie_settings()
    response.delete_cookie(
        key="session_id",
        httponly=True,
        samesite=settings["samesite"],
        secure=settings["secure"],
    )


def _post_auth_redirect_url(session_id: Optional[str] = None) -> str:
    """Return where users should land after OAuth callback succeeds."""
    frontend_url = (os.getenv("FRONTEND_URL") or "").strip()
    if frontend_url:
        target = frontend_url.rstrip("/") + "/"
        if not session_id:
            return target

        parts = urlsplit(target)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        query["session_id"] = session_id
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
    # Safe fallback for backend-only/Jinja usage.
    return "/"


def _has_shared_oauth_credentials() -> bool:
    client_id, client_secret = resolve_google_oauth_client_config()
    return bool(client_id and client_secret)


def render_oauth_choice_page(shared_available: bool, allow_manual: bool):
    """Render a simple chooser for hosted OAuth vs manual OAuth setup."""
    shared_disabled = "disabled" if not shared_available else ""
    shared_note = "" if shared_available else "<p class='muted' style='color:#b00020;'>Hosted OAuth is not configured on this server yet.</p>"

    manual_card = ""
    if allow_manual:
        manual_card = """
        <div class='card'>
            <h3>Use My Own OAuth Credentials</h3>
            <p>Upload your OAuth JSON or paste Client ID and Client Secret.</p>
            <a class='btn secondary' href='/setup/google-credentials'>Manual Setup</a>
        </div>
        """

    html = f"""
    <html>
        <head>
            <title>Choose Sign-In Method</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 2rem; line-height: 1.5; }}
                .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 1rem; max-width: 900px; }}
                .card {{ border: 1px solid #ddd; border-radius: 10px; padding: 1.25rem; }}
                .btn {{ margin-top: 0.8rem; display: inline-block; text-decoration: none; padding: 0.6rem 1rem; border-radius: 8px; background: #0a66c2; color: #fff; }}
                .btn.secondary {{ background: #444; }}
                .btn[disabled] {{ pointer-events: none; opacity: 0.5; }}
                .muted {{ color: #666; font-size: 0.95rem; }}
            </style>
        </head>
        <body>
            <h1>Choose how to connect Gmail</h1>
            <p class='muted'>You can sign in using hosted OAuth managed by this app, or configure your own Google OAuth credentials.</p>
            <div class='grid'>
                <div class='card'>
                    <h3>Use Hosted OAuth</h3>
                    <p>This is easiest for end users. They just sign in with Google.</p>
                    {shared_note}
                    <a class='btn' href='/auth/gmail?mode=shared' {shared_disabled}>Continue with Hosted OAuth</a>
                </div>
                {manual_card}
            </div>
        </body>
    </html>
    """
    return HTMLResponse(html)


def render_oauth_setup_page(message: str = "", is_error: bool = False):
    """Render a simple browser-based setup page for Google OAuth credentials."""
    status_style = "color:#b00020;" if is_error else "color:#0a7c2f;"
    status_html = f"<p style='{status_style}'>{message}</p>" if message else ""

    html = f"""
    <html>
        <head>
            <title>Inbotic Setup</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 2rem; line-height: 1.5; }}
                .card {{ max-width: 760px; border: 1px solid #ddd; border-radius: 10px; padding: 1.25rem; }}
                .muted {{ color: #666; font-size: 0.95rem; }}
                label {{ font-weight: 600; display: block; margin-top: 1rem; }}
                input[type='file'], input[type='text'] {{ width: 100%; padding: 0.5rem; margin-top: 0.35rem; }}
                button {{ margin-top: 1rem; padding: 0.6rem 1rem; border: 0; border-radius: 8px; background: #0a66c2; color: #fff; cursor: pointer; }}
                code {{ background: #f5f5f5; padding: 0.12rem 0.3rem; border-radius: 4px; }}
            </style>
        </head>
        <body>
            <h1>One-time Google setup</h1>
            <div class='card'>
                <p>Use this page to configure OAuth without editing environment variables manually.</p>
                {status_html}
                <ol>
                    <li>Create OAuth credentials in Google Cloud (see quick steps below).</li>
                    <li>Either upload OAuth JSON or paste Client ID/Client Secret.</li>
                    <li>Click Save, then Connect Gmail.</li>
                </ol>

                <div class='muted'>
                    <p><strong>Quick Google OAuth steps</strong></p>
                    <ol>
                        <li>Open Google Cloud Console and create/select a project.</li>
                        <li>Enable Gmail API and Google Tasks API.</li>
                        <li>Configure OAuth consent screen.</li>
                        <li>Create OAuth Client ID (Web application).</li>
                        <li>Add redirect URI: http://localhost:8000/auth/callback</li>
                        <li>Copy Client ID and Client Secret (or download JSON).</li>
                    </ol>
                </div>

                <form action='/setup/google-credentials' method='post' enctype='multipart/form-data'>
                    <label>Option A: Upload Google OAuth credentials JSON</label>
                    <input type='file' name='credentials_file' accept='.json,application/json' />

                    <p class='muted'>Option B (skip JSON): paste these values directly.</p>
                    <label>Client ID</label>
                    <input type='text' name='client_id' placeholder='your-google-oauth-client-id' />

                    <label>Client Secret</label>
                    <input type='text' name='client_secret' placeholder='your-google-oauth-client-secret' />

                    <button type='submit'>Save and Continue</button>
                </form>

                <p class='muted'>If you upload JSON, it is saved to <code>.secrets/google-credentials.json</code>.</p>
                <p><a href='/auth/gmail'>Back to sign-in options</a></p>
            </div>
        </body>
    </html>
    """
    return HTMLResponse(html)

def get_current_user_from_session(request: Request):
    """Get current user from cookie first, then bearer fallback for cross-domain auth."""
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

    for email in emails:
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
            is_dedupe = tasks and len(tasks) == 1 and tasks[0].get('dedupe')
            if tasks and not is_dedupe:
                processed_count += 1
        except Exception as e:
            logger.error(f"Error processing email {email.get('id', 'unknown')} for user {username}: {e}")

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

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Home page - Gmail-first approach"""
    user = get_current_user_from_session(request)
    context = {
        "request": request,
        "title": "Inbotic - Gmail to Google Tasks"
    }

    if user:
        # User is logged in - show dashboard
        gmail_svc, tasks_svc = get_user_services(user["user_id"])

        if gmail_svc and tasks_svc:
            try:
                # Get user's task lists
                task_lists = tasks_svc.get_task_lists()
                # Count tasks in our app's list only (more meaningful than total lists)
                ia_title = f"Inbotic - {user['username']}"
                ia_tasks_count = 0
                recent_activity = "No recent activity found."

                try:
                    ia_list = next((tl for tl in task_lists if tl.get('title') == ia_title), None)
                    if ia_list:
                        ia_tasks = tasks_svc.get_tasks(ia_list['id'], max_results=200)
                        ia_tasks_count = len(ia_tasks or [])

                        # Get recent tasks for activity feed
                        if ia_tasks:
                            # Sort by updated/created if available, or just take top
                            # Google Tasks API returns in default order (usually custom), so we take top 3
                            recent_tasks = ia_tasks[:3]
                            activity_lines = []
                            for t in recent_tasks:
                                status = "Completed" if t.get('status') == 'completed' else "Created"
                                title = t.get('title', 'Untitled task')
                                activity_lines.append(f"{status}: {title}")

                            if activity_lines:
                                recent_activity = " | ".join(activity_lines)
                    else:
                        ia_tasks_count = 0
                except Exception:
                    ia_tasks_count = 0

                context.update({
                    "authenticated": True,
                    "user": user,
                    "task_lists": task_lists,
                    "ia_tasks_count": ia_tasks_count,
                    "recent_activity": recent_activity,
                })
            except Exception as e:
                error_str = str(e)
                if "invalid_grant" in error_str or "Token has been expired" in error_str:
                    logger.warning(f"Token expired for user {user['username']}: {e}")
                    context["error"] = "Your Google connection has expired. Please reconnect."
                    context["needs_reauth"] = True
                else:
                    logger.error(f"Error loading user dashboard: {e}")
                    context["error"] = "Error loading dashboard"
        else:
            context.update({
                "authenticated": True,
                "user": user,
                "needs_gmail": True
            })
    else:
        # User not logged in - show Gmail-first onboarding
        context["authenticated"] = False
        context["gmail_first"] = True
        context["oauth_shared_available"] = _has_shared_oauth_credentials()
        context["oauth_manual_allowed"] = _manual_oauth_allowed()

    return templates.TemplateResponse("index.html", context)

@app.get("/auth/gmail")
async def auth_gmail(request: Request, mode: str = None):
    """Initiate Gmail OAuth2 authentication (Gmail-first approach)"""
    allow_manual = _manual_oauth_allowed()
    shared_available = _has_shared_oauth_credentials()

    # Let users choose between hosted OAuth and manual setup when both are enabled.
    if mode not in {"shared", "manual"}:
        if shared_available and allow_manual:
            return render_oauth_choice_page(shared_available=True, allow_manual=True)
        if shared_available and not allow_manual:
            mode = "shared"
        if not shared_available:
            if not allow_manual:
                return HTMLResponse(
                    "<h1>OAuth not configured</h1><p>Hosted OAuth credentials are missing and manual setup is disabled on this deployment.</p>",
                    status_code=500,
                )
            return RedirectResponse("/setup/google-credentials", status_code=302)

    if mode == "manual":
        if not allow_manual:
            return HTMLResponse("<h1>Manual setup is disabled</h1>", status_code=403)
        return RedirectResponse("/setup/google-credentials", status_code=302)

    if not shared_available:
        return RedirectResponse("/setup/google-credentials", status_code=302)

    # Signed state token avoids in-memory callback dependency across process restarts.
    temp_state = _create_oauth_state()

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
    """Beginner-friendly setup page for Google OAuth credentials."""
    return render_oauth_setup_page()


@app.post("/setup/google-credentials")
async def setup_google_credentials(
    credentials_file: UploadFile = File(None),
    client_id: str = Form(""),
    client_secret: str = Form(""),
):
    """Save Google OAuth credentials from uploaded JSON or manual inputs."""
    client_id = (client_id or "").strip()
    client_secret = (client_secret or "").strip()

    if credentials_file and credentials_file.filename:
        try:
            raw_bytes = await credentials_file.read()
            payload = json.loads(raw_bytes.decode("utf-8"))

            web_block = payload.get("web") if isinstance(payload, dict) else None
            installed_block = payload.get("installed") if isinstance(payload, dict) else None

            if isinstance(web_block, dict):
                client_id = client_id or (web_block.get("client_id") or "").strip()
                client_secret = client_secret or (web_block.get("client_secret") or "").strip()
            if isinstance(installed_block, dict):
                client_id = client_id or (installed_block.get("client_id") or "").strip()
                client_secret = client_secret or (installed_block.get("client_secret") or "").strip()

            # Also support flat payload shape just in case.
            client_id = client_id or (payload.get("client_id") or "").strip()
            client_secret = client_secret or (payload.get("client_secret") or "").strip()

            secrets_dir = Path(".secrets")
            secrets_dir.mkdir(parents=True, exist_ok=True)
            output_path = secrets_dir / "google-credentials.json"
            output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            os.environ["GOOGLE_CREDENTIALS_PATH"] = str(output_path)
        except Exception as e:
            return render_oauth_setup_page(f"Could not read uploaded JSON: {e}", is_error=True)

    if not client_id or not client_secret:
        return render_oauth_setup_page(
            "Missing client_id/client_secret. Upload a valid OAuth JSON file or fill both fields.",
            is_error=True,
        )

    # Keep values in memory for this run; persisted values can be added in .env if desired.
    os.environ["CLIENT_ID"] = client_id
    os.environ["CLIENT_SECRET"] = client_secret

    # After saving manual credentials, immediately start OAuth consent.
    return RedirectResponse("/auth/gmail?mode=shared", status_code=302)

@app.get("/auth/callback")
async def auth_callback(code: str = None, state: str = None, error: str = None):
    """Handle OAuth2 callback - create/register user"""
    if error:
        return HTMLResponse(f"<h1>Authentication failed</h1><p>Error: {error}</p><p><a href='/'>Try Again</a></p>")

    if not code or not state:
        return HTMLResponse("<h1>Authentication failed</h1><p>Missing authorization code or state</p><p><a href='/'>Try Again</a></p>")

    # Validate signed OAuth state without requiring in-memory state storage.
    if _is_valid_oauth_state(state):
        return await handle_gmail_first_auth(code, state)
    else:
        # Legacy flow - redirect to login
        return RedirectResponse("/login?message=Please+login+first", status_code=302)

async def handle_gmail_first_auth(code: str, temp_state: str):
    """Handle Gmail-first authentication and user registration"""
    try:
        # Exchange code for token
        token_url = "https://oauth2.googleapis.com/token"
        client_id, client_secret = resolve_google_oauth_client_config()
        redirect_uri = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/callback")

        if not client_id or not client_secret:
            return HTMLResponse(
                "<h1>Configuration error</h1><p>Missing Google OAuth credentials. Set CLIENT_ID/CLIENT_SECRET or place your Google credentials JSON at .secrets/google-credentials.json.</p>",
                status_code=500,
            )

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

        # Get user profile from Gmail
        gmail_service = GmailService.from_user_token(tokens)
        profile = gmail_service.service.users().getProfile(userId='me').execute()
        user_email = profile['emailAddress']

        # Check if user already exists
        db = SessionLocal()
        try:
            existing_user = db.query(User).filter(User.email == user_email).first()

            if existing_user:
                # User exists - update their Gmail token and login
                save_gmail_token(db, existing_user.id, tokens)
                session_id = create_session(existing_user.id, existing_user.username, user_email)

                response_redirect = RedirectResponse(_post_auth_redirect_url(session_id=session_id), status_code=302)
                _set_session_cookie(response_redirect, session_id)
                logger.info(f"Existing user {existing_user.username} connected Gmail")
                return response_redirect
            else:
                # Auto-provision a new local user using Gmail identity
                base_username = user_email.split("@")[0]
                username = base_username
                suffix = 1
                while db.query(User).filter(User.username == username).first() is not None:
                    suffix += 1
                    username = f"{base_username}{suffix}"

                random_password = __import__("secrets").token_urlsafe(12)
                hashed_password = get_password_hash(random_password)

                new_user = User(
                    email=user_email,
                    username=username,
                    hashed_password=hashed_password
                )
                db.add(new_user)
                db.commit()
                db.refresh(new_user)

                # Save Gmail tokens and start a session
                save_gmail_token(db, new_user.id, tokens)
                session_id = create_session(new_user.id, new_user.username, user_email)

                response_redirect = RedirectResponse(_post_auth_redirect_url(session_id=session_id), status_code=302)
                _set_session_cookie(response_redirect, session_id)
                logger.info(f"Auto-provisioned user {username} from Gmail {user_email}")
                return response_redirect

        finally:
            db.close()

    except Exception as e:
        logger.error(f"OAuth2 callback failed: {e}")
        return HTMLResponse(f"<h1>Authentication failed</h1><p>Error: {e}</p><p><a href='/'>Try Again</a></p>")

@app.post("/register")
async def register(
    request: Request,
    response: Response,
    email: str = Form(...),
    username: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    state: str = Form(None)
):
    """Handle user registration - enhanced for Gmail-first flow"""
    if password != confirm_password:
        return RedirectResponse("/register?error=Passwords+do+not+match", status_code=302)

    if len(password) < 6:
        return RedirectResponse("/register?error=Password+must+be+at+least+6+characters", status_code=302)

    db = SessionLocal()
    try:
        # Check if user already exists
        existing_user = db.query(User).filter(
            (User.email == email) | (User.username == username)
        ).first()

        if existing_user:
            return RedirectResponse("/register?error=Username+or+email+already+exists", status_code=302)

        # Create new user
        hashed_password = get_password_hash(password)
        new_user = User(
            email=email,
            username=username,
            hashed_password=hashed_password
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)

        # If Gmail was connected first, save the tokens
        if state and state in sessions:
            session_data = sessions[state]
            if session_data.get("gmail_tokens"):
                save_gmail_token(db, new_user.id, session_data["gmail_tokens"])

        # Create session
        session_id = create_session(new_user.id, new_user.username, email)

        # Prepare redirect and set session cookie on the redirect response
        redirect_resp = RedirectResponse("/", status_code=302)
        _set_session_cookie(redirect_resp, session_id)

        # Clean up temp state
        if state and state in sessions:
            del sessions[state]

        logger.info(f"User {username} registered successfully")
        return redirect_resp
    finally:
        db.close()

@app.post("/login")
@app.post("/api/login")
@limiter.limit("5/minute")
async def login(
    request: Request,
    response: Response,
    username: str = Form(...),
    password: str = Form(...)
):
    """Handle user login"""
    db = SessionLocal()
    try:
        user = authenticate_user(db, username, password)
        if not user:
            # For API requests, return JSON error
            if "application/json" in request.headers.get("accept", "") or request.url.path.startswith("/api/"):
                return JSONResponse({"success": False, "message": "Invalid credentials"}, status_code=401)
            return RedirectResponse("/login?error=Invalid+credentials", status_code=302)

        # Create session
        session_id = create_session(user.id, user.username, user.email)

        logger.info(f"User {username} logged in successfully")

        # Check if this is an API request
        if "application/json" in request.headers.get("accept", "") or request.url.path.startswith("/api/"):
            response = JSONResponse({
                "success": True,
                "user": {
                    "username": user.username,
                    "email": user.email,
                    "profile_photo": user.profile_photo
                }
            })
            _set_session_cookie(response, session_id)
            return response

        # Prepare redirect and set session cookie on the redirect response
        redirect_resp = RedirectResponse("/", status_code=302)
        _set_session_cookie(redirect_resp, session_id)
        return redirect_resp
    finally:
        db.close()

@app.get("/logout")
async def logout(response: Response):
    """Handle user logout"""
    redirect_resp = RedirectResponse("/", status_code=302)
    _delete_session_cookie(redirect_resp)
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
    """Manually trigger email processing for current user"""
    user = get_current_user_from_session(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    gmail_svc, tasks_svc = get_user_services(user["user_id"])
    if not gmail_svc or not tasks_svc:
        return RedirectResponse("/?error=Gmail+not+connected", status_code=302)

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

        if result["total"] == 0:
            if "application/json" in request.headers.get("accept", ""):
                return JSONResponse({"message": "No emails found", "processed_count": 0, "total_emails": 0})
            return RedirectResponse("/?message=No+emails+found", status_code=302)

        message = f"Successfully processed {result['processed']} out of {result['total']} emails"
        if "application/json" in request.headers.get("accept", ""):
            return JSONResponse({"message": message, "processed_count": result['processed'], "total_emails": result['total']})
        return RedirectResponse(f"/?message={message}", status_code=302)

    except Exception as e:
        logger.error(f"Error processing emails: {e}")
        if "application/json" in request.headers.get("accept", ""):
            return JSONResponse({"error": str(e)}, status_code=500)
        return RedirectResponse(f"/?error=Error+processing+emails", status_code=302)

@app.get("/tasks", response_class=HTMLResponse)
async def view_tasks(request: Request):
    """View tasks for current user"""
    user = get_current_user_from_session(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    gmail_svc, tasks_svc = get_user_services(user["user_id"])
    if not gmail_svc or not tasks_svc:
        return RedirectResponse("/?error=Gmail+not+connected", status_code=302)

    try:
        # Get user's task lists
        task_lists = tasks_svc.get_task_lists()

        # Get tasks from each list
        all_tasks = []
        for task_list in task_lists:
            tasks = tasks_svc.get_tasks(task_list['id'], max_results=50)
            for task in tasks:
                task['list_name'] = task_list['title']
                all_tasks.append(task)

        context = {
            "request": request,
            "authenticated": True,
            "user": user,
            "task_lists": task_lists,
            "tasks": all_tasks,
            "title": "Inbotic - My Tasks"
        }

        return templates.TemplateResponse("tasks.html", context)

    except Exception as e:
        logger.error(f"Error loading tasks: {e}")
        return RedirectResponse(f"/?error=Error+loading+tasks", status_code=302)

# Removed Jinja2 routes: /, /emails, /profile to support React frontend
# These paths should be handled by the frontend router, with data fetched from API endpoints.

@app.post("/profile/update-username")
@app.post("/api/profile/update-username")
async def update_username(request: Request, new_username: str = Form(...)):
    """Allow a logged-in user to change their username"""
    user_session = get_current_user_from_session(request)
    if not user_session:
        return RedirectResponse("/login", status_code=302)

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
    <p><a href="/login">Go to Login</a></p>
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
    _delete_session_cookie(resp)
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
    email = data.get("email")
    username = data.get("username")
    password = data.get("password")
    confirm_password = data.get("confirm_password")

    if password != confirm_password:
        return JSONResponse({"error": "Passwords do not match"}, status_code=400)

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
        _set_session_cookie(resp, session_id)
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
                            # Handle '2023-12-01T00:00:00.000Z' or '2023-12-01'
                            if 'T' in due_str:
                                date_part, time_part = due_str.split('T', 1)
                                due_date = datetime.strptime(date_part, "%Y-%m-%d")
                                # Extract time: "14:35:00.000Z" -> "14:35:00"
                                time_cleaned = time_part.replace('Z', '').split('.')[0]  # Remove milliseconds/timezone
                                due_time = time_cleaned
                            else:
                                due_date = datetime.strptime(due_str, "%Y-%m-%d")
                        except Exception as e:
                            logger.debug(f"Failed to parse due date '{task.get('due')}': {e}")

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

