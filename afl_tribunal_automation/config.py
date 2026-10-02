"""Central settings, read from environment (.env). No framework magic —
just one place every module imports from."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _env_float(name: str, default: float) -> float:
    return float(os.environ.get(name, default))


def _env_int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


@dataclass(frozen=True)
class Settings:
    database_url: str = field(
        default_factory=lambda: os.environ.get(
            "DATABASE_URL", "postgresql+psycopg2://afl:afl@localhost:5432/afl_tribunal"
        )
    )

    # "s3" (default) or "local" — local keeps clips on disk under local_storage_dir
    storage_backend: str = field(default_factory=lambda: os.environ.get("STORAGE_BACKEND", "s3"))
    local_storage_dir: str = field(default_factory=lambda: os.environ.get("LOCAL_STORAGE_DIR", "./storage"))

    s3_endpoint_url: str = field(default_factory=lambda: os.environ.get("S3_ENDPOINT_URL", ""))
    s3_bucket: str = field(default_factory=lambda: os.environ.get("S3_BUCKET", "afl-tribunal-clips"))
    s3_access_key: str = field(default_factory=lambda: os.environ.get("S3_ACCESS_KEY", ""))
    s3_secret_key: str = field(default_factory=lambda: os.environ.get("S3_SECRET_KEY", ""))
    s3_region: str = field(default_factory=lambda: os.environ.get("S3_REGION", "ap-southeast-2"))
    s3_public_base_url: str = field(default_factory=lambda: os.environ.get("S3_PUBLIC_BASE_URL", ""))

    anthropic_api_key: str = field(default_factory=lambda: os.environ.get("ANTHROPIC_API_KEY", ""))
    claude_model: str = field(default_factory=lambda: os.environ.get("CLAUDE_MODEL", "claude-sonnet-5"))

    candidate_window_seconds: int = field(default_factory=lambda: _env_int("CANDIDATE_WINDOW_SECONDS", 2))
    candidate_score_threshold: float = field(
        default_factory=lambda: _env_float("CANDIDATE_SCORE_THRESHOLD", 0.3)
    )
    candidate_merge_gap_seconds: int = field(
        default_factory=lambda: _env_int("CANDIDATE_MERGE_GAP_SECONDS", 2)
    )
    # Keep this share of all windows (0.06 = top 6%); score_threshold acts as a floor.
    candidate_top_fraction: float = field(default_factory=lambda: _env_float("CANDIDATE_TOP_FRACTION", 0.06))

    clip_buffer_before_seconds: float = field(
        default_factory=lambda: _env_float("CLIP_BUFFER_BEFORE_SECONDS", 3.0)
    )
    clip_buffer_after_seconds: float = field(
        default_factory=lambda: _env_float("CLIP_BUFFER_AFTER_SECONDS", 5.0)
    )

    tribunal_webhook_url: str = field(default_factory=lambda: os.environ.get("TRIBUNAL_WEBHOOK_URL", ""))
    tribunal_slack_webhook_url: str = field(
        default_factory=lambda: os.environ.get("TRIBUNAL_NOTIFY_SLACK_WEBHOOK_URL", "")
    )
    umpire_webhook_shared_secret: str = field(
        default_factory=lambda: os.environ.get("UMPIRE_WEBHOOK_SHARED_SECRET", "")
    )


settings = Settings()
