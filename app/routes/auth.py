import json
import os
from pathlib import Path
from urllib.parse import urlencode

import requests
from fastapi import APIRouter, Body, File, Form, Request, Response, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app.config import (
    _create_oauth_state,
    _delete_session_cookie,
    _has_shared_oauth_credentials,
    _is_valid_oauth_state,
    _manual_oauth_allowed,
    _post_auth_redirect_url,
    _set_session_cookie,
    logger,
    render_oauth_choice_page,
    render_oauth_setup_page,
    sessions,
)
from app.deps import create_session, get_current_user_from_session
from auth import get_password_hash
from database import SessionLocal, User, GmailToken
from gmail_service import GmailService
from google_oauth_config import resolve_google_oauth_client_config
from user_service import save_gmail_token, get_all_gmail_tokens

router = APIRouter()


@router.get("/auth/gmail")
async def auth_gmail(request: Request, mode: str = None):
    allow_manual = _manual_oauth_allowed()
    shared_available = _has_shared_oauth_credentials()
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
    temp_state = _create_oauth_state()
    client_id, _ = resolve_google_oauth_client_config()
    redirect_uri = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/callback")
    if not client_id:
        return RedirectResponse("/setup/google-credentials", status_code=302)
    params = {
        'response_type': 'code',
        'client_id': client_id,
        'redirect_uri': redirect_uri,
        'scope': 'https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/tasks',
        'prompt': 'consent',
        'access_type': 'offline',
        'state': temp_state,
    }
    return RedirectResponse(f"https://accounts.google.com/o/oauth2/auth?{urlencode(params)}")


@router.get("/setup/google-credentials")
async def setup_google_credentials_page():
    return render_oauth_setup_page()


