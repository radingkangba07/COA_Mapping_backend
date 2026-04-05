import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from src.modules.auth.dependencies import get_auth_service, get_current_user
from src.modules.auth.models import User
from src.modules.auth.schemas import LoginRequest, LoginResponse, UserResponse
from src.modules.auth.service import AuthService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(data: LoginRequest, service: AuthService = Depends(get_auth_service)):
    try:
        return await service.login(user_id=data.user_id)
    except Exception:
        logger.exception("Login failed for user_id='%s'", data.user_id)
        return JSONResponse(status_code=500, content={"detail": "Login failed"})


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user)):
    try:
        return UserResponse.from_user(user)
    except Exception:
        logger.exception("Failed to get current user")
        return JSONResponse(status_code=500, content={"detail": "Failed to get user profile"})


@router.post("/logout")
async def logout():
    return {"success": True, "message": "Logged out"}
