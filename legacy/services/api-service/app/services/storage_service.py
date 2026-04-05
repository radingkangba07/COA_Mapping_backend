"""
Object Storage Service - Provider-Agnostic Storage Layer

This module provides a unified interface for object storage operations.
Supports:
- Emergent Object Storage (default, uses EMERGENT_LLM_KEY)
- Cloudflare R2 (via S3-compatible API)
- DigitalOcean Spaces (via S3-compatible API)

Configuration is done via environment variables only - no code changes needed
to switch providers.

Key Structure:
- company/{company_id}/project/{project_id}/uploads/{uuid}.{ext}
- company/{company_id}/project/{project_id}/artifacts/{uuid}.{ext}
- company/{company_id}/project/{project_id}/jobs/{job_id}/{uuid}.{ext}
"""
import os
import uuid
import logging
import requests
from abc import ABC, abstractmethod
from typing import Optional, Tuple, Dict, Any
from datetime import datetime, timezone
from enum import Enum

logger = logging.getLogger(__name__)


class StorageProvider(str, Enum):
    """Supported storage providers."""
    EMERGENT = "emergent"      # Default - Emergent Object Storage
    CLOUDFLARE_R2 = "r2"       # Cloudflare R2
    DIGITALOCEAN = "spaces"    # DigitalOcean Spaces


class StorageConfig:
    """Storage configuration from environment variables."""
    
    # Common
    PROVIDER = os.environ.get("STORAGE_PROVIDER", "emergent")
    APP_NAME = os.environ.get("STORAGE_APP_NAME", "coa-migration")
    
    # Emergent Object Storage (default)
    EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY", "")
    EMERGENT_STORAGE_URL = "https://integrations.emergentagent.com/objstore/api/v1/storage"
    
    # Cloudflare R2 / DigitalOcean Spaces (S3-compatible)
    S3_ENDPOINT = os.environ.get("S3_ENDPOINT", "")  # e.g., https://<account>.r2.cloudflarestorage.com
    S3_ACCESS_KEY = os.environ.get("S3_ACCESS_KEY", "")
    S3_SECRET_KEY = os.environ.get("S3_SECRET_KEY", "")
    S3_BUCKET = os.environ.get("S3_BUCKET", "coa-storage")
    S3_REGION = os.environ.get("S3_REGION", "auto")
    
    # Signed URL expiration (seconds)
    SIGNED_URL_EXPIRATION = int(os.environ.get("SIGNED_URL_EXPIRATION", "3600"))


class BaseStorageProvider(ABC):
    """Abstract base class for storage providers."""
    
    @abstractmethod
    def init(self) -> bool:
        """Initialize the storage provider. Returns True if successful."""
        pass
    
    @abstractmethod
    def put_object(self, path: str, data: bytes, content_type: str) -> Dict[str, Any]:
        """Upload an object. Returns metadata dict with path, size, etag."""
        pass
    
    @abstractmethod
    def get_object(self, path: str) -> Tuple[bytes, str]:
        """Download an object. Returns (content_bytes, content_type)."""
        pass
    
    @abstractmethod
    def delete_object(self, path: str) -> bool:
        """Delete an object. Returns True if successful."""
        pass
    
    @abstractmethod
    def get_signed_url(self, path: str, expires_in: int = 3600) -> Optional[str]:
        """Get a signed URL for direct access. Returns None if not supported."""
        pass
    
    @abstractmethod
    def object_exists(self, path: str) -> bool:
        """Check if an object exists."""
        pass


