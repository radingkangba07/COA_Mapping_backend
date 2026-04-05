import logging

from botocore.exceptions import ClientError

from src.core.config import get_settings

logger = logging.getLogger(__name__)

MIME_TYPES = {
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls": "application/vnd.ms-excel",
    ".csv": "text/csv",
    ".json": "application/json",
    ".pdf": "application/pdf",
    ".txt": "text/plain",
}


class S3Provider:
    def __init__(self, client):
        self.client = client
        self.bucket = get_settings().s3_bucket

    def put_object(self, path: str, data: bytes, content_type: str) -> dict:
        result = self.client.put_object(Bucket=self.bucket, Key=path, Body=data, ContentType=content_type)
        return {"etag": result.get("ETag", ""), "path": path}

    def get_object(self, path: str) -> tuple[bytes, str]:
        response = self.client.get_object(Bucket=self.bucket, Key=path)
        data = response["Body"].read()
        content_type = response.get("ContentType", "application/octet-stream")
        return data, content_type

    def delete_object(self, path: str) -> bool:
        try:
            self.client.delete_object(Bucket=self.bucket, Key=path)
            return True
        except ClientError:
            logger.exception("Failed to delete object %s", path)
            return False

    def get_signed_url(self, path: str, expires_in: int = 3600) -> str | None:
        try:
            return self.client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": path},
                ExpiresIn=expires_in,
            )
        except ClientError:
            return None

    def object_exists(self, path: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=path)
            return True
        except ClientError:
            return False
