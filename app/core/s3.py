import boto3
from botocore.client import BaseClient

from app.core.config import settings

_s3_client: BaseClient | None = None


def get_s3_client() -> BaseClient:
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client(
            "s3",
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )
    return _s3_client


def generate_presigned_upload_url(object_key: str, content_type: str) -> str:
    client = get_s3_client()
    return client.generate_presigned_url(
        ClientMethod="put_object",
        Params={
            "Bucket": settings.AWS_S3_BUCKET_NAME,
            "Key": object_key,
            "ContentType": content_type,
        },
        ExpiresIn=settings.AWS_S3_PRESIGNED_URL_EXPIRE,
    )


def generate_presigned_download_url(object_key: str) -> str:
    client = get_s3_client()
    return client.generate_presigned_url(
        ClientMethod="get_object",
        Params={
            "Bucket": settings.AWS_S3_BUCKET_NAME,
            "Key": object_key,
        },
        ExpiresIn=settings.AWS_S3_PRESIGNED_URL_EXPIRE,
    )
