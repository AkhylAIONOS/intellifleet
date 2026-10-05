# auth.py

from datetime import timedelta, datetime, timezone
from pydantic import BaseModel, EmailStr, Field, field_validator
from fastapi import Depends
from contextlib import closing
import secrets
import jwt
from fastapi import status
from fastapi import APIRouter
from backend.config.logger import logger
from fastapi.responses import JSONResponse, RedirectResponse
from backend.database.database import *
from fastapi.security import HTTPBearer
from backend.utilities.email import send_email
from ..core.security import *
from ..models.userSchema import *

router = APIRouter(prefix="/auth", tags=["Authentication"])
security = HTTPBearer()    


class DemoIdentityInput(BaseModel):
    name: str = Field(default='', max_length=120)
    email: EmailStr

    @field_validator('email', mode='before')
    @classmethod
    def normalize_email(cls, value):
        return value.strip().lower() if isinstance(value,str) else value


def ensure_login_fields(conn):
    columns={row[1] for row in conn.execute('PRAGMA table_info(users)')}
    for name,kind in [('name','TEXT'),('created_at','TEXT'),('first_login_at','TEXT'),('last_login_at','TEXT'),('login_count','INTEGER NOT NULL DEFAULT 0')]:
        if name not in columns:
            conn.execute(f'ALTER TABLE users ADD COLUMN {name} {kind}')
    conn.execute("UPDATE users SET name=trim(first_name || ' ' || last_name) WHERE name IS NULL")
    conn.execute("UPDATE users SET created_at=CURRENT_TIMESTAMP WHERE created_at IS NULL")


@router.post("/demo-access")
async def demo_access(identity: DemoIdentityInput):
    """Temporary email-identity demo login; not production-secure authentication."""
    if not settings.DEMO_ACCESS_ENABLED:
        raise HTTPException(status_code=403, detail="Demo access is disabled")
    email=str(identity.email).lower()
    now=datetime.now(timezone.utc).isoformat()
    with closing(get_db_connection()) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        ensure_login_fields(conn)
        user=conn.execute('SELECT * FROM users WHERE lower(email)=? ORDER BY id LIMIT 1',(email,)).fetchone()
        if user is None:
            name=identity.name.strip()
            if not name:
                raise HTTPException(400,'Name is required for a new account')
            first,_,last=name.partition(' ')
            # Existing schema requires a password hash; this is an unknowable
            # compatibility value, never a user password or login mechanism.
            conn.execute('INSERT INTO users(first_name,last_name,name,email,password,verified,created_at,first_login_at,last_login_at,login_count) VALUES(?,?,?,?,?,1,?,?,?,1)',
                (first,last,name,email,get_password_hash(secrets.token_urlsafe(32)),now,now,now))
        else:
            conn.execute('UPDATE users SET first_login_at=COALESCE(first_login_at,?),last_login_at=?,login_count=login_count+1 WHERE id=?',(now,now,user['id']))
        user=conn.execute('SELECT * FROM users WHERE lower(email)=? ORDER BY id LIMIT 1',(email,)).fetchone()
        public_user={key:user[key] for key in ('id','name','first_name','last_name','email')}
        public_user['email']=email
    token=create_access_token({'user_id':public_user['id'],**{key:value for key,value in public_user.items() if key!='id'}})
    return {'success':True,'data':{'token':token,'user':public_user}}


@router.get('/users')
def logged_in_users(current_user=Depends(get_current_user)):
    allowed={email.strip().lower() for email in settings.UNIFLEET_ADMIN_EMAILS.split(',') if email.strip()}
    with closing(get_db_connection()) as conn,conn:
        user=conn.execute('SELECT email FROM users WHERE id=?',(current_user.get('user_id'),)).fetchone()
        if not user or user['email'].strip().lower() not in allowed:
            raise HTTPException(403,'Unauthorized')
        ensure_login_fields(conn)
        rows=conn.execute('SELECT name,email,first_login_at,last_login_at,login_count FROM users WHERE first_login_at IS NOT NULL ORDER BY last_login_at DESC,id DESC').fetchall()
    return {'users':[dict(row) for row in rows]}

# ======================
# ✅ SIGNUP
# ======================


@router.post("/signup", status_code=status.HTTP_201_CREATED)
async def create_user_endpoint(user: UserCreate):
    try:
        # ✅ Validate required fields
        if not user.email or not user.password:
            return JSONResponse(
                status_code=200,
                content={
                    "success": False,
                    "message": "All required fields must be provided",
                    "error": "Missing required fields",
                },
            )

        # ✅ Check if user already exists
        existing_user = get_user_by_email(user.email)
        if existing_user:
            return JSONResponse(
                status_code=200,
                content={
                    "success": False,
                    "message": "Email already registered",
                    "error": "Duplicate email",
                },
            )

        hashed_pw = get_password_hash(user.password)
        token = create_access_token({
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
            "password": hashed_pw
        }, expires_delta=timedelta(minutes=120))

        verify_link = f"{BACKEND_URL}/auth/verify-email?token={token}"

        await send_email(
            to=user.email,
            subject="Verify your email address",
            body=f"Click the link to verify your account:\n\n{verify_link}\n\nLink expires in 2 HOURS."
        )

        return JSONResponse(
            status_code=200,
            content={
                "success": True, 
                "message": f"Verification email sent to {user.email}",
                "first_name": user.first_name,
                "last_name": user.last_name
            }
        )

    except Exception as e:
        logger.error(f"Signup error: {e}")
        return JSONResponse(status_code=500, content={"success": False, "message": "Internal server error"})


