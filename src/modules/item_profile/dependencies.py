from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.s3_client import get_s3_client
from src.modules.item_profile.publisher import ItemProfilePublisher
from src.modules.item_profile.repository import (
    ItemFieldProfileRepository,
    ItemProfileDecisionRepository,
    ItemProfileRunRepository,
)
from src.modules.item_profile.service import ItemProfileService
from src.modules.storage.s3_provider import S3Provider


def get_item_profile_service(db: AsyncSession = Depends(get_db)) -> ItemProfileService:
    s3_client = get_s3_client()
    store = S3Provider(s3_client) if s3_client else None

    publisher: ItemProfilePublisher | None = None
    try:
        from src.core.nats_client import get_jetstream
        publisher = ItemProfilePublisher(get_jetstream())
    except RuntimeError:
        pass

    return ItemProfileService(
        run_repo=ItemProfileRunRepository(db),
        store=store,
        publisher=publisher,
        session=db,
    )


def get_run_repo(db: AsyncSession = Depends(get_db)) -> ItemProfileRunRepository:
    return ItemProfileRunRepository(db)


def get_field_repo(db: AsyncSession = Depends(get_db)) -> ItemFieldProfileRepository:
    return ItemFieldProfileRepository(db)


def get_decision_repo(db: AsyncSession = Depends(get_db)) -> ItemProfileDecisionRepository:
    return ItemProfileDecisionRepository(db)
