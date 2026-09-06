# auth.py

from datetime import timedelta
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


@router.post("/demo-access")
async def demo_access():
    if not settings.DEMO_ACCESS_ENABLED:
        raise HTTPException(status_code=403, detail="Demo access is disabled")

    # The canonical user schema requires a password column. Use an unknowable
    # random password hash; visitors never supply credentials or receive it.
    with closing(get_db_connection()) as conn, conn:
        user = conn.execute("SELECT * FROM users WHERE email=?", ("demo@unifleet.local",)).fetchone()
        if user is None:
            conn.execute(
                "INSERT OR IGNORE INTO users(first_name,last_name,email,password,verified) VALUES(?,?,?,?,1)",
                ("UniFleet", "Demo", "demo@unifleet.local", get_password_hash(secrets.token_urlsafe(32))),
            )
            user = conn.execute("SELECT * FROM users WHERE email=?", ("demo@unifleet.local",)).fetchone()
        public_user = {key: user[key] for key in ("id", "first_name", "last_name", "email")}

    token = create_access_token({"user_id": public_user["id"],
                                 **{key: value for key, value in public_user.items() if key != "id"}})
    return {"success": True, "data": {"token": token, "user": public_user}}

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
