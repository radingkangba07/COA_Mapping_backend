"""Base repository with common CRUD operations."""
from typing import Any, Dict, List, Optional
from motor.motor_asyncio import AsyncIOMotorDatabase, AsyncIOMotorCollection


def strip_mongo_id(doc: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Remove MongoDB _id from document."""
    if doc is None:
        return None
    if "_id" in doc:
        doc = {k: v for k, v in doc.items() if k != "_id"}
    return doc


class BaseRepository:
    """Base repository providing common MongoDB operations."""
    
    def __init__(self, db: AsyncIOMotorDatabase, collection_name: str):
        self.db = db
        self.collection: AsyncIOMotorCollection = db[collection_name]
    
    async def find_one(self, query: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Find a single document matching the query."""
        doc = await self.collection.find_one(query)
        return strip_mongo_id(doc)
    
    async def find_by_id(self, id_field: str, id_value: str) -> Optional[Dict[str, Any]]:
        """Find document by its ID field."""
        return await self.find_one({id_field: id_value})
    
    async def find_many(
        self, 
        query: Dict[str, Any], 
        sort: Optional[List[tuple]] = None,
        limit: int = 0,
        skip: int = 0
    ) -> List[Dict[str, Any]]:
        """Find multiple documents matching the query."""
        cursor = self.collection.find(query)
        
        if sort:
            cursor = cursor.sort(sort)
        if skip > 0:
            cursor = cursor.skip(skip)
        if limit > 0:
            cursor = cursor.limit(limit)
        
        docs = await cursor.to_list(length=None)
        return [strip_mongo_id(doc) for doc in docs]
    
    async def insert_one(self, document: Dict[str, Any]) -> Dict[str, Any]:
        """Insert a new document."""
        # Make a copy to avoid mutating the original
        doc_copy = dict(document)
        await self.collection.insert_one(doc_copy)
        return strip_mongo_id(document)
    
    async def update_one(
        self, 
        query: Dict[str, Any], 
        update: Dict[str, Any],
        upsert: bool = False
    ) -> bool:
        """Update a single document."""
        result = await self.collection.update_one(query, {"$set": update}, upsert=upsert)
        return result.modified_count > 0 or result.upserted_id is not None
    
    async def delete_one(self, query: Dict[str, Any]) -> bool:
        """Delete a single document."""
        result = await self.collection.delete_one(query)
        return result.deleted_count > 0
    
    async def delete_many(self, query: Dict[str, Any]) -> int:
        """Delete multiple documents."""
        result = await self.collection.delete_many(query)
        return result.deleted_count
    
    async def count(self, query: Dict[str, Any] = None) -> int:
        """Count documents matching the query."""
        return await self.collection.count_documents(query or {})
    
    async def exists(self, query: Dict[str, Any]) -> bool:
        """Check if a document exists."""
        doc = await self.collection.find_one(query, {"_id": 1})
        return doc is not None
