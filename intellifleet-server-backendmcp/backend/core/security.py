from passlib.context import CryptContext
from backend.config.config import settings
from datetime import datetime, timedelta, timezone
import jwt
from backend.config.logger import logger
from typing import Optional
from fastapi import HTTPException, Request
 
BACKEND_URL = settings.BACKEND_URL
FRONTEND_URL = settings.FRONTEND_URL
 
# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
 

SECRET_KEY = settings.SECRET_KEY
ALGORITHM = settings.ALGORITHM or "HS256"

ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES or 20
TOKEN_EXPIRE_TIME_HOURS = settings.TOKEN_EXPIRE_TIME_HOURS or 24
 
# Configuration validation
def validate_config():
    """Validate that all required configuration is present"""
    if not SECRET_KEY:
        raise RuntimeError("SECRET_KEY is not set. Configure it in the backend .env file.")
 
# Validate configuration on module load
validate_config()
 
 
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(hours=TOKEN_EXPIRE_TIME_HOURS))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt
 
 
def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against hash"""
    return pwd_context.verify(plain_password, hashed_password)
 
def get_password_hash(password: str) -> str:
    """Create password hash"""
    return pwd_context.hash(password)
 
def get_current_user(request: Request) -> int:
    """Extract user_id from JWT token"""
    try:
        authorization = request.headers.get("Authorization")
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="No valid token provided")
 
        token = authorization.split(" ")[1]
        # Decode token to get user info
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:  # Updated: Use imported exception directly
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:  # Updated: Use imported exception directly
        raise HTTPException(status_code=401, detail="Invalid token")
    except Exception as e:
        logger.error(f"Error extracting user_id from token: {str(e)}")
        raise HTTPException(status_code=401, detail="Token validation failed")
