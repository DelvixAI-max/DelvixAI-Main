"""SQLAlchemy models for the AFL tribunal automation pipeline.

games                -> one row per match, one video path per quarter
clock_sync_segments   -> Stage 0 output: broadcast-second <-> game-clock-second mapping
candidates            -> Stage 1 output: scored windows of potential incidents
clips                 -> Stage 2 output: cut + stored video clips
llm_assessments       -> Stage 3 output: Claude's structured read on a candidate clip
umpire_reports        -> Stage 4 input: the umpire's on-field report
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from config import settings


class Base(DeclarativeBase):
    pass


class CandidateStatus(str, enum.Enum):
    PENDING = "pending"
    REVIEWED = "reviewed"
    DISMISSED = "dismissed"


class ClipSource(str, enum.Enum):
    BROADCAST = "broadcast"
    COACHES_ANGLE = "coaches_angle"


class UmpireReportStatus(str, enum.Enum):
    RECEIVED = "received"
    CLIP_READY = "clip_ready"
    SENT_TO_TRIBUNAL = "sent_to_tribunal"
    FAILED = "failed"


class Game(Base):
    __tablename__ = "games"

    id: Mapped[int] = mapped_column(primary_key=True)
    season: Mapped[int] = mapped_column(Integer)
    round: Mapped[str] = mapped_column(String(16))
    home_team: Mapped[str] = mapped_column(String(64))
    away_team: Mapped[str] = mapped_column(String(64))
    ground: Mapped[str] = mapped_column(String(64), default="")
    played_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # {"1": "/path/to/q1.mp4", "2": "...", "3": "...", "4": "..."}
    broadcast_video_paths: Mapped[dict] = mapped_column(JSON, default=dict)
    # Optional wide "coaches' angle" footage, same keying, for off-ball incidents
    coaches_angle_video_paths: Mapped[dict] = mapped_column(JSON, default=dict)

    # Broadcast clock crop box, e.g. {"x": 1700, "y": 40, "w": 160, "h": 50}
    clock_crop_box: Mapped[dict] = mapped_column(JSON, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    clock_sync_segments: Mapped[list["ClockSyncSegment"]] = relationship(
        back_populates="game", cascade="all, delete-orphan"
    )
    candidates: Mapped[list["Candidate"]] = relationship(back_populates="game", cascade="all, delete-orphan")
    clips: Mapped[list["Clip"]] = relationship(back_populates="game", cascade="all, delete-orphan")
    umpire_reports: Mapped[list["UmpireReport"]] = relationship(
        back_populates="game", cascade="all, delete-orphan"
    )


class ClockSyncSegment(Base):
    """One row per contiguous run of broadcast seconds during which the
    on-screen game clock displayed a single value (i.e. the clock was
    live-counting through that value, or paused on it during a stoppage)."""

    __tablename__ = "clock_sync_segments"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"))
    quarter: Mapped[int] = mapped_column(Integer)
    game_clock_seconds: Mapped[int] = mapped_column(Integer)
    broadcast_start_seconds: Mapped[float] = mapped_column(Float)
    broadcast_end_seconds: Mapped[float] = mapped_column(Float)

    game: Mapped["Game"] = relationship(back_populates="clock_sync_segments")


class Candidate(Base):
    __tablename__ = "candidates"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"))
    quarter: Mapped[int] = mapped_column(Integer)
    source: Mapped[ClipSource] = mapped_column(Enum(ClipSource), default=ClipSource.BROADCAST)

    broadcast_start_seconds: Mapped[float] = mapped_column(Float)
    broadcast_end_seconds: Mapped[float] = mapped_column(Float)
    game_clock_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)

    score: Mapped[float] = mapped_column(Float)
    motion_score: Mapped[float] = mapped_column(Float, default=0.0)
    density_score: Mapped[float] = mapped_column(Float, default=0.0)
    pose_score: Mapped[float] = mapped_column(Float, default=0.0)

    status: Mapped[CandidateStatus] = mapped_column(Enum(CandidateStatus), default=CandidateStatus.PENDING)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    game: Mapped["Game"] = relationship(back_populates="candidates")
    clips: Mapped[list["Clip"]] = relationship(back_populates="candidate")
    llm_assessments: Mapped[list["LLMAssessment"]] = relationship(back_populates="candidate")


class Clip(Base):
    __tablename__ = "clips"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"))
    candidate_id: Mapped[int | None] = mapped_column(ForeignKey("candidates.id"), nullable=True)
    umpire_report_id: Mapped[int | None] = mapped_column(ForeignKey("umpire_reports.id"), nullable=True)

    quarter: Mapped[int] = mapped_column(Integer)
    broadcast_start_seconds: Mapped[float] = mapped_column(Float)
    broadcast_end_seconds: Mapped[float] = mapped_column(Float)
    game_clock_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)

    storage_key: Mapped[str] = mapped_column(String(255))
    url: Mapped[str] = mapped_column(String(1024), default="")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    game: Mapped["Game"] = relationship(back_populates="clips")
    candidate: Mapped["Candidate | None"] = relationship(back_populates="clips")
    llm_assessments: Mapped[list["LLMAssessment"]] = relationship(back_populates="clip")


class LLMAssessment(Base):
    __tablename__ = "llm_assessments"

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"))
    clip_id: Mapped[int] = mapped_column(ForeignKey("clips.id"))

    offence_category: Mapped[str] = mapped_column(String(128))
    confidence: Mapped[float] = mapped_column(Float)
    rationale: Mapped[str] = mapped_column(Text)
    players_involved: Mapped[list] = mapped_column(JSON, default=list)
    needs_human_review: Mapped[bool] = mapped_column(Boolean, default=True)
    raw_response: Mapped[dict] = mapped_column(JSON, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    candidate: Mapped["Candidate"] = relationship(back_populates="llm_assessments")
    clip: Mapped["Clip"] = relationship(back_populates="llm_assessments")


class UmpireReport(Base):
    __tablename__ = "umpire_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"))

    reporting_umpire: Mapped[str] = mapped_column(String(128), default="")
    offender_jumper_number: Mapped[int] = mapped_column(Integer)
    offender_team: Mapped[str] = mapped_column(String(64))
    victim_jumper_number: Mapped[int] = mapped_column(Integer)
    victim_team: Mapped[str] = mapped_column(String(64))
    incident_type: Mapped[str] = mapped_column(String(128))
    expected_damage: Mapped[str] = mapped_column(String(64), default="")
    ground_zone: Mapped[str] = mapped_column(String(64), default="")

    quarter: Mapped[int] = mapped_column(Integer)
    game_clock_seconds: Mapped[int] = mapped_column(Integer)

    raw_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[UmpireReportStatus] = mapped_column(
        Enum(UmpireReportStatus), default=UmpireReportStatus.RECEIVED
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    game: Mapped["Game"] = relationship(back_populates="umpire_reports")


engine = create_engine(settings.database_url, future=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)
