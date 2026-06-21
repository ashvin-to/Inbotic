import os
import re
from datetime import datetime

from fastapi import APIRouter, Body, Query, Request
from fastapi.responses import JSONResponse

from app.auto_process import _process_user_emails_once
from app.config import logger
from app.deps import get_all_user_services, get_current_user_from_session, get_user_services
from database import GmailToken, SessionLocal, Task

router = APIRouter()


def _normalize_time_hms_for_api(time_value: str) -> str:
    if not time_value:
        return ""
    text = str(time_value).strip()
    if 'T' in text:
        text = text.split('T', 1)[1]
    text = text.replace('Z', '').split('.', 1)[0]
    text = re.sub(r'([+-]\d{2}:?\d{2})$', '', text).strip()
    parts = text.split(':')
    if len(parts) == 2:
        text = f"{parts[0]}:{parts[1]}:00"
    if re.fullmatch(r'([01]?\d|2[0-3]):([0-5]\d):([0-5]\d)', text):
        h, m, s = text.split(':')
        return f"{int(h):02d}:{int(m):02d}:{int(s):02d}"
    return ""


def _task_to_dict(t: Task, account_email: str = None) -> dict:
    due = None
    if t.due_date:
        dp = t.due_date.strftime("%Y-%m-%d")
        tp = _normalize_time_hms_for_api(t.due_time) or "00:00:00"
        due = f"{dp}T{tp}.000Z"
    source = "google" if t.gmail_task_id else "custom"
    return {
        "id": t.gmail_task_id or str(t.id),
        "local_id": t.id,
        "title": t.title,
        "notes": t.description,
        "due": due,
        "updated": t.updated_at.isoformat() if t.updated_at else None,
        "status": t.status,
        "list_id": t.gmail_task_list_id,
        "priority": t.priority,
        "source": source,
        "account_email": account_email,
    }


