import asyncio
import logging

import nats
from nats.js import JetStreamContext
from nats.js.api import RetentionPolicy, StreamConfig

logger = logging.getLogger(__name__)

_nc: nats.NATS | None = None
_js: JetStreamContext | None = None

MAX_RETRIES = 3
BASE_BACKOFF_SECONDS = 1


async def _nats_error_cb(e: Exception) -> None:
    logger.debug("NATS error (non-critical): %s", e)


async def connect_nats(url: str, stream_name: str = "COA_JOBS") -> None:
    global _nc, _js
    if not url:
        logger.info("NATS_URL not set, job queue disabled (sync fallback)")
        return

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
            # Ensure stream exists
            from src.core.config import get_settings

            settings = get_settings()
            try:
                await _js.find_stream_info_by_subject(settings.nats_subject_job_run)  # type: ignore[attr-defined]
            except Exception:
                await _js.add_stream(
                    StreamConfig(
                        name=stream_name,
                        subjects=["jobs.mapping.*"],
                        retention=RetentionPolicy.WORK_QUEUE,
                        max_age=86400,  # 24h in seconds
                    )
                )
            logger.info("Connected to NATS at %s (stream=%s)", url, stream_name)
            return
        except Exception as exc:
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
            else:
                logger.warning(
                    "NATS connection failed after %d attempts — sync fallback",
                    MAX_RETRIES,
                )


async def close_nats() -> None:
    global _nc, _js
    if _nc:
        await _nc.close()
    _nc = None
    _js = None


def get_jetstream() -> JetStreamContext | None:
    return _js


def is_nats_available() -> bool:
    return _js is not None
