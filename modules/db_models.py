"""
Database models and session helpers for job tracking.
"""
from __future__ import annotations

import os
import time
import uuid
from contextlib import contextmanager
from datetime import datetime
from typing import Generator, Optional

from sqlalchemy import Column, DateTime, Float, Integer, JSON, String, Text, create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://jarvis:jarvis@postgres:5432/jarvis",
)

connect_timeout = int(os.getenv("DB_CONNECT_TIMEOUT", "5"))
engine_kwargs = {"pool_pre_ping": True}
if not DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"connect_timeout": connect_timeout}

engine = create_engine(DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

Base = declarative_base()


class Job(Base):
    __tablename__ = "jobs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    status = Column(String(32), index=True, nullable=False, default="queued")
    input_data = Column(JSON, nullable=True)
    output_data = Column(JSON, nullable=True)
    output_key = Column(String(1024), nullable=True)
    clips_keys = Column(JSON, nullable=True)
    output_url = Column(String(1024), nullable=True)
    progress = Column(Float, nullable=True)
    progress_stage = Column(String(128), nullable=True)
    error = Column(Text, nullable=True)
    retry_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


VALID_STATUS_TRANSITIONS = {
    "queued": {"processing", "failed"},
    "processing": {"completed", "failed"},
    "failed": {"queued"},
    "completed": set(),
}


def validate_status_transition(current: str, new: str) -> bool:
    return new in VALID_STATUS_TRANSITIONS.get(current, set())


def init_db(retries: int = 10, delay_seconds: float = 2.0) -> None:
    """Create tables with a small retry loop for container startup."""
    last_error: Optional[Exception] = None
    for _ in range(retries):
        try:
            Base.metadata.create_all(bind=engine)
            with engine.begin() as conn:
                conn.execute(
                    text("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS output_key VARCHAR(1024)")
                )
                conn.execute(
                    text("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS clips_keys JSON")
                )
                conn.execute(
                    text("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS progress DOUBLE PRECISION")
                )
                conn.execute(
                    text("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS progress_stage VARCHAR(128)")
                )
                conn.execute(
                    text("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS retry_count INTEGER DEFAULT 0")
                )
            return
        except Exception as exc:
            last_error = exc
            time.sleep(delay_seconds)
    if last_error:
        raise last_error


@contextmanager
def db_session() -> Generator:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
