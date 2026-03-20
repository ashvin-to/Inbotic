from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
import os
import hashlib
import bcrypt
import secrets
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    # If python-dotenv isn't installed or .env missing, skip
    pass

def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


# JWT settings (configurable via environment)
SECRET_KEY = _require_env("SECRET_KEY")
# Optional alternate key to support key rotation during verification
DECODER_SECRET_KEY = os.getenv("DECODER_SECRET_KEY", SECRET_KEY).strip() or SECRET_KEY
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

def _is_bcrypt_hash(hashed: str) -> bool:
    """Heuristically check if a stored hash is a bcrypt hash."""
    # bcrypt hashes typically start with $2b$, $2a$, or $2y$
    return isinstance(hashed, str) and hashed.startswith(("$2b$", "$2a$", "$2y$"))

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash.

    Supports both bcrypt (preferred) and legacy SHA-256 hashes that may exist
    if users were created before bcrypt was installed.
    """
    if not isinstance(hashed_password, str):
        return False

    # If the stored hash looks like bcrypt, verify with bcrypt
    if _is_bcrypt_hash(hashed_password):
        try:
            return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
        except Exception:
            # Fall through to False if the hash is malformed
            return False

    # Otherwise, treat it as legacy SHA-256
    legacy_sha256 = hashlib.sha256(plain_password.encode()).hexdigest()
    return legacy_sha256 == hashed_password

def get_password_hash(password: str) -> str:
    """Hash a password using bcrypt, with SHA-256 fallback."""
    try:
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
        return hashed.decode("utf-8")
    except Exception:
        # Fallback for environments without bcrypt (legacy behavior)
        return hashlib.sha256(password.encode()).hexdigest()

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """Create a JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_token(token: str) -> Optional[str]:
    """Verify a JWT token and return the username.

    Tries SECRET_KEY first; if it fails and DECODER_SECRET_KEY differs, tries that
    as a fallback to support secret rotation.
    """
    keys_to_try = [SECRET_KEY]
    if DECODER_SECRET_KEY and DECODER_SECRET_KEY != SECRET_KEY:
        keys_to_try.append(DECODER_SECRET_KEY)

    for key in keys_to_try:
        try:
            payload = jwt.decode(token, key, algorithms=[ALGORITHM])
            username: str = payload.get("sub")
            if username is None:
                return None
            return username
        except JWTError:
            continue
    return None
