from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from database import User, GmailToken
from auth import get_password_hash, verify_password
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

def create_user(db: Session, email: str, username: str, password: str):
    """Create a new user"""
    try:
        hashed_password = get_password_hash(password)
        db_user = User(
            email=email,
            username=username,
            hashed_password=hashed_password
        )
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        logger.info(f"Created new user: {username} ({email})")
        return db_user
    except IntegrityError:
        db.rollback()
        logger.error(f"User creation failed - email or username already exists: {email}")
        return None

def authenticate_user(db: Session, username: str, password: str):
    """Authenticate a user"""
    user = db.query(User).filter(User.username == username).first()
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user

def get_user_by_username(db: Session, username: str):
    """Get user by username"""
    return db.query(User).filter(User.username == username).first()

def get_user_by_email(db: Session, email: str):
    """Get user by email"""
    return db.query(User).filter(User.email == email).first()

def get_user_by_id(db: Session, user_id: int):
    """Get user by ID"""
    return db.query(User).filter(User.id == user_id).first()

def save_gmail_token(db: Session, user_id: int, token_data: dict):
    """Save or update Gmail token for a user"""
    try:
        # Remove existing tokens for this user
        db.query(GmailToken).filter(GmailToken.user_id == user_id).delete()

        # Create new token
        gmail_token = GmailToken(
            user_id=user_id,
            access_token=token_data.get('access_token'),
            refresh_token=token_data.get('refresh_token'),
            token_type=token_data.get('token_type', 'Bearer'),
            expires_at=datetime.fromtimestamp(token_data.get('expires_at', 0)) if token_data.get('expires_at') else None
        )
        db.add(gmail_token)
        db.commit()
        db.refresh(gmail_token)
        logger.info(f"Saved Gmail token for user_id: {user_id}")
        return gmail_token
    except Exception as e:
        db.rollback()
        logger.error(f"Error saving Gmail token: {e}")
        return None

def get_gmail_token(db: Session, user_id: int):
    """Get Gmail token for a user"""
    return db.query(GmailToken).filter(GmailToken.user_id == user_id).first()

def update_user_activity(db: Session, user_id: int):
    """Update user's last activity timestamp"""
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        user.updated_at = datetime.utcnow()
        db.commit()
        return True
    return False
