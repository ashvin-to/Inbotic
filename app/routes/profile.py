import os
from datetime import datetime

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse

from app.config import logger
from app.deps import get_current_user_from_session
from database import SessionLocal, User

router = APIRouter()


@router.post("/profile/update-username")
@router.post("/api/profile/update-username")
async def update_username(request: Request, new_username: str = Form(...)):
    user_session = get_current_user_from_session(request)
    if not user_session:
        return RedirectResponse("/login", status_code=302)
    new_username = new_username.strip()
    import re
    if len(new_username) < 3 or len(new_username) > 30 or not re.match(r"^[A-Za-z0-9_.-]+$", new_username):
        return RedirectResponse("/profile?error=Invalid+username+format", status_code=302)
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.username == new_username).first()
        if existing and existing.id != user_session["user_id"]:
            return RedirectResponse("/profile?error=Username+already+taken", status_code=302)
        db_user = db.query(User).filter(User.id == user_session["user_id"]).first()
        if not db_user:
            return RedirectResponse("/login", status_code=302)
        db_user.username = new_username
        db.commit()
        session_id = request.cookies.get("session_id")
        from app.config import sessions
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


@router.post("/profile/update-photo")
@router.post("/api/profile/update-photo")
async def update_photo(request: Request, file: UploadFile = File(...)):
    user_session = get_current_user_from_session(request)
    if not user_session:
        if "application/json" in request.headers.get("accept", ""):
            return JSONResponse({"error": "Not authenticated"}, status_code=401)
        return RedirectResponse("/login", status_code=302)
    if not file.content_type or not file.content_type.startswith("image/"):
        if "application/json" in request.headers.get("accept", ""):
            return JSONResponse({"error": "Only image files are allowed"}, status_code=400)
        return RedirectResponse("/profile?error=Invalid+file+type", status_code=302)
    file_content = await file.read()
    if len(file_content) > 5 * 1024 * 1024:
        if "application/json" in request.headers.get("accept", ""):
            return JSONResponse({"error": "File size too large. Maximum 5MB allowed."}, status_code=400)
        return RedirectResponse("/profile?error=File+too+large", status_code=302)
    upload_dir = "static/uploads"
    os.makedirs(upload_dir, exist_ok=True)
    ext = os.path.splitext(file.filename)[1].lower()
    filename = f"{user_session['user_id']}_{int(datetime.now().timestamp())}{ext}"
    file_path = os.path.join(upload_dir, filename)
    try:
        with open(file_path, "wb") as f:
            f.write(file_content)
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
        photo_path = f"/static/uploads/{filename}"
        db_user.profile_photo = photo_path
        db.commit()
        db.refresh(db_user)
        if user_session:
            user_session["profile_photo"] = photo_path
        full_url = f"{str(request.base_url).rstrip('/')}{photo_path}"
        if "application/json" in request.headers.get("accept", ""):
            return JSONResponse({"message": "Profile photo updated", "profile_photo": photo_path, "full_photo_url": full_url})
        return RedirectResponse("/profile?message=Profile+photo+updated", status_code=302)
    except Exception as e:
        logger.error(f"Error updating profile photo: {e}")
        db.rollback()
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception as ce:
            logger.error(f"Cleanup error: {ce}")
        if "application/json" in request.headers.get("accept", ""):
            return JSONResponse({"error": "Failed to update profile photo"}, status_code=500)
        return RedirectResponse("/profile?error=Failed+to+update+profile+photo", status_code=302)
    finally:
        db.close()


@router.get("/api/profile")
async def api_profile(request: Request):
    user_session = get_current_user_from_session(request)
    if not user_session:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    db = SessionLocal()
    try:
        db_user = db.query(User).filter(User.id == user_session["user_id"]).first()
        if not db_user:
            return JSONResponse({"error": "User not found"}, status_code=404)
        profile = {
            "username": db_user.username, "email": db_user.email,
            "profile_photo": db_user.profile_photo,
            "created_at": db_user.created_at.isoformat() if db_user.created_at else None,
            "updated_at": db_user.updated_at.isoformat() if db_user.updated_at else None,
            "emails_count": len(db_user.emails) if db_user.emails else 0,
            "tasks_count": len(db_user.tasks) if db_user.tasks else 0,
            "gmail_tokens_count": len(db_user.gmail_tokens) if db_user.gmail_tokens else 0,
            "gmail_tokens_connected": bool(db_user.gmail_tokens and len(db_user.gmail_tokens) > 0),
            "days_active": (db_user.updated_at - db_user.created_at).days if db_user.created_at and db_user.updated_at else 0,
        }
        return JSONResponse({"user": profile})
    finally:
        db.close()
