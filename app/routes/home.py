import os
from pathlib import Path

from fastapi import APIRouter, Header, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from app.auto_process import _run_auto_process_once
from app.config import _has_shared_oauth_credentials, _manual_oauth_allowed, logger, sessions
from app.deps import get_current_user_from_session, get_user_services
from database import GmailToken, SessionLocal

router = APIRouter()


FRONTEND_INDEX = str(Path("frontend/dist/index.html"))


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return FileResponse(FRONTEND_INDEX)


@router.get("/tasks", response_class=HTMLResponse)
async def view_tasks(request: Request):
    return FileResponse(FRONTEND_INDEX)


@router.get("/debug-session", response_class=HTMLResponse)
async def debug_session(request: Request):
    user = get_current_user_from_session(request)
    return HTMLResponse(f"""
    <h1>Session Debug Info</h1>
    <pre>{{"session_id": {request.cookies.get("session_id")}, "user": {user}, "all_sessions": {list(sessions.keys())}, "all_cookies": {dict(request.cookies)}}}</pre>
    <p><a href="/">Go to Home</a></p>
    """)


@router.get("/api/me")
async def api_me(request: Request):
    user = get_current_user_from_session(request)
    if not user:
        return JSONResponse({"authenticated": False}, status_code=401)
    user_data = dict(user)
    if "created_at" in user_data and hasattr(user_data["created_at"], "isoformat"):
        user_data["created_at"] = user_data["created_at"].isoformat()
    db = SessionLocal()
    try:
        user_data["gmail_tokens_connected"] = db.query(GmailToken).filter(GmailToken.user_id == user["user_id"]).first() is not None
    finally:
        db.close()
    return JSONResponse({"authenticated": True, "user": user_data})


@router.post("/api/logout")
async def api_logout():
    from app.config import _delete_session_cookie
    r = JSONResponse({"success": True})
    _delete_session_cookie(r)
    return r


@router.get("/api/dashboard")
async def api_dashboard(request: Request):
    user = get_current_user_from_session(request)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    gmail_svc, tasks_svc = get_user_services(user["user_id"])
    user_data = dict(user)
    if "created_at" in user_data and hasattr(user_data["created_at"], "isoformat"):
        user_data["created_at"] = user_data["created_at"].isoformat()
    data = {"user": user_data, "gmail_connected": False, "ia_tasks_count": 0, "task_lists": [], "emails_this_week": 0, "pending_tasks": 0}
    if gmail_svc and tasks_svc:
        data["gmail_connected"] = True
        try:
            task_lists = tasks_svc.get_task_lists()
            data["task_lists"] = task_lists
            ia_list = next((tl for tl in task_lists if tl.get('title') == f"Inbotic - {user['username']}"), None)
            if ia_list:
                ia_tasks = tasks_svc.get_tasks(ia_list['id'], max_results=50)
                data["ia_tasks_count"] = len(ia_tasks or [])
                data["pending_tasks"] = sum(1 for t in (ia_tasks or []) if t.get('status') == 'needsAction')
        except Exception as e:
            err = str(e)
            if "invalid_grant" in err or "Token has been expired" in err:
                data["needs_reauth"] = True
                data["error"] = "Your Google connection has expired. Please reconnect."
            else:
                logger.error(f"Dashboard API error: {e}")
        if not data.get("needs_reauth"):
            try:
                emails = gmail_svc.get_recent_emails(max_results=20, days_back=7)
                data["emails_this_week"] = len(emails) if emails else 0
            except Exception as e:
                err = str(e)
                if "invalid_grant" in err or "Token has been expired" in err:
                    data["needs_reauth"] = True
                    data["error"] = "Your Google connection has expired. Please reconnect."
                logger.error(f"Email count error: {e}")
    return JSONResponse(data)


@router.post("/api/auto-process/run")
async def api_auto_process_run(x_auto_process_key: str = Header(default=None)):
    expected = (os.getenv("INBOTIC_AUTO_PROCESS_API_KEY") or "").strip()
    if not expected:
        return JSONResponse({"error": "Auto-process API key is not configured"}, status_code=503)
    if (x_auto_process_key or "").strip() != expected:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    try:
        import asyncio
        result = await asyncio.to_thread(_run_auto_process_once)
        return JSONResponse({"success": True, "result": result})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)



