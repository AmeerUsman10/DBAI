"""
Knowledge Store (SQLite)
Normalized persistence for training artifacts, feedback, sessions, and telemetry.
"""

import logging
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

from sqlalchemy import create_engine, Column, Integer, String, Text, Boolean, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker

logger = logging.getLogger(__name__)

DB_DIR = Path(__file__).parent.parent / "logs"
DB_PATH = DB_DIR / "dbai_training.db"

Base = declarative_base()


class Rule(Base):
    __tablename__ = "rules"
    id = Column(Integer, primary_key=True)
    instruction = Column(Text)
    owner = Column(String(100))
    priority = Column(Integer, default=5)
    status = Column(String(20), default="draft")
    usage_count = Column(Integer, default=0)
    workspace_id = Column(String(100), default="default")
    added_at = Column(DateTime)


class Learning(Base):
    __tablename__ = "learnings"
    id = Column(Integer, primary_key=True)
    original_query = Column(Text)
    clarified_query = Column(Text)
    sql = Column(Text)
    outcome = Column(String(20))
    usage_count = Column(Integer, default=0)
    workspace_id = Column(String(100), default="default")
    created_at = Column(DateTime)


class FeedbackEvent(Base):
    __tablename__ = "feedback_events"
    id = Column(Integer, primary_key=True)
    message_id = Column(String(50))
    feedback_type = Column(String(20))
    question = Column(Text)
    sql_query = Column(Text)
    response_preview = Column(Text)
    feedback_text = Column(Text)
    session_id = Column(String(50))
    workspace_id = Column(String(100), default="default")
    created_at = Column(DateTime)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id = Column(Integer, primary_key=True)
    session_id = Column(String(50))
    message_id = Column(String(50))
    question_hash = Column(String(64))
    sql_hash = Column(String(64))
    provider = Column(String(50))
    model = Column(String(100))
    generation_method = Column(String(20))
    tokens_total = Column(Integer, default=0)
    execution_time_ms = Column(Integer, default=0)
    cache_hit = Column(Boolean, default=False)
    safety_blocked = Column(Boolean, default=False)
    created_at = Column(DateTime)


_engine = None
_Session = None


def init_store() -> bool:
    """Initialize SQLite knowledge store."""
    global _engine, _Session
    try:
        DB_DIR.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(f"sqlite:///{DB_PATH}", echo=False, future=True)
        _Session = sessionmaker(bind=_engine)
        Base.metadata.create_all(_engine)
        logger.info(f"Knowledge store initialized at {DB_PATH}")
        return True
    except Exception as e:
        logger.error(f"Failed to init knowledge store: {e}")
        return False


def insert_feedback_event(event: Dict[str, Any]) -> None:
    """Insert a feedback event (best effort)."""
    try:
        if _Session is None:
            init_store()
        sess = _Session()
        fe = FeedbackEvent(
            message_id=event.get("message_id"),
            feedback_type=event.get("feedback_type"),
            question=event.get("question"),
            sql_query=event.get("sql_query"),
            response_preview=event.get("response_preview"),
            feedback_text=event.get("feedback_text"),
            session_id=event.get("session_id"),
            created_at=datetime.now()
        )
        sess.add(fe)
        sess.commit()
        sess.close()
    except Exception as e:
        logger.debug(f"Insert feedback event failed: {e}")


def insert_audit_event(event: Dict[str, Any]) -> None:
    """Insert an audit event (best effort)."""
    try:
        if _Session is None:
            init_store()
        sess = _Session()
        ae = AuditEvent(
            session_id=event.get("session_id"),
            message_id=event.get("message_id"),
            question_hash=event.get("question_hash"),
            sql_hash=event.get("sql_hash"),
            provider=event.get("provider"),
            model=event.get("model"),
            generation_method=event.get("generation_method"),
            tokens_total=event.get("tokens_total", 0),
            execution_time_ms=event.get("execution_time_ms", 0),
            cache_hit=bool(event.get("cache_hit")),
            safety_blocked=bool(event.get("safety_blocked")),
            created_at=datetime.now()
        )
        sess.add(ae)
        sess.commit()
        sess.close()
    except Exception as e:
        logger.debug(f"Insert audit event failed: {e}")


def insert_learning(entry: Dict[str, Any]) -> None:
    """Insert a learning record (best effort)."""
    try:
        if _Session is None:
            init_store()
        sess = _Session()
        lr = Learning(
            original_query=entry.get("original_query"),
            clarified_query=entry.get("clarified_query"),
            sql=entry.get("sql"),
            outcome=entry.get("outcome", "positive"),
            usage_count=int(entry.get("usage_count", 1)),
            workspace_id=entry.get("workspace_id", "default"),
            created_at=datetime.now()
        )
        sess.add(lr)
        sess.commit()
        sess.close()
    except Exception as e:
        logger.debug(f"Insert learning failed: {e}")
