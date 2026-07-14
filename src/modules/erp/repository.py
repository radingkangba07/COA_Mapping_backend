from coa_db_models.erp.models import ErpProduct
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class ErpProductRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_unique_vendors(self) -> list[str]:
        result = await self._db.execute(
            select(ErpProduct.vendor).distinct().order_by(ErpProduct.vendor)
        )
        return list(result.scalars())

    async def get_products_by_vendor(self, vendor: str) -> list[ErpProduct]:
        result = await self._db.execute(
            select(ErpProduct)
            .where(ErpProduct.vendor == vendor)
            .order_by(ErpProduct.product_name)
        )
        return list(result.scalars())

    async def get_product(self, product_id: str) -> ErpProduct | None:
        result = await self._db.execute(
            select(ErpProduct).where(ErpProduct.id == product_id)
        )
        return result.scalar_one_or_none()