class EmergentStorageProvider(BaseStorageProvider):
    """Emergent Object Storage provider (default)."""
    
    def __init__(self):
        self.storage_key = None
        self.storage_url = StorageConfig.EMERGENT_STORAGE_URL
        self.emergent_key = StorageConfig.EMERGENT_KEY
    
    def init(self) -> bool:
        """Initialize storage and get session key."""
        if self.storage_key:
            return True
        
        if not self.emergent_key:
            logger.error("EMERGENT_LLM_KEY not set")
            return False
        
        try:
            resp = requests.post(
                f"{self.storage_url}/init",
                json={"emergent_key": self.emergent_key},
                timeout=30
            )
            resp.raise_for_status()
            self.storage_key = resp.json()["storage_key"]
            logger.info("Emergent storage initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Emergent storage: {e}")
            return False
    
    def put_object(self, path: str, data: bytes, content_type: str) -> Dict[str, Any]:
        """Upload object to Emergent storage."""
        if not self.init():
            raise RuntimeError("Storage not initialized")
        
        resp = requests.put(
            f"{self.storage_url}/objects/{path}",
            headers={
                "X-Storage-Key": self.storage_key,
                "Content-Type": content_type
            },
            data=data,
            timeout=120
        )
        resp.raise_for_status()
        return resp.json()
    
    def get_object(self, path: str) -> Tuple[bytes, str]:
        """Download object from Emergent storage."""
        if not self.init():
            raise RuntimeError("Storage not initialized")
        
        resp = requests.get(
            f"{self.storage_url}/objects/{path}",
            headers={"X-Storage-Key": self.storage_key},
            timeout=60
        )
        resp.raise_for_status()
        return resp.content, resp.headers.get("Content-Type", "application/octet-stream")
    
    def delete_object(self, path: str) -> bool:
        """Soft delete only - Emergent storage doesn't support delete."""
        logger.warning(f"Emergent storage doesn't support delete. Path: {path}")
        return True  # Soft delete handled in DB
    
    def get_signed_url(self, path: str, expires_in: int = 3600) -> Optional[str]:
        """Not supported - access through backend only."""
        return None
    
    def object_exists(self, path: str) -> bool:
        """Check if object exists by attempting HEAD-like request."""
        try:
            self.get_object(path)
            return True
        except:
            return False


class S3CompatibleProvider(BaseStorageProvider):
    """S3-compatible storage provider (Cloudflare R2, DigitalOcean Spaces)."""
    
    def __init__(self):
        self.client = None
        self.bucket = StorageConfig.S3_BUCKET
    
    def init(self) -> bool:
        """Initialize boto3 client."""
        if self.client:
            return True
        
        try:
            import boto3
            from botocore.config import Config
            
            self.client = boto3.client(
                's3',
                endpoint_url=StorageConfig.S3_ENDPOINT,
                aws_access_key_id=StorageConfig.S3_ACCESS_KEY,
                aws_secret_access_key=StorageConfig.S3_SECRET_KEY,
                region_name=StorageConfig.S3_REGION,
                config=Config(
                    signature_version='s3v4',
                    s3={'addressing_style': 'path'}
                )
            )
            
            # Test connection
            self.client.head_bucket(Bucket=self.bucket)
            logger.info(f"S3-compatible storage initialized: {StorageConfig.S3_ENDPOINT}")
            return True
        except ImportError:
            logger.error("boto3 not installed. Run: pip install boto3")
            return False
        except Exception as e:
            logger.error(f"Failed to initialize S3 storage: {e}")
            return False
    
    def put_object(self, path: str, data: bytes, content_type: str) -> Dict[str, Any]:
        """Upload object to S3-compatible storage."""
        if not self.init():
            raise RuntimeError("Storage not initialized")
        
        response = self.client.put_object(
            Bucket=self.bucket,
            Key=path,
            Body=data,
            ContentType=content_type
        )
        
        return {
            "path": path,
            "size": len(data),
            "etag": response.get("ETag", "").strip('"')
        }
    
    def get_object(self, path: str) -> Tuple[bytes, str]:
        """Download object from S3-compatible storage."""
        if not self.init():
            raise RuntimeError("Storage not initialized")
        
        response = self.client.get_object(Bucket=self.bucket, Key=path)
        content = response['Body'].read()
        content_type = response.get('ContentType', 'application/octet-stream')
        return content, content_type
    
    def delete_object(self, path: str) -> bool:
        """Delete object from S3-compatible storage."""
        if not self.init():
            raise RuntimeError("Storage not initialized")
        
        try:
            self.client.delete_object(Bucket=self.bucket, Key=path)
            return True
        except Exception as e:
            logger.error(f"Failed to delete object: {e}")
            return False
    
    def get_signed_url(self, path: str, expires_in: int = 3600) -> Optional[str]:
        """Generate presigned URL for direct access."""
        if not self.init():
            return None
        
        try:
            url = self.client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.bucket, 'Key': path},
                ExpiresIn=expires_in
            )
            return url
        except Exception as e:
            logger.error(f"Failed to generate signed URL: {e}")
            return None
    
    def object_exists(self, path: str) -> bool:
        """Check if object exists."""
        if not self.init():
            return False
        
        try:
            self.client.head_object(Bucket=self.bucket, Key=path)
            return True
        except:
            return False


