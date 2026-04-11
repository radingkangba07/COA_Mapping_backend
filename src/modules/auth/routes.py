import logging

from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.responses import HTMLResponse, JSONResponse

from src.core.config import get_settings
from src.core.exceptions import AppError
from src.modules.auth.dependencies import get_auth_service, get_current_user
from src.modules.auth.email_service import _template_env
from src.modules.auth.models import User
from src.modules.auth.schemas import LoginRequest, LoginResponse, RegisterRequest, RegisterResponse, UserResponse
from src.modules.auth.service import AuthService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/register", response_model=RegisterResponse, status_code=201)
async def register(
    data: RegisterRequest,
    background_tasks: BackgroundTasks,
    service: AuthService = Depends(get_auth_service),
):
    try:
        result = await service.register(
            name=data.name, email=data.email, org_name=data.org_name, background_tasks=background_tasks
        )
        return result
    except AppError:
        raise
    except Exception:
        logger.exception("Registration failed for email='%s'", data.email)
        return JSONResponse(status_code=500, content={"detail": "Registration failed"})


@router.get("/verify", response_class=HTMLResponse)
async def verify_email(token: str, service: AuthService = Depends(get_auth_service)):
    try:
        result = await service.verify_email(token)
        if result["success"]:
            html = _template_env.get_template("verify_success.html").render(
                message=result["message"],
                frontend_url=get_settings().frontend_url,
            )
        else:
            html = _template_env.get_template("verify_error.html").render(error=result["error"])
        return HTMLResponse(content=html)
    except Exception:
        logger.exception("Email verification failed")
        html = _template_env.get_template("verify_error.html").render(error="Something went wrong")
        return HTMLResponse(content=html)


@router.post("/login", response_model=LoginResponse)
async def login(data: LoginRequest, service: AuthService = Depends(get_auth_service)):
    try:
        return await service.login(user_id=data.user_id)
    except AppError:
        raise
    except Exception:
        logger.exception("Login failed for user_id='%s'", data.user_id)
        return JSONResponse(status_code=500, content={"detail": "Login failed"})


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user)):
    try:
        return UserResponse.from_user(user)
    except AppError:
        raise
    except Exception:
        logger.exception("Failed to get current user")
        return JSONResponse(status_code=500, content={"detail": "Failed to get user profile"})


@router.post("/logout")
async def logout():
    return {"success": True, "message": "Logged out"}
