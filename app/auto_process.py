import asyncio
import os

from app.config import logger
from app.deps import get_all_user_services
from database import GmailToken, SessionLocal, User

auto_process_task: asyncio.Task | None = None
auto_process_running = False


def _list_users_with_gmail_tokens() -> list[User]:
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
    user_id: int, username: str,
    days_back: int, max_emails: int,
    pre_reminder_days: int, pre_reminder_hours: int,
    max_days_ahead: int,
) -> dict[str, int]:
    services = get_all_user_services(user_id)
    if not services:
        return {"processed": 0, "total": 0}
    total_processed = 0
    total_emails = 0
    for gmail_svc, tasks_svc, account_email, _ in services:
        if not gmail_svc or not tasks_svc:
            continue
        try:
            emails = gmail_svc.get_recent_emails(max_results=max_emails, days_back=days_back)
            if not emails:
                continue
            task_list_name = f"Inbotic - {username}" if not account_email else f"Inbotic - {account_email.split('@')[0]}"
            task_list = tasks_svc.get_or_create_task_list(task_list_name)
            if not task_list:
                total_emails += len(emails)
                continue
            task_list_id = task_list['id']
            for email in emails:
                total_emails += 1
                try:
                    tasks = tasks_svc.create_tasks_from_email(
                        task_list_id=task_list_id, email_data=email,
                        extract_deadlines=True, max_days_ahead=max_days_ahead,
                        default_due_time_utc="09:00:00.000Z",
                        create_action_tasks=False,
                        pre_reminder_days=pre_reminder_days,
                        pre_reminder_hours=pre_reminder_hours,
                        create_pre_reminder=True, dedupe=True,
                    )
                    is_dedupe = tasks and len(tasks) == 1 and tasks[0].get('dedupe')
                    if tasks and not is_dedupe:
                        total_processed += 1
                except Exception as e:
                    logger.error(f"Error processing email {email.get('id', 'unknown')} for {account_email}: {e}")
        except Exception as e:
            logger.error(f"Error processing account {account_email}: {e}")
    return {"processed": total_processed, "total": total_emails}


def _run_auto_process_once() -> dict[str, int]:
    days_back = int(os.getenv("INBOTIC_AUTO_PROCESS_DAYS_BACK", "1"))
    max_emails = int(os.getenv("INBOTIC_AUTO_PROCESS_MAX_EMAILS", "20"))
    pre_reminder_days = int(os.getenv("INBOTIC_AUTO_PROCESS_PRE_REMINDER_DAYS", "1"))
    pre_reminder_hours = int(os.getenv("INBOTIC_AUTO_PROCESS_PRE_REMINDER_HOURS", "0"))
    max_days_ahead = int(os.getenv("INBOTIC_AUTO_PROCESS_MAX_DAYS_AHEAD", "60"))
    users = _list_users_with_gmail_tokens()
    if not users:
        logger.info("Auto process: no users with Gmail tokens found")
        return {"users": 0, "emails_scanned": 0, "emails_created": 0}
    total_users = 0
    total_emails = 0
    total_created = 0
    for u in users:
        total_users += 1
        result = _process_user_emails_once(
            user_id=u.id, username=u.username,
            days_back=days_back, max_emails=max_emails,
            pre_reminder_days=pre_reminder_days,
            pre_reminder_hours=pre_reminder_hours,
            max_days_ahead=max_days_ahead,
        )
        total_created += result["processed"]
        total_emails += result["total"]
    logger.info(f"Auto process done: users={total_users}, emails_scanned={total_emails}, emails_created={total_created}")
    return {"users": total_users, "emails_scanned": total_emails, "emails_created": total_created}


async def _auto_process_loop():
    global auto_process_running
    interval_seconds = max(15, int(os.getenv("INBOTIC_AUTO_PROCESS_INTERVAL_SECONDS", "30")))
    while auto_process_running:
        try:
            await asyncio.to_thread(_run_auto_process_once)
        except Exception as e:
            logger.error(f"Auto process loop error: {e}")
        await asyncio.sleep(interval_seconds)


async def startup_auto_process():
    global auto_process_task, auto_process_running
    from app.config import _env_bool
    enabled = _env_bool("INBOTIC_AUTO_PROCESS_NEW_MAIL", False)
    if not enabled:
        logger.info("Auto process disabled (INBOTIC_AUTO_PROCESS_NEW_MAIL=false)")
        return
    if auto_process_task and not auto_process_task.done():
        return
    auto_process_running = True
    auto_process_task = asyncio.create_task(_auto_process_loop())
    logger.info("Auto process enabled: background new-mail polling started")


async def shutdown_auto_process():
    global auto_process_task, auto_process_running
    auto_process_running = False
    if auto_process_task:
        auto_process_task.cancel()
        try:
            await auto_process_task
        except asyncio.CancelledError:
            pass
        auto_process_task = None
