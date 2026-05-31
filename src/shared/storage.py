from __future__ import annotations

from pathlib import Path

import boto3

from src.shared.config import settings


class LocalObjectStore:
    def __init__(self, base_path: str = "local_store") -> None:
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def put_bytes(self, object_key: str, content: bytes) -> str:
        file_path = self.base_path / object_key
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(content)
        return object_key

    def get_bytes(self, object_key: str) -> bytes:
        return (self.base_path / object_key).read_bytes()


class S3ObjectStore:
    def __init__(self) -> None:
        self.bucket = settings.s3_bucket
        session = boto3.Session(profile_name=settings.aws_profile) if settings.aws_profile else boto3.Session()
        self.client = session.client("s3", region_name=settings.aws_region)

    def put_bytes(self, object_key: str, content: bytes) -> str:
        self.client.put_object(Bucket=self.bucket, Key=object_key, Body=content)
        return object_key

    def get_bytes(self, object_key: str) -> bytes:
        response = self.client.get_object(Bucket=self.bucket, Key=object_key)
        return response["Body"].read()


object_store = S3ObjectStore() if settings.use_aws_services else LocalObjectStore()
