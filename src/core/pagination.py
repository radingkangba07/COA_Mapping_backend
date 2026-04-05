from typing import Generic, TypeVar

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

T = TypeVar("T")


class PaginationParams(BaseModel):
    skip: int = Field(default=0, ge=0)
    limit: int = Field(default=50, ge=1, le=100)


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    skip: int
    limit: int


async def paginate(
    session: AsyncSession,
    query: Select,
    params: PaginationParams,
) -> dict:
    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await session.execute(count_query)
    total = total_result.scalar_one()

    # Fetch page
    result = await session.execute(query.offset(params.skip).limit(params.limit))
    items = list(result.scalars().all())

    return {"items": items, "total": total, "skip": params.skip, "limit": params.limit}
