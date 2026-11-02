"""Saving recordings in object storage, through the S3 API (Week 3 Step 4).

Object storage keeps files ("objects") in a "bucket" under a name (the "key"). There are no
real folders: "sessions/7/abc.wav" is simply one long name. Recordings live here and not in
PostgreSQL because audio is big, and the database only needs to remember the key.
"""

from typing import Protocol
from uuid import uuid4

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError


class StorageError(Exception):
    """The storage service couldn't save the file: down, wrong key, missing bucket..."""


class AudioStorage(Protocol):
    """Anything that can keep a file under a key. Tests use a fake without a server."""

    def save(self, key: str, data: bytes, content_type: str) -> None:
        """Store the file, or raise StorageError."""

    def load(self, key: str) -> bytes:
        """The stored file, or raise StorageError."""


class S3AudioStorage:
    """AudioStorage for any S3-compatible service. Moving to real S3 only changes settings."""

    def __init__(self, endpoint_url: str, access_key: str, secret_key: str, bucket: str) -> None:
        self.bucket = bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name="us-east-1",  # required by the library, unused by a local server
            config=Config(
                signature_version="s3v4",
                # Bucket in the path (localhost:8333/bucket/key): a bucket as a subdomain
                # (bucket.localhost:8333) doesn't resolve on a local server.
                s3={"addressing_style": "path"},
                # Fail fast: a user is waiting, so don't hang if storage is down.
                connect_timeout=3,
                read_timeout=30,
                retries={"total_max_attempts": 2},
            ),
        )

    def save(self, key: str, data: bytes, content_type: str) -> None:
        try:
            self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)
        except (BotoCoreError, ClientError) as e:
            raise StorageError(f"{type(e).__name__}: {e}") from e

    def load(self, key: str) -> bytes:
        try:
            return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        except (BotoCoreError, ClientError) as e:
            raise StorageError(f"{type(e).__name__}: {e}") from e


def new_audio_key(session_id: int) -> str:
    """A unique name for one recording. Random, so two uploads can never overwrite each other."""
    return f"sessions/{session_id}/{uuid4().hex}.wav"
