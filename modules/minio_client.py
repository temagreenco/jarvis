"""
MinIO / S3 client helpers.
"""
from __future__ import annotations

import os
from typing import Optional, Any

import boto3
from botocore.config import Config

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "http://minio:9000")
MINIO_PUBLIC_ENDPOINT = os.getenv("MINIO_PUBLIC_ENDPOINT", "http://localhost:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
MINIO_REGION = os.getenv("MINIO_REGION", "us-east-1")


def get_s3_client(public: bool = False) -> Optional[Any]:
    endpoint = MINIO_PUBLIC_ENDPOINT if public else MINIO_ENDPOINT
    if not endpoint:
        return None
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
        region_name=MINIO_REGION,
        config=Config(signature_version="s3v4"),
    )


def presign_get_url(key: str, expires_seconds: int = 3600) -> str:
    client = get_s3_client(public=True)
    if not client:
        raise RuntimeError("S3 client is not configured")
    bucket = os.getenv("MINIO_BUCKET", "jarvis")
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=expires_seconds,
    )
