from __future__ import annotations

from pathlib import Path
import boto3

from src.shared.aws import get_boto3_session
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


class SmartTestObjectStore:
    def __init__(self, fallback_dir: str = "SampleData/templates") -> None:
        self.fallback_dir = Path(fallback_dir)
        self._mem_store: dict[str, bytes] = {}

    def put_bytes(self, object_key: str, content: bytes) -> str:
        self._mem_store[object_key] = content
        return object_key

    def get_bytes(self, object_key: str) -> bytes:
        if object_key in self._mem_store:
            return self._mem_store[object_key]
        
        # Check if direct local file path exists
        p = Path(object_key)
        if p.is_file():
            return p.read_bytes()
            
        # Check inside fallback directory
        fallback_path = self.fallback_dir / p.name
        if fallback_path.is_file():
            return fallback_path.read_bytes()
            
        # Check sub-path
        if "templates/" in object_key:
            sub = object_key.split("templates/", 1)[1]
            p_sub = self.fallback_dir.parent / "templates" / sub
            if p_sub.is_file():
                return p_sub.read_bytes()

        raise FileNotFoundError(f"SmartTestObjectStore could not resolve key: {object_key}")


class S3ObjectStore:
    def __init__(self) -> None:
        self.bucket = settings.s3_bucket
        session = get_boto3_session()
        self.client = session.client("s3", region_name=settings.aws_region)

    def put_bytes(self, object_key: str, content: bytes) -> str:
        self.client.put_object(Bucket=self.bucket, Key=object_key, Body=content)
        return object_key

    def get_bytes(self, object_key: str) -> bytes:
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=object_key)
            return response["Body"].read()
        except Exception as e:
            # Fallback for local development and non-production testing if key is not found
            if settings.app_env != "production":
                p = Path(object_key)
                if p.is_file():
                    return p.read_bytes()
                
                # Check SampleData/templates
                fallback_dir = Path("SampleData/templates")
                fallback_path = fallback_dir / p.name
                if fallback_path.is_file():
                    return fallback_path.read_bytes()
                
                if "templates/" in object_key:
                    sub = object_key.split("templates/", 1)[1]
                    p_sub = Path("SampleData/templates") / sub
                    if p_sub.is_file():
                        return p_sub.read_bytes()
                        
            raise e


object_store = S3ObjectStore() if settings.use_aws_services else LocalObjectStore()