@router.get("/api/tasks")
async def api_tasks(request: Request, refresh: bool = False):
    user = get_current_user_from_session(request)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    db = SessionLocal()
    try:
        all_tasks = []

        if refresh:
            # Clear cached Google Tasks and re-fetch from all accounts
            db.query(Task).filter(
                Task.user_id == user["user_id"],
                Task.gmail_task_id.isnot(None)
            ).delete()
            db.commit()

            services = get_all_user_services(user["user_id"])
            for _, tasks_svc, account_email, token_id in services:
                if tasks_svc:
                    try:
                        task_lists = tasks_svc.get_task_lists()
                    tasks_svc: tasks_svc
                    for tl in task_lists:
                        for task in tasks_svc.get_tasks(tl['id'], max_results=50):
                            task['list_name'] = tl['title']
                            task['list_id'] = tl['id']
                            task['account_email'] = account_email
                            all_tasks.append(task)
                            due_date = None
                            due_time = None
                            if task.get('due'):
                                try:
                                    ds = task['due']
                                    if 'T' in ds:
                                        dp, tp = ds.split('T', 1)
                                        due_date = datetime.strptime(dp, "%Y-%m-%d")
                                        due_time = tp.replace('Z', '').split('.')[0]
                                    else:
                                        due_date = datetime.strptime(ds, "%Y-%m-%d")
                                except Exception as e:
                                    logger.debug(f"Failed to parse due '{task.get('due')}': {e}")
                            db.add(Task(
                                user_id=user["user_id"], gmail_token_id=token_id,
                                gmail_task_id=task['id'], gmail_task_list_id=tl['id'],
                                gmail_task_list_name=tl['title'],
                                title=task.get('title', 'Untitled'),
                                description=task.get('notes', ''),
                                status=task.get('status', 'needsAction'),
                                due_date=due_date, due_time=due_time,
                            ))
                    except Exception as e:
                        logger.error(f"Error fetching tasks for {account_email}: {e}")
            db.commit()
        else:
            # Load from local DB with account info
            db_tasks = db.query(Task).filter(
                Task.user_id == user["user_id"],
                Task.gmail_task_id.isnot(None)
            ).all()
            for t in db_tasks:
                account_email = None
                if t.gmail_token_id:
                    token = db.query(GmailToken).filter(GmailToken.id == t.gmail_token_id).first()
                    if token:
                        account_email = token.email_account
                d = _task_to_dict(t, account_email)
                d['list_name'] = t.gmail_task_list_name or "Google Tasks"
                all_tasks.append(d)

        # Include custom tasks (no gmail_task_id)
        custom_tasks = db.query(Task).filter(
            Task.user_id == user["user_id"],
            Task.gmail_task_id.is_(None)
        ).all()
        for t in custom_tasks:
            d = _task_to_dict(t)
            d['list_name'] = "Custom Tasks"
            all_tasks.append(d)

        # Build task_lists from distinct list_name entries in all_tasks
        seen = {}
        for t in all_tasks:
            key = t.get('list_name', 'Unknown')
            lid = t.get('list_id') or t.get('list_name', 'Unknown')
            if key not in seen:
                seen[key] = {'id': lid, 'title': key}
        task_lists = list(seen.values())

        return JSONResponse({"tasks": all_tasks, "task_lists": task_lists})
    except Exception as e:
        logger.error(f"Error fetching tasks: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)
    finally:
        db.close()


@router.post("/api/tasks")
async def api_create_task(request: Request, data: dict = Body(...)):
    user = get_current_user_from_session(request)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    title = data.get("title", "").strip()
    if not title:
        return JSONResponse({"error": "Title is required"}, status_code=400)

    due = data.get("due")
    due_date = None
    due_time = None
    if due:
        try:
            if 'T' in due:
                dp, tp = due.split('T', 1)
                due_date = datetime.strptime(dp, "%Y-%m-%d")
                due_time = tp.replace('Z', '').split('.')[0]
            else:
                due_date = datetime.strptime(due, "%Y-%m-%d")
        except Exception as e:
            logger.debug(f"Failed to parse due '{due}': {e}")

    db = SessionLocal()
    try:
        task = Task(
            user_id=user["user_id"],
            title=title,
            description=data.get("notes", ""),
            status=data.get("status", "pending"),
            priority=data.get("priority", "medium"),
            due_date=due_date,
            due_time=due_time,
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        return JSONResponse({"task": _task_to_dict(task)}, status_code=201)
    except Exception as e:
        logger.error(f"Error creating task: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)
    finally:
        db.close()


@router.put("/api/tasks/{task_id}")
async def api_update_task(
    task_id: str,
    request: Request,
    data: dict = Body(...),
    source: str = Query("google"),
):
    user = get_current_user_from_session(request)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    db = SessionLocal()
    try:
        if source == "custom":
            task = db.query(Task).filter(
                Task.id == int(task_id),
                Task.user_id == user["user_id"],
                Task.gmail_task_id.is_(None),
            ).first()
            if not task:
                return JSONResponse({"error": "Task not found"}, status_code=404)

            if "title" in data:
                task.title = data["title"]
            if "notes" in data:
                task.description = data["notes"]
            if "status" in data:
                task.status = data["status"]
            if "priority" in data:
                task.priority = data["priority"]
            if "due" in data:
                due = data["due"]
                if due:
                    try:
                        if 'T' in due:
                            dp, tp = due.split('T', 1)
                            task.due_date = datetime.strptime(dp, "%Y-%m-%d")
                            task.due_time = tp.replace('Z', '').split('.')[0]
                        else:
                            task.due_date = datetime.strptime(due, "%Y-%m-%d")
                            task.due_time = None
                    except Exception as e:
                        logger.debug(f"Failed to parse due '{due}': {e}")
                else:
                    task.due_date = None
                    task.due_time = None
            task.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(task)
            return JSONResponse({"task": _task_to_dict(task)})

        # Google Tasks path
        _, tasks_svc = get_user_services(user["user_id"])
        if not tasks_svc:
            return JSONResponse({"error": "Tasks service not connected"}, status_code=400)
        task_list_id = data.get("list_id")
        if not task_list_id:
            return JSONResponse({"error": "Missing task_list_id"}, status_code=400)
        updates = {}
        for k in ("title", "notes", "status", "due"):
            if k in data:
                updates[k] = data[k]
        updated = tasks_svc.update_task(task_list_id, task_id, updates)
        if updated:
            return JSONResponse({"task": updated})
        return JSONResponse({"error": "Failed to update task"}, status_code=500)
    except Exception as e:
        logger.error(f"Error updating task: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)
    finally:
        db.close()


@router.delete("/api/tasks/{task_id}")
async def api_delete_task(
    task_id: str,
    request: Request,
    list_id: str = Query(""),
    source: str = Query("google"),
):
    user = get_current_user_from_session(request)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    db = SessionLocal()
    try:
        if source == "custom":
            result = db.query(Task).filter(
                Task.id == int(task_id),
                Task.user_id == user["user_id"],
                Task.gmail_task_id.is_(None),
            ).delete()
            db.commit()
            if result:
                return JSONResponse({"success": True})
            return JSONResponse({"error": "Task not found"}, status_code=404)

        # Google Tasks path
        _, tasks_svc = get_user_services(user["user_id"])
        if not tasks_svc:
            return JSONResponse({"error": "Tasks service not connected"}, status_code=400)
        if not list_id:
            return JSONResponse({"error": "Missing list_id"}, status_code=400)
        if tasks_svc.delete_task(list_id, task_id):
            db.query(Task).filter(
                Task.user_id == user["user_id"],
                Task.gmail_task_id == task_id,
            ).delete()
            db.commit()
            return JSONResponse({"success": True})
        return JSONResponse({"error": "Failed to delete task"}, status_code=500)
    except Exception as e:
        logger.error(f"Error deleting task: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)
    finally:
        db.close()


@router.post("/api/tasks/auto-process")
async def api_auto_process_tasks(request: Request):
    user = get_current_user_from_session(request)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    days_back = int(os.getenv("INBOTIC_AUTO_PROCESS_DAYS_BACK", "1"))
    max_emails = int(os.getenv("INBOTIC_AUTO_PROCESS_MAX_EMAILS", "20"))
    pre_reminder_days = int(os.getenv("INBOTIC_AUTO_PROCESS_PRE_REMINDER_DAYS", "1"))
    pre_reminder_hours = int(os.getenv("INBOTIC_AUTO_PROCESS_PRE_REMINDER_HOURS", "0"))
    max_days_ahead = int(os.getenv("INBOTIC_AUTO_PROCESS_MAX_DAYS_AHEAD", "60"))

    result = _process_user_emails_once(
        user_id=user["user_id"], username=user["username"],
        days_back=days_back, max_emails=max_emails,
        pre_reminder_days=pre_reminder_days,
        pre_reminder_hours=pre_reminder_hours,
        max_days_ahead=max_days_ahead,
    )
    return JSONResponse(result)
