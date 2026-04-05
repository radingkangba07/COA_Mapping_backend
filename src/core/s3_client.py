import boto3

from src.core.config import get_settings

_s3_client = None


def init_s3_client() -> None:
    global _s3_client
    settings = get_settings()
    if not settings.s3_endpoint:
        return
    _s3_client = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region,
        config=boto3.session.Config(signature_version="s3v4"),
    )


def close_s3_client() -> None:
    global _s3_client
    _s3_client = None


def get_s3_client():
    return _s3_client
