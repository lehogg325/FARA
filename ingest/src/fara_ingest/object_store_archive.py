from __future__ import annotations

import boto3
from botocore.client import Config as BotoConfig
from botocore.exceptions import ClientError


class ObjectStoreArchive:
    """Object-storage raw archive backed by any S3-compatible bucket (Supabase
    Storage in production — docs/deploy.md; works identically against
    Cloudflare R2, AWS S3, MinIO, etc., since it only ever uses a custom
    endpoint_url and never assumes a specific provider). Same
    exists()/write_atomic()/read_bytes() surface as LocalArchive, so
    ingest/normalize/extract code never branches on which backend is active
    (see fara_ingest.archive_factory.get_archive).

    A single S3 PUT is already atomic at the object level — an interrupted
    upload simply never produces an object at that key — so, unlike
    LocalArchive, no separate tmp-key-then-rename dance is needed here.
    """

    def __init__(self, *, bucket: str, endpoint_url: str, access_key_id: str, secret_access_key: str):
        self.bucket = bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            config=BotoConfig(signature_version="s3v4"),
            region_name="auto",
        )

    def exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") in ("404", "NoSuchKey"):
                return False
            raise

    def write_atomic(self, key: str, data: bytes) -> str:
        self._client.put_object(Bucket=self.bucket, Key=key, Body=data)
        return key

    def read_bytes(self, key: str) -> bytes:
        response = self._client.get_object(Bucket=self.bucket, Key=key)
        return response["Body"].read()
