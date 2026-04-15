import logging
import urllib.parse

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status
from fastapi.responses import HTMLResponse, JSONResponse

from src.core.config import get_settings
from src.core.exceptions import AppError
from src.modules.auth.dependencies import get_auth_service, get_current_user
from src.modules.auth.email_service import _template_env
from src.modules.auth.models import User
from src.modules.auth.schemas import (
    InviteRequest,
    LogoutRequest,
    MagicLinkRequest,
    MagicLinkResponse,
    MeResponse,
    OrgInvitationResponse,
    OrgMemberResponse,
    OrgMembership,
    RefreshRequest,
    RegisterRequest,
    RegisterResponse,
    TokenResponse,
)
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


@router.post("/login", response_model=MagicLinkResponse)
async def login(
    data: MagicLinkRequest,
    background_tasks: BackgroundTasks,
    service: AuthService = Depends(get_auth_service),
):
    try:
        return await service.request_magic_link(
            email=data.email,
            background_tasks=background_tasks,
        )
    except AppError:
        raise
    except Exception:
        logger.exception("Login failed for email='%s'", data.email)
        return JSONResponse(status_code=500, content={"detail": "Login failed"})


@router.get("/magic-link", response_class=HTMLResponse)
async def magic_link(token: str = Query(...), service: AuthService = Depends(get_auth_service)):
    try:
        result = await service.verify_magic_link(token)
        if not result["success"]:
            html = _template_env.get_template("verify_error.html").render(error=result["error"])
            return HTMLResponse(content=html)

        settings = get_settings()
        redirect_url = (
            f"{settings.frontend_url}/auth/callback"
            f"?access_token={result['access_token']}"
            f"&refresh_token={result['refresh_token']}"
        )
        html = f"""<!DOCTYPE html>
<html><head><meta http-equiv="refresh" content="0;url={redirect_url}">
<script>window.location.href="{redirect_url}";</script>
</head><body>Redirecting...</body></html>"""
        return HTMLResponse(content=html)
    except Exception:
        logger.exception("Magic link verification failed")
        html = _template_env.get_template("verify_error.html").render(error="Something went wrong")
        return HTMLResponse(content=html)


@router.get("/invite", response_class=HTMLResponse)
async def accept_invitation(token: str = Query(...), service: AuthService = Depends(get_auth_service)):
    try:
        result = await service.accept_invitation(token)
        if not result["success"]:
            html = _template_env.get_template("verify_error.html").render(error=result["error"])
            return HTMLResponse(content=html)

        settings = get_settings()
        if result["action"] == "redirect_to_signup":
            encoded_email = urllib.parse.quote(result["email"])
            redirect_url = f"{settings.frontend_url}/auth/signup?invite_token={result['token']}&email={encoded_email}"
        else:
            redirect_url = (
                f"{settings.frontend_url}/auth/callback"
                f"?access_token={result['access_token']}"
                f"&refresh_token={result['refresh_token']}"
            )

        html = f"""<!DOCTYPE html>
<html><head><meta http-equiv="refresh" content="0;url={redirect_url}">
<script>window.location.href="{redirect_url}";</script>
</head><body>Redirecting...</body></html>"""
        return HTMLResponse(content=html)
    except Exception:
        logger.exception("Invitation acceptance failed")
        html = _template_env.get_template("verify_error.html").render(error="Something went wrong")
        return HTMLResponse(content=html)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(data: RefreshRequest, service: AuthService = Depends(get_auth_service)):
    try:
        return await service.refresh_tokens(refresh_token=data.refresh_token)
    except AppError:
        raise
    except Exception:
        logger.exception("Token refresh failed")
        return JSONResponse(status_code=500, content={"detail": "Token refresh failed"})


@router.post("/logout")
async def logout(data: LogoutRequest, service: AuthService = Depends(get_auth_service)):
    try:
        return await service.logout(refresh_token=data.refresh_token)
    except AppError:
        raise
    except Exception:
        logger.exception("Logout failed")
        return JSONResponse(status_code=500, content={"detail": "Logout failed"})


@router.get("/me", response_model=MeResponse)
async def me(user: User = Depends(get_current_user), service: AuthService = Depends(get_auth_service)):
    try:
        return await service.get_me(user)
    except AppError:
        raise
    except Exception:
        logger.exception("Failed to get user profile")
        return JSONResponse(status_code=500, content={"detail": "Failed to get user profile"})


users_router = APIRouter(prefix="/api/v1/users", tags=["users"])
orgs_router = APIRouter(prefix="/api/v1/orgs", tags=["organizations"])


@users_router.get("/me/orgs", response_model=list[OrgMembership])
async def get_my_orgs(
    user: User = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
):
    try:
        return await service.get_user_orgs(user)
    except AppError:
        raise
    except Exception:
        logger.exception("Failed to get user orgs")
        return JSONResponse(status_code=500, content={"detail": "Failed to get user orgs"})


@orgs_router.get("/{org_id}/members", response_model=list[OrgMemberResponse])
async def get_org_members(
    org_id: str,
    user: User = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
):
    try:
        return await service.get_org_members(org_id=org_id, user=user)
    except AppError:
        raise
    except Exception:
        logger.exception("Failed to get org members for org_id=%s", org_id)
        return JSONResponse(status_code=500, content={"detail": "Failed to get org members"})


@orgs_router.get("/{org_id}/invitations", response_model=list[OrgInvitationResponse])
async def get_org_invitations(
    org_id: str,
    user: User = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
):
    try:
        return await service.get_org_invitations(org_id=org_id, user=user)
    except AppError:
        raise
    except Exception:
        logger.exception("Failed to get org invitations for org_id=%s", org_id)
        return JSONResponse(status_code=500, content={"detail": "Failed to get org invitations"})


@orgs_router.post("/{org_id}/invitations", response_model=OrgInvitationResponse, status_code=status.HTTP_201_CREATED)
async def create_org_invitation(
    org_id: str,
    data: InviteRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
):
    try:
        return await service.invite_to_org(
            org_id=org_id, email=data.email, role=data.role, user=user, background_tasks=background_tasks
        )
    except AppError:
        raise
    except Exception:
        logger.exception("Failed to create invitation for org_id=%s", org_id)
        return JSONResponse(status_code=500, content={"detail": "Failed to create invitation"})


@orgs_router.delete("/{org_id}/invitations/{invitation_id}")
async def cancel_org_invitation(
    org_id: str,
    invitation_id: str,
    user: User = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
):
    try:
        return await service.cancel_invitation(org_id=org_id, invitation_id=invitation_id, user=user)
    except AppError:
        raise
    except Exception:
        logger.exception("Failed to cancel invitation %s for org_id=%s", invitation_id, org_id)
        return JSONResponse(status_code=500, content={"detail": "Failed to cancel invitation"})
