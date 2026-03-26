"""MongoDB connection management using motor (async driver)."""
import os
import logging
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from dotenv import load_dotenv

load_dotenv(override=True)

logger = logging.getLogger(__name__)

# Global connection state
_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None

# Connection settings from environment
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "coa_migration")


async def init_db() -> AsyncIOMotorDatabase:
    """Initialize MongoDB connection and return database instance."""
    global _client, _db
    
    if _db is not None:
        return _db
    
    try:
        _client = AsyncIOMotorClient(MONGO_URL)
        _db = _client[DB_NAME]
        
        # Test connection
        await _client.admin.command('ping')
        logger.info(f"Connected to MongoDB: {DB_NAME}")
        
        # Create indexes for performance
        await _create_indexes(_db)
        
        return _db
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB: {e}")
        raise


async def _create_indexes(db: AsyncIOMotorDatabase):
    """Create indexes for better query performance."""
    try:
        # Users collection
        await db.users.create_index("user_id", unique=True)
        await db.users.create_index("email", unique=True, sparse=True)
        
        # Companies collection
        await db.companies.create_index("company_id", unique=True)
        
        # Projects collection
        await db.projects.create_index("company_id")
        await db.projects.create_index("created_by")
        await db.projects.create_index("status")
        
        # Project access collection
        await db.project_access.create_index([("user_id", 1), ("project_id", 1)], unique=True)
        await db.project_access.create_index("project_id")
        await db.project_access.create_index("user_id")
        
        # Mappings collection
        await db.mappings.create_index("project_id")
        await db.mappings.create_index([("project_id", 1), ("status", 1)])
        
        # Files collection
        await db.files.create_index("project_id")
        await db.files.create_index("storage_path", unique=True, sparse=True)
        await db.files.create_index([("project_id", 1), ("file_type", 1)])
        
        logger.info("Database indexes created successfully")
    except Exception as e:
        logger.warning(f"Index creation warning (may already exist): {e}")


def get_database() -> AsyncIOMotorDatabase:
    """Get the database instance. Raises if not initialized."""
    if _db is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _db


async def close_db():
    """Close database connection."""
    global _client, _db
    
    if _client is not None:
        _client.close()
        _client = None
        _db = None
        logger.info("MongoDB connection closed")


