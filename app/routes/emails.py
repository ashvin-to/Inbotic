from datetime import datetime

from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse

from app.auto_process import _process_user_emails_once
from app.config import logger
from app.deps import get_all_user_services, get_current_user_from_session
from database import Email, GmailToken, SessionLocal

router = APIRouter()


@router.post("/process-emails")
@router.post("/api/process-emails")
async def process_emails(
    request: Request,
    days_back: int = Form(7),
    max_emails: int = Form(10),
    pre_reminder_days: int = Form(1),
    pre_reminder_hours: int = Form(0),
    max_days_ahead: int = Form(60),
):
    user = get_current_user_from_session(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    services = get_all_user_services(user["user_id"])
    if not services:
        return RedirectResponse("/?error=Gmail+not+connected", status_code=302)
    try:
        result = _process_user_emails_once(
            user_id=user["user_id"], username=user["username"],
            days_back=days_back, max_emails=max_emails,
            pre_reminder_days=pre_reminder_days, pre_reminder_hours=pre_reminder_hours,
            max_days_ahead=max_days_ahead,
        )
        if result["total"] == 0:
            if "application/json" in request.headers.get("accept", ""):
                return JSONResponse({"message": "No emails found", "processed_count": 0, "total_emails": 0})
            return RedirectResponse("/?message=No+emails+found", status_code=302)
        msg = f"Successfully processed {result['processed']} out of {result['total']} emails"
        if "application/json" in request.headers.get("accept", ""):
            return JSONResponse({"message": msg, "processed_count": result['processed'], "total_emails": result['total']})
        return RedirectResponse(f"/?message={msg}", status_code=302)
    except Exception as e:
        logger.error(f"Error processing emails: {e}")
        if "application/json" in request.headers.get("accept", ""):
            return JSONResponse({"error": str(e)}, status_code=500)
        return RedirectResponse("/?error=Error+processing+emails", status_code=302)


@router.get("/api/emails")
async def api_emails(request: Request, days_back: int = 7):
    user = get_current_user_from_session(request)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    db = SessionLocal()
    try:
        # Return cached emails from all accounts
        db_emails = db.query(Email).filter(Email.user_id == user["user_id"]).order_by(Email.received_at.desc()).limit(50).all()
        if db_emails:
            results = []
            for e in db_emails:
                account_email = None
                if e.gmail_token_id:
                    token = db.query(GmailToken).filter(GmailToken.id == e.gmail_token_id).first()
                    if token:
                        account_email = token.email_account
                results.append({
                    "id": e.gmail_message_id, "subject": e.subject, "sender": e.sender,
                    "body": e.body, "date": e.received_at.strftime("%Y-%m-%d") if e.received_at else "",
                    "processed": e.processed, "extracted_data": e.extracted_data,
                    "account_email": account_email,
                })
            return JSONResponse({"emails": results})

        # Fetch from all connected accounts
        services = get_all_user_services(user["user_id"])
        all_emails = []
        for gmail_svc, _, account_email, token_id in services:
            try:
                emails = gmail_svc.get_recent_emails(max_results=20, days_back=days_back)
                for email_data in emails:
                    email_data["account_email"] = account_email
                    all_emails.append(email_data)
                    if not db.query(Email).filter(Email.user_id == user["user_id"], Email.gmail_message_id == email_data['id']).first():
                        db.add(Email(
                            user_id=user["user_id"], gmail_token_id=token_id,
                            gmail_message_id=email_data['id'],
                            subject=email_data.get('subject', 'No Subject'),
                            sender=email_data.get('sender', 'Unknown'),
                            body=email_data.get('body', ''),
                            received_at=datetime.now(), processed=False,
                        ))
            except Exception as e:
                logger.error(f"Error fetching emails for {account_email}: {e}")
        db.commit()
        return JSONResponse({"emails": all_emails})
    except Exception as e:
        logger.error(f"Error fetching emails: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)
    finally:
        db.close()
