import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from src.core.exceptions import AppError
from src.modules.auth.dependencies import get_auth_service, get_current_user
from src.modules.auth.models import User
from src.modules.auth.schemas import LoginRequest, LoginResponse, RegisterRequest, RegisterResponse, UserResponse
from src.modules.auth.service import AuthService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/register", response_model=RegisterResponse, status_code=201)
async def register(data: RegisterRequest, service: AuthService = Depends(get_auth_service)):
    try:
        return await service.register(name=data.name, email=data.email, org_name=data.org_name)
    except AppError:
        raise
    except Exception:
        logger.exception("Registration failed for email='%s'", data.email)
        return JSONResponse(status_code=500, content={"detail": "Registration failed"})


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
