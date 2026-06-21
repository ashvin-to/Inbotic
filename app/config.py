import hashlib
import hmac
import logging
import os
import secrets
from datetime import datetime
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from dotenv import load_dotenv
from fastapi import Response
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from slowapi import Limiter
from slowapi.util import get_remote_address

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler('inbox_agent.log'), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

sessions: dict[str, Any] = {}
templates = Jinja2Templates(directory="templates")
templates.env.globals["now"] = datetime.now
limiter = Limiter(key_func=get_remote_address)


def _build_allowed_hosts() -> list[str]:
    hosts = {"localhost", "127.0.0.1", "0.0.0.0"}
    for var in ("RENDER_EXTERNAL_URL", "FRONTEND_URL"):
        val = (os.getenv(var) or "").strip()
        if val:
            parts = urlsplit(val)
            if parts.netloc:
                hosts.add(parts.netloc)
    extra = (os.getenv("ALLOWED_HOSTS") or "").strip()
    if extra:
        for host in extra.split(","):
            clean = host.strip()
            if clean:
                hosts.add(clean)
    return sorted(hosts)


def _build_cors_origins() -> list[str]:
    origins = {"http://localhost:5173", "http://127.0.0.1:5173"}
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


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _is_production_deployment() -> bool:
    return any([
        _env_bool("INBOTIC_PRODUCTION", False),
        bool(os.getenv("VERCEL")), bool(os.getenv("NETLIFY")),
        bool(os.getenv("RENDER")), bool(os.getenv("RENDER_EXTERNAL_URL")),
    ])


def _manual_oauth_allowed() -> bool:
    return _env_bool("INBOTIC_ALLOW_MANUAL_OAUTH", not _is_production_deployment())


def _oauth_state_secret() -> str:
    return (os.getenv("OAUTH_STATE_SECRET") or os.getenv("SECRET_KEY") or "inbotic-dev-secret").strip()


