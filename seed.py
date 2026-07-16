"""Seed initial demo data into PostgreSQL.

Run AFTER migrations have been applied.
This script only inserts demo rows; it does NOT create tables.

Usage:
    DATABASE_URL=postgresql+asyncpg://... uv run python seed.py
"""

import asyncio
import logging
import os
from datetime import UTC, datetime

from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from coa_db_models.auth.models import Organization, User
from coa_db_models.mappings.models import CoaMapping
from coa_db_models.projects.models import Project, ProjectAccess

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

    # Organizations
    acme = Organization(slug="acme-corp", name="ACME Corporation")
    globex = Organization(slug="globex-inc", name="Globex Inc")
    session.add_all([acme, globex])
    await session.flush()

    # Projects
    p1 = Project(
        name="QuickBooks to Xero Migration",
        org_id=acme.id,
        source_system="quickbooks",
        target_system="xero",
        status="in_progress",
        description="Q1 2024 COA migration project",
        created_by=john.id,
    )
    p2 = Project(
        name="SAP to NetSuite Migration",
        org_id=acme.id,
        source_system="sap",
        target_system="oracle_netsuite",
        status="completed",
        description="Legacy system migration",
        created_by=john.id,
    )
    p3 = Project(
        name="Sage to Dynamics Migration",
        org_id=globex.id,
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

    # Sample mapping suggestions
    mappings = [
        CoaMapping(
            project_id=p1.id,
            source_account_name="Checking",
            source_account_type="Bank",
            target_account_name="Business Bank Account",
            target_account_type="BANK",
            confidence_score=95.0,
            mapping_status="approved",
        ),
        CoaMapping(
            project_id=p1.id,
            source_account_name="Accounts Receivable",
            source_account_type="Accounts Receivable",
            target_account_name="Trade Debtors",
            target_account_type="CURRENT",
            confidence_score=88.0,
            mapping_status="suggested",
        ),
        CoaMapping(
            project_id=p2.id,
            source_account_name="Cash and Equivalents",
            source_account_type="Asset",
            target_account_name="Petty Cash",
            target_account_type="Bank",
            confidence_score=100.0,
            mapping_status="approved",
        ),
    ]
    session.add_all(mappings)

    await session.commit()
    logger.info("Initial data seeded successfully")


async def main() -> None:
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        raise RuntimeError("DATABASE_URL environment variable is not set")

    engine = create_async_engine(database_url)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        await seed(session)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
