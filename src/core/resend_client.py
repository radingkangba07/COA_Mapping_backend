import logging

import resend

from src.core.config import get_settings

logger = logging.getLogger(__name__)

_resend_initialized = False


def init_resend() -> None:
    global _resend_initialized
    settings = get_settings()
    if not settings.resend_api_key:
        logger.info("RESEND_API_KEY not set, email sending disabled")
        return
    resend.api_key = settings.resend_api_key
    _resend_initialized = True
    logger.info("Resend email client initialized")


def close_resend() -> None:
    global _resend_initialized
    _resend_initialized = False


def is_resend_available() -> bool:
    return _resend_initialized