# ======================
# ✅ VERIFY EMAIL
# ======================

@router.get("/verify-email")
async def verify_email(token: str):
    try:
        # ✅ Decode the JWT token
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("email")

        if not email:
            return JSONResponse(
                status_code=400,
                content={"success": False, "message": "Invalid verification link"}
            )

        existing_user = get_user_by_email(email)
        if existing_user:
            return RedirectResponse(f"{FRONTEND_URL}/?verified=true", status_code=303)
        
        create_user({
            "first_name": payload["first_name"],
            "last_name": payload["last_name"],
            "email": payload["email"],
            "password": payload["password"],
            "verified": True
        })

        logger.info(f"User verified and created: {email}")

        # ✅ Redirect user to frontend (sign-in page)
        return RedirectResponse(f"{FRONTEND_URL}/?verified=true", status_code=303)

    except jwt.ExpiredSignatureError:
        logger.warning("Verification link expired")
        return RedirectResponse(f"{FRONTEND_URL}/?verified=false", status_code=303)
    except jwt.InvalidTokenError:
        logger.warning("Invalid verification token")
        return RedirectResponse(f"{FRONTEND_URL}/?verified=false", status_code=303)
    except Exception as e:
        logger.error(f"Verification error: {e}")
        return RedirectResponse(f"{FRONTEND_URL}/?verified=false", status_code=303)


    
# ======================
# ✅ SIGNIN
# ======================
@router.post("/signin", status_code=status.HTTP_200_OK)
async def login_for_access_token(payload: LoginRequest):
    try:
        # ✅ Validate input
        if not payload.email or not payload.password:
            return JSONResponse(
                status_code=200,
                content={
                    "success": False,
                    "message": "Please provide both email and password to continue."
                }
            )

        # ✅ Check user existence
        user = get_user_by_email(payload.email)
        if not user:
            return JSONResponse(
                status_code=200,
                content={
                    "success": False,
                    "message": "No account found with this email. Please sign up to continue."
                }
            )

        if not user.get("verified"):
            return JSONResponse(
                status_code=200,
                content={"success": False, "message": "Please verify your email before signing in."}
            )

        # ✅ Check if user has password
        if not user.get("password"):
            return JSONResponse(
                status_code=200,
                content={
                    "success": False,
                    "message": "Invalid account configuration. Please contact support."
                }
            )

        # ✅ Verify password
        if not verify_password(payload.password, user["password"]):
            return JSONResponse(
                status_code=200,
                content={
                    "success": False,
                    "message": "Login failed. Please check your credentials and try again."
                }
            )

        # ✅ Create access token with user_id
        access_token = create_access_token(
            data={
                "user_id": user["id"],  # Include user_id in token
                "first_name": user["first_name"],
                "last_name": user["last_name"],
                "email": user["email"],
            },
            expires_delta=timedelta(hours=TOKEN_EXPIRE_TIME_HOURS),
        )

        logger.info(f"User logged in successfully: {user['email']}")

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "user": f"{user['first_name']} {user['last_name']}",
                "message": "You have successfully logged in.",
                "data": {
                    "first_name": user["first_name"],
                    "last_name": user["last_name"],
                    "token": access_token
                },
            },
        )

    except Exception as e:
        logger.error(f"Unexpected error during login: {str(e)}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "success": False,
                "message": "An unexpected error occurred. Please try again later."
            },
        )

# ======================
# ✅ Get Current User (Optional - for frontend to validate token)
# ======================
# @router.get("/me", status_code=status.HTTP_200_OK)
# async def get_current_user(request: Request):
#     try:
#         user_id = get_current_user_id(request)
        
#         # ✅ Get user from database
#         user = get_user_by_id(user_id)
#         if not user:
#             return JSONResponse(
#                 status_code=200,
#                 content={
#                     "success": False,
#                     "message": "User not found"
#                 }
#             )

#         return JSONResponse(
#             status_code=200,
#             content={
#                 "success": True,
#                 "data": {
#                     "user": {
#                         "id": user["id"],
#                         "first_name": user["first_name"],
#                         "last_name": user["last_name"],
#                         "email": user["email"],
#                         "provider": "email"
#                     }
#                 }
#             }
#         )

#     except HTTPException as e:
#         logger.error(f"Get current user error: {str(e)}")
#         return JSONResponse(
#             status_code=200,
#             content={
#                 "success": False,
#                 "message": "An error occurred while fetching user data"
#             }
#         )
#     except Exception as e:
#         logger.error(f"Get current user error: {str(e)}")
#         return JSONResponse(
#             status_code=200,
#             content={
#                 "success": False,
#                 "message": "An error occurred while fetching user data"
#             }
#         )
