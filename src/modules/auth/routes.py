import logging
from uuid import UUID

from coa_db_models.auth.models import User
from fastapi import APIRouter, BackgroundTasks, Depends, Query
from fastapi.responses import HTMLResponse, JSONResponse

from src.core.config import get_settings
from src.core.exceptions import AppError
from src.modules.auth.dependencies import (
    get_auth_service,
    get_client_org_service,
    get_current_user,
    get_invitation_service,
)
from src.modules.auth.email_service import _template_env
from src.modules.auth.invitation_service import InvitationService
from src.modules.auth.schemas import (
    ClientOrgCreate,
    ClientOrgResponse,
    ClientOrgUpdate,
    InvitationCreate,
    InvitationMessageResponse,
    InvitationResponse,
    LogoutRequest,
    MagicLinkRequest,
    MagicLinkResponse,
    MeResponse,
    OrgMemberResponse,
    OrgMembership,
    RefreshRequest,
    RegisterRequest,
    RegisterResponse,
    TokenResponse,
)
from src.modules.auth.service import AuthService, ClientOrgService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["auth"])
users_router = APIRouter(prefix="/api/v1/users", tags=["users"])
orgs_router = APIRouter(prefix="/api/v1/orgs", tags=["organizations"])


# --- Auth ---


@router.post("/auth/register", response_model=RegisterResponse, status_code=201)
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


@router.get("/auth/verify", response_class=HTMLResponse)
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


@router.post("/auth/login", response_model=MagicLinkResponse)
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


@router.get("/auth/magic-link", response_class=HTMLResponse)
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


@router.post("/auth/refresh", response_model=TokenResponse)
async def refresh(data: RefreshRequest, service: AuthService = Depends(get_auth_service)):
    try:
        return await service.refresh_tokens(refresh_token=data.refresh_token)
    except AppError:
        raise
    except Exception:
        logger.exception("Token refresh failed")
        return JSONResponse(status_code=500, content={"detail": "Token refresh failed"})


@router.post("/auth/logout")
async def logout(data: LogoutRequest, service: AuthService = Depends(get_auth_service)):
    try:
        return await service.logout(refresh_token=data.refresh_token)
    except AppError:
        raise
    except Exception:
        logger.exception("Logout failed")
        return JSONResponse(status_code=500, content={"detail": "Logout failed"})


@router.get("/auth/me", response_model=MeResponse)
async def me(user: User = Depends(get_current_user), service: AuthService = Depends(get_auth_service)):
    try:
        return await service.get_me(user)
    except AppError:
        raise
    except Exception:
        logger.exception("Failed to get user profile")
        return JSONResponse(status_code=500, content={"detail": "Failed to get user profile"})


# --- Invite acceptance (public, token-based) ---


@router.get("/auth/invite", response_class=HTMLResponse)
async def accept_invite(
    token: str = Query(...),
    service: InvitationService = Depends(get_invitation_service),
):
    try:
        result = await service.accept_invitation(token)
        if not result["success"]:
            html = _template_env.get_template("verify_error.html").render(error=result["error"])
            return HTMLResponse(content=html)

        redirect_url = result["redirect_url"]
        html = f"""<!DOCTYPE html>
<html><head><meta http-equiv="refresh" content="0;url={redirect_url}">
<script>window.location.href="{redirect_url}";</script>
</head><body>Redirecting...</body></html>"""
        return HTMLResponse(content=html)
    except Exception:
        logger.exception("Invite acceptance failed")
        html = _template_env.get_template("verify_error.html").render(error="Something went wrong")
        return HTMLResponse(content=html)


# --- Organization Invitations ---


@orgs_router.post(
    "/{org_id}/invitations",
    response_model=InvitationMessageResponse,
    status_code=201,
)
async def send_invitation(
    org_id: UUID,
    data: InvitationCreate,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    service: InvitationService = Depends(get_invitation_service),
):
    try:
        invitation = await service.send_invitation(
            org_id=org_id,
            email=data.email,
            role=data.role,
            current_user=user,
            background_tasks=background_tasks,
        )
        return InvitationMessageResponse(invitation_id=invitation.id, message="Invitation sent")
    except AppError:
        raise
    except Exception:
        logger.exception("Failed to send invitation for org %s", org_id)
        return JSONResponse(status_code=500, content={"detail": "Failed to send invitation"})