def _create_oauth_state() -> str:
    ts = int(datetime.utcnow().timestamp())
    nonce = secrets.token_urlsafe(16)
    payload = f"{ts}:{nonce}"
    sig = hmac.new(_oauth_state_secret().encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}:{sig}"


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
    expected = hmac.new(_oauth_state_secret().encode(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        return False
    age = int(datetime.utcnow().timestamp()) - int(ts_raw)
    return 0 <= age <= max_age_seconds


def _session_cookie_settings() -> dict[str, Any]:
    default_prod = _is_production_deployment()
    default_samesite = "none" if default_prod else "lax"
    samesite = (os.getenv("SESSION_COOKIE_SAMESITE") or default_samesite).strip().lower()
    if samesite not in {"lax", "strict", "none"}:
        samesite = default_samesite
    secure = _env_bool("SESSION_COOKIE_SECURE", default_prod or samesite == "none")
    return {"max_age": 86400, "httponly": True, "samesite": samesite, "secure": secure}


def _set_session_cookie(response: Response, session_id: str) -> None:
    response.set_cookie(key="session_id", value=session_id, **_session_cookie_settings())


def _delete_session_cookie(response: Response) -> None:
    s = _session_cookie_settings()
    response.delete_cookie(key="session_id", httponly=True, samesite=s["samesite"], secure=s["secure"])


def _post_auth_redirect_url(session_id: str | None = None) -> str:
    frontend_url = (os.getenv("FRONTEND_URL") or "").strip()
    if frontend_url:
        target = frontend_url.rstrip("/") + "/"
        if not session_id:
            return target
        parts = urlsplit(target)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        query["session_id"] = session_id
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
    return "/"


def _has_shared_oauth_credentials() -> bool:
    from google_oauth_config import resolve_google_oauth_client_config
    cid, secret = resolve_google_oauth_client_config()
    return bool(cid and secret)


def render_oauth_choice_page(shared_available: bool, allow_manual: bool):
    disabled = "disabled" if not shared_available else ""
    note = "" if shared_available else "<p class='muted' style='color:#b00020;'>Hosted OAuth is not configured on this server yet.</p>"
    manual = ""
    if allow_manual:
        manual = """
        <div class='card'>
            <h3>Use My Own OAuth Credentials</h3>
            <p>Upload your OAuth JSON or paste Client ID and Client Secret.</p>
            <a class='btn secondary' href='/setup/google-credentials'>Manual Setup</a>
        </div>"""
    return HTMLResponse(f"""
    <html><head><title>Choose Sign-In Method</title>
    <style>body{{font-family:Arial,sans-serif;margin:2rem;line-height:1.5}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:1rem;max-width:900px}}.card{{border:1px solid #ddd;border-radius:10px;padding:1.25rem}}.btn{{margin-top:.8rem;display:inline-block;text-decoration:none;padding:.6rem 1rem;border-radius:8px;background:#0a66c2;color:#fff}}.btn.secondary{{background:#444}}.btn[disabled]{{pointer-events:none;opacity:.5}}.muted{{color:#666;font-size:.95rem}}</style></head>
    <body><h1>Choose how to connect Gmail</h1>
    <p class='muted'>You can sign in using hosted OAuth managed by this app, or configure your own Google OAuth credentials.</p>
    <div class='grid'><div class='card'><h3>Use Hosted OAuth</h3><p>This is easiest for end users. They just sign in with Google.</p>{note}
    <a class='btn' href='/auth/gmail?mode=shared' {disabled}>Continue with Hosted OAuth</a></div>{manual}</div></body></html>""")


def render_oauth_setup_page(message: str = "", is_error: bool = False):
    style = "color:#b00020;" if is_error else "color:#0a7c2f;"
    status = f"<p style='{style}'>{message}</p>" if message else ""
    return HTMLResponse(f"""
    <html><head><title>Inbotic Setup</title>
    <style>body{{font-family:Arial,sans-serif;margin:2rem;line-height:1.5}}.card{{max-width:760px;border:1px solid #ddd;border-radius:10px;padding:1.25rem}}.muted{{color:#666;font-size:.95rem}}label{{font-weight:600;display:block;margin-top:1rem}}input[type='file'],input[type='text']{{width:100%;padding:.5rem;margin-top:.35rem}}button{{margin-top:1rem;padding:.6rem 1rem;border:0;border-radius:8px;background:#0a66c2;color:#fff;cursor:pointer}}code{{background:#f5f5f5;padding:.12rem .3rem;border-radius:4px}}</style></head>
    <body><h1>One-time Google setup</h1><div class='card'>
    <p>Use this page to configure OAuth without editing environment variables manually.</p>{status}
    <ol><li>Create OAuth credentials in Google Cloud (see quick steps below).</li><li>Either upload OAuth JSON or paste Client ID/Client Secret.</li><li>Click Save, then Connect Gmail.</li></ol>
    <div class='muted'><p><strong>Quick Google OAuth steps</strong></p>
    <ol><li>Open Google Cloud Console and create/select a project.</li><li>Enable Gmail API and Google Tasks API.</li><li>Configure OAuth consent screen.</li><li>Create OAuth Client ID (Web application).</li><li>Add redirect URI: http://localhost:8000/auth/callback</li><li>Copy Client ID and Client Secret (or download JSON).</li></ol></div>
    <form action='/setup/google-credentials' method='post' enctype='multipart/form-data'>
    <label>Option A: Upload Google OAuth credentials JSON</label>
    <input type='file' name='credentials_file' accept='.json,application/json' />
    <p class='muted'>Option B (skip JSON): paste these values directly.</p>
    <label>Client ID</label><input type='text' name='client_id' placeholder='your-google-oauth-client-id' />
    <label>Client Secret</label><input type='text' name='client_secret' placeholder='your-google-oauth-client-secret' />
    <button type='submit'>Save and Continue</button></form>
    <p class='muted'>If you upload JSON, it is saved to <code>.secrets/google-credentials.json</code>.</p>
    <p><a href='/auth/gmail'>Back to sign-in options</a></p></div></body></html>""")