class StorageService:
    """
    Unified storage service that abstracts provider details.
    
    Usage:
        storage = StorageService()
        storage.init()
        
        # Upload
        result = storage.upload_file(
            data=file_bytes,
            filename="report.xlsx",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            company_id="acme-corp",
            project_id="p-001",
            file_type="upload"
        )
        
        # Download
        data, content_type = storage.download_file(result["path"])
    """
    
    _instance = None
    
    def __new__(cls):
        """Singleton pattern for storage service."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self.app_name = StorageConfig.APP_NAME
        self.provider_name = StorageConfig.PROVIDER
        
        # Select provider based on config
        if self.provider_name == StorageProvider.EMERGENT.value:
            self.provider = EmergentStorageProvider()
        elif self.provider_name in [StorageProvider.CLOUDFLARE_R2.value, StorageProvider.DIGITALOCEAN.value]:
            self.provider = S3CompatibleProvider()
        else:
            logger.warning(f"Unknown provider '{self.provider_name}', defaulting to Emergent")
            self.provider = EmergentStorageProvider()
        
        self._initialized = True
    
    def init(self) -> bool:
        """Initialize the storage provider."""
        return self.provider.init()
    
    def _build_path(
        self,
        filename: str,
        company_id: str,
        project_id: str,
        file_type: str = "upload",
        job_id: Optional[str] = None
    ) -> str:
        """
        Build storage path following the key structure.
        
        Key Structure:
        - {app}/company/{company_id}/project/{project_id}/uploads/{uuid}.{ext}
        - {app}/company/{company_id}/project/{project_id}/artifacts/{uuid}.{ext}
        - {app}/company/{company_id}/project/{project_id}/jobs/{job_id}/{uuid}.{ext}
        """
        # Extract extension
        ext = filename.split(".")[-1] if "." in filename else "bin"
        unique_id = str(uuid.uuid4())
        
        # Build path based on type
        base = f"{self.app_name}/company/{company_id}/project/{project_id}"
        
        if job_id:
            return f"{base}/jobs/{job_id}/{unique_id}.{ext}"
        elif file_type == "artifact":
            return f"{base}/artifacts/{unique_id}.{ext}"
        else:
            return f"{base}/uploads/{unique_id}.{ext}"
    
    def upload_file(
        self,
        data: bytes,
        filename: str,
        content_type: str,
        company_id: str,
        project_id: str,
        file_type: str = "upload",
        job_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Upload a file to storage.
        
        Args:
            data: File content as bytes
            filename: Original filename (for extension extraction)
            content_type: MIME type
            company_id: Company ID for path
            project_id: Project ID for path
            file_type: "upload" or "artifact"
            job_id: Optional job ID for job-specific files
        
        Returns:
            Dict with path, size, etag, original_filename, content_type
        """
        path = self._build_path(filename, company_id, project_id, file_type, job_id)
        
        result = self.provider.put_object(path, data, content_type)
        
        return {
            **result,
            "original_filename": filename,
            "content_type": content_type,
            "company_id": company_id,
            "project_id": project_id,
            "job_id": job_id,
            "file_type": file_type,
            "uploaded_at": datetime.now(timezone.utc).isoformat()
        }
    
    def download_file(self, path: str) -> Tuple[bytes, str]:
        """
        Download a file from storage.
        
        Args:
            path: Storage path
        
        Returns:
            Tuple of (content_bytes, content_type)
        """
        return self.provider.get_object(path)
    
    def delete_file(self, path: str) -> bool:
        """Delete a file from storage (or soft-delete if not supported)."""
        return self.provider.delete_object(path)
    
    def get_download_url(self, path: str, expires_in: int = 3600) -> Optional[str]:
        """
        Get a signed URL for direct download (if supported).
        
        Returns None if provider doesn't support signed URLs.
        """
        return self.provider.get_signed_url(path, expires_in)
    
    def file_exists(self, path: str) -> bool:
        """Check if a file exists in storage."""
        return self.provider.object_exists(path)


# MIME type mapping
MIME_TYPES = {
    # Images
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "gif": "image/gif",
    "webp": "image/webp",
    "svg": "image/svg+xml",
    # Documents
    "pdf": "application/pdf",
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xls": "application/vnd.ms-excel",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "csv": "text/csv",
    "txt": "text/plain",
    # Data
    "json": "application/json",
    "xml": "application/xml",
    # Archives
    "zip": "application/zip",
    "tar": "application/x-tar",
    "gz": "application/gzip",
}


def get_content_type(filename: str, default: str = "application/octet-stream") -> str:
    """Get content type from filename extension."""
    ext = filename.split(".")[-1].lower() if "." in filename else ""
    return MIME_TYPES.get(ext, default)


# Singleton instance
storage_service = StorageService()