@orgs_router.get("/{org_id}/invitations", response_model=list[InvitationResponse])
async def list_invitations(
    org_id: UUID,
    user: User = Depends(get_current_user),
    service: InvitationService = Depends(get_invitation_service),
):
    try:
        return await service.list_invitations(org_id, user)
    except AppError:
        raise
    except Exception:
        logger.exception("Failed to list invitations for org %s", org_id)
        return JSONResponse(status_code=500, content={"detail": "Failed to list invitations"})


@orgs_router.delete("/{org_id}/invitations/{invitation_id}")
async def cancel_invitation(
    org_id: UUID,
    invitation_id: UUID,
    user: User = Depends(get_current_user),
    service: InvitationService = Depends(get_invitation_service),
):
    try:
        await service.cancel_invitation(org_id, invitation_id, user)
        return {"status": "cancelled"}
    except AppError:
        raise
    except Exception:
        logger.exception("Failed to cancel invitation %s", invitation_id)
        return JSONResponse(status_code=500, content={"detail": "Failed to cancel invitation"})


# --- Organization Members ---


@orgs_router.get("/{org_id}/members", response_model=list[OrgMemberResponse])
async def list_org_members(
    org_id: UUID,
    user: User = Depends(get_current_user),
    service: InvitationService = Depends(get_invitation_service),
):
    try:
        return await service.list_org_members(org_id, user)
    except AppError:
        raise
    except Exception:
        logger.exception("Failed to list members for org %s", org_id)
        return JSONResponse(status_code=500, content={"detail": "Failed to list members"})


@orgs_router.delete("/{org_id}/members/{user_id}")
async def remove_org_member(
    org_id: UUID,
    user_id: UUID,
    user: User = Depends(get_current_user),
    service: InvitationService = Depends(get_invitation_service),
):
    try:
        await service.remove_org_member(org_id, user_id, user)
        return {"status": "removed"}
    except AppError:
        raise
    except Exception:
        logger.exception("Failed to remove user %s from org %s", user_id, org_id)
        return JSONResponse(status_code=500, content={"detail": "Failed to remove member"})


# --- User's Organizations ---


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


# --- Client Orgs ---


@orgs_router.post("/{org_id}/clients", response_model=ClientOrgResponse, status_code=201)
async def create_client_org(
    org_id: UUID,
    data: ClientOrgCreate,
    user: User = Depends(get_current_user),
    service: ClientOrgService = Depends(get_client_org_service),
):
    try:
        return await service.create_client(org_id, data, user)
    except AppError:
        raise
    except Exception:
        logger.exception("Failed to create client org under employer %s", org_id)
        return JSONResponse(status_code=500, content={"detail": "Failed to create client organization"})


@orgs_router.get("/{org_id}/clients", response_model=list[ClientOrgResponse])
async def list_client_orgs(
    org_id: UUID,
    user: User = Depends(get_current_user),
    service: ClientOrgService = Depends(get_client_org_service),
):
    try:
        return await service.list_clients(org_id, user)
    except AppError:
        raise
    except Exception:
        logger.exception("Failed to list client orgs for employer %s", org_id)
        return JSONResponse(status_code=500, content={"detail": "Failed to list client organizations"})


@orgs_router.get("/{org_id}/clients/{client_id}", response_model=ClientOrgResponse)
async def get_client_org(
    org_id: UUID,
    client_id: UUID,
    user: User = Depends(get_current_user),
    service: ClientOrgService = Depends(get_client_org_service),
):
    try:
        return await service.get_client(org_id, client_id, user)
    except AppError:
        raise
    except Exception:
        logger.exception("Failed to get client org %s", client_id)
        return JSONResponse(status_code=500, content={"detail": "Failed to get client organization"})


@orgs_router.patch("/{org_id}/clients/{client_id}", response_model=ClientOrgResponse)
async def update_client_org(
    org_id: UUID,
    client_id: UUID,
    data: ClientOrgUpdate,
    user: User = Depends(get_current_user),
    service: ClientOrgService = Depends(get_client_org_service),
):
    try:
        return await service.update_client(org_id, client_id, data, user)
    except AppError:
        raise
    except Exception:
        logger.exception("Failed to update client org %s", client_id)
        return JSONResponse(status_code=500, content={"detail": "Failed to update client organization"})