async def seed_initial_data(db: AsyncIOMotorDatabase):
    """Seed initial data for demo purposes."""
    from datetime import datetime, timezone
    
    now = datetime.now(timezone.utc).isoformat()
    
    # Check if data already exists
    existing_users = await db.users.count_documents({})
    if existing_users > 0:
        logger.info("Database already has data, skipping seed")
        return
    
    # Seed users
    users = [
        {
            "id": "u-001",
            "user_id": "admin",
            "name": "Admin User",
            "email": "admin@company.com",
            "is_active": True,
            "created_at": "2024-01-01T00:00:00Z"
        },
        {
            "id": "u-002",
            "user_id": "john.doe",
            "name": "John Doe",
            "email": "john.doe@acme.com",
            "is_active": True,
            "created_at": "2024-01-15T00:00:00Z"
        },
        {
            "id": "u-003",
            "user_id": "jane.smith",
            "name": "Jane Smith",
            "email": "jane.smith@globex.com",
            "is_active": True,
            "created_at": "2024-02-01T00:00:00Z"
        }
    ]
    await db.users.insert_many(users)
    
    # Seed companies
    companies = [
        {
            "id": "c-001",
            "company_id": "acme-corp",
            "name": "ACME Corporation",
            "description": "Manufacturing and distribution company",
            "created_at": "2024-01-01T00:00:00Z"
        },
        {
            "id": "c-002",
            "company_id": "globex-inc",
            "name": "Globex Inc",
            "description": "Global technology solutions",
            "created_at": "2024-01-15T00:00:00Z"
        }
    ]
    await db.companies.insert_many(companies)
    
    # Seed projects
    projects = [
        {
            "id": "p-001",
            "company_id": "acme-corp",
            "name": "QuickBooks to Xero Migration",
            "source_erp": "quickbooks",
            "target_erp": "xero",
            "status": "in_progress",
            "description": "Q1 2024 COA migration project",
            "created_by": "john.doe",
            "created_at": "2024-03-01T00:00:00Z",
            "updated_at": "2024-03-15T10:30:00Z",
            "last_edited_by": "john.doe"
        },
        {
            "id": "p-002",
            "company_id": "acme-corp",
            "name": "SAP to NetSuite Migration",
            "source_erp": "sap",
            "target_erp": "oracle_netsuite",
            "status": "completed",
            "description": "Legacy system migration",
            "created_by": "john.doe",
            "created_at": "2024-02-01T00:00:00Z",
            "updated_at": "2024-02-28T16:00:00Z",
            "last_edited_by": "john.doe"
        },
        {
            "id": "p-003",
            "company_id": "globex-inc",
            "name": "Sage to Dynamics Migration",
            "source_erp": "sage",
            "target_erp": "microsoft_dynamics",
            "status": "draft",
            "description": "Planned Q2 migration",
            "created_by": "jane.smith",
            "created_at": "2024-03-10T00:00:00Z",
            "updated_at": "2024-03-10T00:00:00Z",
            "last_edited_by": "jane.smith"
        }
    ]
    await db.projects.insert_many(projects)
    
    # Seed project access
    project_access = [
        {"user_id": "john.doe", "project_id": "p-001", "permission": "admin", "assigned_at": "2024-03-01T00:00:00Z"},
        {"user_id": "jane.smith", "project_id": "p-001", "permission": "viewer", "assigned_at": "2024-03-05T00:00:00Z"},
        {"user_id": "admin", "project_id": "p-001", "permission": "admin", "assigned_at": "2024-03-01T00:00:00Z"},
        {"user_id": "john.doe", "project_id": "p-002", "permission": "admin", "assigned_at": "2024-02-01T00:00:00Z"},
        {"user_id": "admin", "project_id": "p-002", "permission": "admin", "assigned_at": "2024-02-01T00:00:00Z"},
        {"user_id": "jane.smith", "project_id": "p-003", "permission": "admin", "assigned_at": "2024-03-10T00:00:00Z"},
        {"user_id": "admin", "project_id": "p-003", "permission": "admin", "assigned_at": "2024-03-10T00:00:00Z"}
    ]
    await db.project_access.insert_many(project_access)
    
    # Seed sample mappings
    mappings = [
        {
            "id": "m-001",
            "project_id": "p-001",
            "source_account_name": "Checking",
            "source_account_type": "Bank",
            "target_account_name": "Business Bank Account",
            "target_account_type": "BANK",
            "confidence_score": 95.0,
            "status": "approved",
            "remark": "ai",
            "changed_by_name": None,
            "changed_at": None
        },
        {
            "id": "m-002",
            "project_id": "p-001",
            "source_account_name": "Accounts Receivable",
            "source_account_type": "Accounts Receivable",
            "target_account_name": "Trade Debtors",
            "target_account_type": "CURRENT",
            "confidence_score": 88.0,
            "status": "suggested",
            "remark": "user",
            "changed_by_name": "John Doe",
            "changed_at": "2024-03-15T10:30:00Z"
        },
        {
            "id": "m-003",
            "project_id": "p-002",
            "source_account_name": "Cash and Equivalents",
            "source_account_type": "Asset",
            "target_account_name": "Petty Cash",
            "target_account_type": "Bank",
            "confidence_score": 100.0,
            "status": "approved",
            "remark": "user",
            "changed_by_name": "John Doe",
            "changed_at": "2024-02-20T14:15:00Z"
        }
    ]
    await db.mappings.insert_many(mappings)
    
    logger.info("Initial data seeded successfully")
