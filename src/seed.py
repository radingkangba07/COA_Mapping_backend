"""Seed initial demo data into PostgreSQL. Run once after first setup.
Usage:
    uv run python -m src.seed
"""

import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.core.config import get_settings
from src.core.database import Base
from src.modules.auth.models import User
from src.modules.mappings.models import Mapping
from src.modules.projects.models import Company, Project, ProjectAccess

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def seed(session: AsyncSession) -> None:
    # Check if data already exists
    result = await session.execute(select(User))
    if result.scalars().first():
        logger.info("Database already has data, skipping seed")
        return

    # Users
    admin = User(user_id="admin", email="admin@company.com", name="Admin User")
    john = User(user_id="john.doe", email="john.doe@acme.com", name="John Doe")
    jane = User(user_id="jane.smith", email="jane.smith@globex.com", name="Jane Smith")
    session.add_all([admin, john, jane])
    await session.flush()

    # Companies
    acme = Company(slug="acme-corp", name="ACME Corporation")
    globex = Company(slug="globex-inc", name="Globex Inc")
    session.add_all([acme, globex])
    await session.flush()

    # Projects
    p1 = Project(
        name="QuickBooks to Xero Migration",
        company_id=acme.id,
        source_system="quickbooks",
        target_system="xero",
        status="in_progress",
        description="Q1 2024 COA migration project",
        created_by=john.id,
    )
    p2 = Project(
        name="SAP to NetSuite Migration",
        company_id=acme.id,
        source_system="sap",
        target_system="oracle_netsuite",
        status="completed",
        description="Legacy system migration",
        created_by=john.id,
    )
    p3 = Project(
        name="Sage to Dynamics Migration",
        company_id=globex.id,
        source_system="sage",
        target_system="microsoft_dynamics",
        status="draft",
        description="Planned Q2 migration",
        created_by=jane.id,
    )
    session.add_all([p1, p2, p3])
    await session.flush()

    # Project access
    now = datetime.now(UTC)
    access_entries = [
        ProjectAccess(user_id=john.id, project_id=p1.id, permission="admin", created_at=now),
        ProjectAccess(user_id=jane.id, project_id=p1.id, permission="viewer", created_at=now),
        ProjectAccess(user_id=admin.id, project_id=p1.id, permission="admin", created_at=now),
        ProjectAccess(user_id=john.id, project_id=p2.id, permission="admin", created_at=now),
        ProjectAccess(user_id=admin.id, project_id=p2.id, permission="admin", created_at=now),
        ProjectAccess(user_id=jane.id, project_id=p3.id, permission="admin", created_at=now),
        ProjectAccess(user_id=admin.id, project_id=p3.id, permission="admin", created_at=now),
    ]
    session.add_all(access_entries)
    await session.flush()

    # Sample mappings
    mappings = [
        Mapping(
            project_id=p1.id,
            source_account_name="Checking",
            source_account_type="Bank",
            target_account_name="Business Bank Account",
            target_account_type="BANK",
            confidence_score=95.0,
            status="approved",
        ),
        Mapping(
            project_id=p1.id,
            source_account_name="Accounts Receivable",
            source_account_type="Accounts Receivable",
            target_account_name="Trade Debtors",
            target_account_type="CURRENT",
            confidence_score=88.0,
            status="suggested",
        ),
        Mapping(
            project_id=p2.id,
            source_account_name="Cash and Equivalents",
            source_account_type="Asset",
            target_account_name="Petty Cash",
            target_account_type="Bank",
            confidence_score=100.0,
            status="approved",
        ),
    ]
    session.add_all(mappings)

    await session.commit()
    logger.info("Initial data seeded successfully")


async def main() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)

    # Create tables if they don't exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        await seed(session)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
