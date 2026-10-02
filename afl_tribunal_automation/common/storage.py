"""S3-compatible object storage wrapper (AWS S3 or MinIO for local dev)."""

from __future__ import annotations

import shutil
from pathlib import Path

from config import settings


def _client():
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url or None,
        aws_access_key_id=settings.s3_access_key or None,
        aws_secret_access_key=settings.s3_secret_key or None,
        region_name=settings.s3_region,
    )


def upload_clip(local_path: str, storage_key: str) -> str:
    """Store a clip and return a URL/path ffmpeg and the analyst can open.

    With STORAGE_BACKEND=local the clip is copied under LOCAL_STORAGE_DIR
    (no S3/MinIO needed — handy for single-machine runs); otherwise it's
    uploaded to the configured S3-compatible bucket.
    """
    if settings.storage_backend == "local":
        dest = Path(settings.local_storage_dir) / storage_key
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(local_path, dest)
        return str(dest.resolve())

    client = _client()
    client.upload_file(local_path, settings.s3_bucket, storage_key)
    return public_url(storage_key)


def public_url(storage_key: str) -> str:
    if settings.storage_backend == "local":
        return str((Path(settings.local_storage_dir) / storage_key).resolve())
    base = settings.s3_public_base_url.rstrip("/")
    if base:
        return f"{base}/{storage_key}"
    return f"s3://{settings.s3_bucket}/{storage_key}"


def clip_storage_key(game_id: int, quarter: int, start_seconds: float, suffix: str = "mp4") -> str:
    filename = f"q{quarter}_{start_seconds:07.2f}.{suffix}"
    return f"games/{game_id}/clips/{Path(filename).name}"