@router.post("/setup/google-credentials")
async def setup_google_credentials(
    credentials_file: UploadFile = File(None),
    client_id: str = Form(""),
    client_secret: str = Form(""),
):
    cid = (client_id or "").strip()
    csec = (client_secret or "").strip()
    if credentials_file and credentials_file.filename:
        try:
            raw = await credentials_file.read()
            payload = json.loads(raw.decode("utf-8"))
            if isinstance(payload, dict):
                for block in (payload.get("web"), payload.get("installed")):
                    if isinstance(block, dict):
                        cid = cid or (block.get("client_id") or "").strip()
                        csec = csec or (block.get("client_secret") or "").strip()
                cid = cid or (payload.get("client_id") or "").strip()
                csec = csec or (payload.get("client_secret") or "").strip()
            secrets_dir = Path(".secrets")
            secrets_dir.mkdir(parents=True, exist_ok=True)
            (secrets_dir / "google-credentials.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
            os.environ["GOOGLE_CREDENTIALS_PATH"] = str(secrets_dir / "google-credentials.json")
        except Exception as e:
            return render_oauth_setup_page(f"Could not read uploaded JSON: {e}", is_error=True)
    if not cid or not csec:
        return render_oauth_setup_page(
            "Missing client_id/client_secret. Upload a valid OAuth JSON file or fill both fields.", is_error=True)
    os.environ["CLIENT_ID"] = cid
    os.environ["CLIENT_SECRET"] = csec
    return RedirectResponse("/auth/gmail?mode=shared", status_code=302)


@router.get("/auth/callback")
async def auth_callback(request: Request, code: str = None, state: str = None, error: str = None):
    if error:
        return HTMLResponse(f"<h1>Authentication failed</h1><p>Error: {error}</p><p><a href='/'>Try Again</a></p>")
    if not code or not state:
        return HTMLResponse("<h1>Authentication failed</h1><p>Missing authorization code or state</p><p><a href='/'>Try Again</a></p>")
    if _is_valid_oauth_state(state):
        return await handle_oauth_callback(code, state, request)
    return RedirectResponse("/login?message=Please+login+first", status_code=302)


async def handle_oauth_callback(code: str, temp_state: str, request: Request):
    try:
        client_id, client_secret = resolve_google_oauth_client_config()
        redirect_uri = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/callback")
        if not client_id or not client_secret:
            return HTMLResponse(
                "<h1>Configuration error</h1><p>Missing Google OAuth credentials.</p>", status_code=500)
        resp = requests.post("https://oauth2.googleapis.com/token", data={
            'code': code, 'client_id': client_id, 'client_secret': client_secret,
            'redirect_uri': redirect_uri, 'grant_type': 'authorization_code',
        })
        resp.raise_for_status()
        tokens = resp.json()
        gmail_service = GmailService.from_user_token(tokens)
        profile = gmail_service.service.users().getProfile(userId='me').execute()
        user_email = profile['emailAddress']

        # Check if user is already logged in (adding another account)
        current_user = get_current_user_from_session(request)
        db = SessionLocal()
        try:
            if current_user:
                # Adding another account to existing user
                save_gmail_token(db, current_user["user_id"], tokens, email_account=user_email)
                r = RedirectResponse(_post_auth_redirect_url(), status_code=302)
                _set_session_cookie(r, request.cookies.get("session_id"))
                return r

            # First-time auth: check if user exists for this email
            existing_user = db.query(User).filter(User.email == user_email).first()
            if existing_user:
                save_gmail_token(db, existing_user.id, tokens, email_account=user_email)
                sid = create_session(existing_user.id, existing_user.username, user_email)
                r = RedirectResponse(_post_auth_redirect_url(session_id=sid), status_code=302)
                _set_session_cookie(r, sid)
                return r

            # Create new user
            base = user_email.split("@")[0]
            username = base
            suffix = 1
            while db.query(User).filter(User.username == username).first():
                suffix += 1
                username = f"{base}{suffix}"
            new_user = User(email=user_email, username=username, hashed_password=get_password_hash(__import__("secrets").token_urlsafe(12)))
            db.add(new_user)
            db.commit()
            db.refresh(new_user)
            save_gmail_token(db, new_user.id, tokens, email_account=user_email)
            sid = create_session(new_user.id, new_user.username, user_email)
            r = RedirectResponse(_post_auth_redirect_url(session_id=sid), status_code=302)
            _set_session_cookie(r, sid)
            return r
        finally:
            db.close()
    except Exception as e:
        logger.error(f"OAuth callback failed: {e}")
        return HTMLResponse(f"<h1>Authentication failed</h1><p>Error: {e}</p><p><a href='/'>Try Again</a></p>")


@router.get("/api/auth/accounts")
async def api_list_accounts(request: Request):
    """List all connected Gmail accounts for the current user."""
    current_user = get_current_user_from_session(request)
    if not current_user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    db = SessionLocal()
    try:
        tokens = get_all_gmail_tokens(db, current_user["user_id"])
        accounts = []
        for t in tokens:
            accounts.append({
                "id": t.id,
                "email": t.email_account,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            })
        return JSONResponse({"accounts": accounts})
    finally:
        db.close()


@router.post("/api/auth/gmail-token")
async def api_auth_gmail_token(request: Request, data: dict = Body(...)):
    access_token = (data.get("access_token") or "").strip()
    if not access_token:
        return JSONResponse({"error": "Missing access_token"}, status_code=400)

    # Verify the token with Google
    try:
        resp = requests.get(
            "https://www.googleapis.com/oauth2/v3/tokeninfo",
            params={"access_token": access_token},
            timeout=10,
        )
        if resp.status_code != 200:
            logger.warning(f"Token verification failed: {resp.status_code} {resp.text}")
            return JSONResponse({"error": "Invalid access token"}, status_code=401)
        token_info = resp.json()
        email = token_info.get("email")
        if not email:
            return JSONResponse({"error": "No email in token"}, status_code=401)
    except requests.RequestException as e:
        logger.error(f"Token verification error: {e}")
        return JSONResponse({"error": "Failed to verify token"}, status_code=502)

    # Find or create user by email
    db = SessionLocal()
    try:
        existing_user = db.query(User).filter(User.email == email).first()
        if existing_user:
            user = existing_user
        else:
            base = email.split("@")[0]
            username = base
            suffix = 1
            while db.query(User).filter(User.username == username).first():
                suffix += 1
                username = f"{base}{suffix}"
            password = __import__("secrets").token_urlsafe(12)
            user = User(
                email=email, username=username,
                hashed_password=get_password_hash(password),
            )
            db.add(user)
            db.commit()
            db.refresh(user)

        # Save/update Gmail token
        from user_service import save_gmail_token
        tokens = {"access_token": access_token}
        # Also accept a refresh token if the app sends it
        refresh_token = (data.get("refresh_token") or "").strip()
        if refresh_token:
            tokens["refresh_token"] = refresh_token
        save_gmail_token(db, user.id, tokens, email_account=email)

        # Create session
        sid = create_session(user.id, user.username, email)
        r = JSONResponse({
            "success": True,
            "user": {"username": user.username, "email": user.email},
        })
        _set_session_cookie(r, sid)
        return r
    except Exception as e:
        logger.error(f"Gmail token auth failed: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)
    finally:
        db.close()


@router.get("/logout")
async def logout(response: Response):
    r = RedirectResponse("/", status_code=302)
    _delete_session_cookie(r)
    return r



