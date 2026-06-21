from sqlalchemy.orm import Session
from database import User, GmailToken
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

def save_gmail_token(db: Session, user_id: int, token_data: dict, email_account: str = None):
    """Save or update Gmail token for a user. Allows multiple tokens per user."""
    try:
        # If updating an existing token for this account, remove the old one
        if email_account:
            existing = db.query(GmailToken).filter(
                GmailToken.user_id == user_id,
                GmailToken.email_account == email_account
            ).first()
            if existing:
                db.delete(existing)
                db.flush()

        gmail_token = GmailToken(
            user_id=user_id,
            email_account=email_account,
            access_token=token_data.get('access_token'),
            refresh_token=token_data.get('refresh_token'),
            token_type=token_data.get('token_type', 'Bearer'),
            expires_at=datetime.fromtimestamp(token_data.get('expires_at', 0)) if token_data.get('expires_at') else None
        )
        db.add(gmail_token)
        db.commit()
        db.refresh(gmail_token)
        logger.info(f"Saved Gmail token for user_id={user_id} account={email_account}")
        return gmail_token
    except Exception as e:
        db.rollback()
        logger.error(f"Error saving Gmail token: {e}")
        return None

def get_gmail_token(db: Session, user_id: int):
    """Get the first Gmail token for a user (backward compat)."""
    return db.query(GmailToken).filter(GmailToken.user_id == user_id).first()

def get_all_gmail_tokens(db: Session, user_id: int):
    """Get all Gmail tokens for a user."""
    return db.query(GmailToken).filter(GmailToken.user_id == user_id).all()

def update_user_activity(db: Session, user_id: int):
    """Update user's last activity timestamp"""
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        user.updated_at = datetime.utcnow()
        db.commit()
        return True
    return False
