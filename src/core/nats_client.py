import asyncio
import logging

import nats
from nats.js import JetStreamContext
from nats.js.api import RetentionPolicy, StreamConfig
from nats.js.errors import NotFoundError

logger = logging.getLogger(__name__)

_nc: nats.NATS | None = None
_js: JetStreamContext | None = None

MAX_RETRIES = 3
BASE_BACKOFF_SECONDS = 1

_RETENTION_BY_NAME = {
    "workqueue": RetentionPolicy.WORK_QUEUE,
    "limits": RetentionPolicy.LIMITS,
    "interest": RetentionPolicy.INTEREST,
}


async def _nats_error_cb(e: Exception) -> None:
    logger.debug("NATS error (non-critical): %s", e)


def _build_stream_config(name: str, subjects: list[str], retention_name: str, max_age_seconds: int) -> StreamConfig:
    retention = _RETENTION_BY_NAME.get(retention_name.lower())
    if retention is None:
        raise ValueError(
            f"Invalid nats_stream_retention {retention_name!r}; expected one of {sorted(_RETENTION_BY_NAME)}"
        )
    return StreamConfig(
        name=name,
        subjects=subjects,
        retention=retention,
        max_age=max_age_seconds,
    )


async def _ensure_stream(js: JetStreamContext, desired: StreamConfig) -> None:
    """Idempotent: create the stream if missing, update if config has drifted, else leave alone."""
    try:
        existing = await js.stream_info(desired.name)  # type: ignore[arg-type]
    except NotFoundError:
        await js.add_stream(desired)
        logger.info("NATS stream %s created", desired.name)
        return

    current = existing.config
    if (
        list(current.subjects or []) != list(desired.subjects or [])
        or current.retention != desired.retention
        or current.max_age != desired.max_age
    ):
        await js.update_stream(desired)
        logger.warning("NATS stream %s config drifted from code, updated in place", desired.name)


async def connect_nats(url: str, stream_name: str) -> None:
    global _nc, _js
    if not url:
        raise RuntimeError("NATS_URL is not set; NATS is required and has no fallback")

    from src.core.config import get_settings

    settings = get_settings()
    desired = _build_stream_config(
        name=stream_name,
        subjects=settings.nats_stream_subjects,
        retention_name=settings.nats_stream_retention,
        max_age_seconds=settings.nats_stream_max_age_seconds,
    )

    last_exc: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            _nc = await nats.connect(
                url,
                max_reconnect_attempts=2,
                reconnect_time_wait=1,
                connect_timeout=5,
                error_cb=_nats_error_cb,
            )
            _js = _nc.jetstream()
            await _ensure_stream(_js, desired)
            logger.info("Connected to NATS at %s (stream=%s)", url, stream_name)
            return
        except Exception as exc:
            last_exc = exc
            _nc = None
            _js = None
            if attempt < MAX_RETRIES:
                wait = BASE_BACKOFF_SECONDS * (2 ** (attempt - 1))
                logger.warning(
                    "NATS connection attempt %d/%d failed: %s — retrying in %ds",
                    attempt,
                    MAX_RETRIES,
                    exc,
                    wait,
                )
                await asyncio.sleep(wait)

    logger.exception("NATS connection failed after %d attempts", MAX_RETRIES)
    raise RuntimeError(f"Failed to connect to NATS at {url} after {MAX_RETRIES} attempts") from last_exc


async def close_nats() -> None:
    global _nc, _js
    if _nc:
        await _nc.close()
    _nc = None
    _js = None


def get_jetstream() -> JetStreamContext:
    if _js is None:
        raise RuntimeError("NATS JetStream is not connected; call connect_nats() first")
    return _js
