from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.s3_client import get_s3_client
from src.modules.storage.repository import FileRepository
from src.modules.storage.s3_provider import S3Provider
from src.modules.storage.service import StorageService


def get_storage_service(db: AsyncSession = Depends(get_db)) -> StorageService:
    s3_client = get_s3_client()
    store = S3Provider(s3_client) if s3_client else None
    return StorageService(store=store, file_repo=FileRepository(db), session=db)
