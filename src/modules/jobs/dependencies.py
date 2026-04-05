from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.nats_client import get_jetstream
from src.modules.jobs.publisher import NATSPublisher
from src.modules.jobs.repository import JobRepository
from src.modules.jobs.service import JobService


def get_job_service(db: AsyncSession = Depends(get_db)) -> JobService:
    js = get_jetstream()
    publisher = NATSPublisher(js) if js else None
    return JobService(job_repo=JobRepository(db), session=db, publisher=publisher)
