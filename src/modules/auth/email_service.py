import asyncio
import logging
from pathlib import Path

import jinja2
import resend

from src.core.config import get_settings
from src.core.resend_client import is_resend_available

logger = logging.getLogger(__name__)

_template_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(Path(__file__).parent / "templates"),
    autoescape=True,
)


class EmailService:
    def __init__(self) -> None:
        self.settings = get_settings()

    async def _send_email(self, to: str, subject: str, html: str) -> None:
        if not is_resend_available():
            logger.info("Email sending disabled. Would send to=%s subject='%s'", to, subject)
            return
        try:
            await asyncio.to_thread(
                resend.Emails.send,
                {
                    "from": self.settings.from_email,
                    "to": [to],
                    "subject": subject,
                    "html": html,
                },
            )
            logger.info("Email sent to=%s subject='%s'", to, subject)
        except Exception:
            logger.exception("Failed to send email to=%s subject='%s'", to, subject)

    async def send_verification_email(self, to: str, name: str, token: str) -> None:
        verification_url = f"{self.settings.app_url}/api/v1/auth/verify?token={token}"
        if not is_resend_available():
            logger.info("Verification URL for %s: %s", to, verification_url)
        html = _template_env.get_template("verification.html").render(
            name=name,
            verification_url=verification_url,
            app_name="COA Migration Platform",
        )
        await self._send_email(to, "Verify your email address", html)

    async def send_magic_link_email(self, to: str, name: str, token: str) -> None:
        magic_link_url = f"{self.settings.app_url}/api/v1/auth/magic-link?token={token}"
        if not is_resend_available():
            logger.info("Magic link URL for %s: %s", to, magic_link_url)
        html = _template_env.get_template("magic_link.html").render(
            name=name,
            magic_link_url=magic_link_url,
            app_name="COA Migration Platform",
            expires_minutes=15,
        )
        await self._send_email(to, "Your sign-in link", html)

    async def send_invite_email(self, to: str, inviter_name: str, org_name: str, token: str) -> None:
        invite_url = f"{self.settings.app_url}/api/v1/auth/invite?token={token}"
        if not is_resend_available():
            logger.info("Invite URL for %s: %s", to, invite_url)
        html = _template_env.get_template("invitation.html").render(
            inviter_name=inviter_name,
            org_name=org_name,
            invite_url=invite_url,
            app_name="COA Migration Platform",
        )
        await self._send_email(to, f"You've been invited to {org_name}", html)
