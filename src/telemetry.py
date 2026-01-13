"""
Lightweight Telemetry Logger
Writes compact audit events to logs for analytics and governance.
"""

import json
import hashlib
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

logger = logging.getLogger(__name__)

AUDIT_DIR = Path(__file__).parent.parent / "logs"
AUDIT_LOG = AUDIT_DIR / "audit.log"
AUDIT_EVENTS = AUDIT_DIR / "audit_events.json"


def _ensure_audit_dir():
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)


def _hash_text(text: str) -> str:
    try:
        return hashlib.sha256((text or "").encode()).hexdigest()[:16]
    except Exception:
        return ""


class TelemetryLogger:
    """Minimal telemetry logger writing line-based and JSON audit events."""

    @staticmethod
    def log_audit_event(event: Dict[str, Any]):
        """
        Persist a compact audit event.
        Required keys: session_id, message_id, question, provider, model, generation_method,
        tokens_total, sql_query, success, execution_time_ms, cache_hit, safety_blocked.
        """
        try:
            _ensure_audit_dir()

            # Enrich with hashes and timestamp
            event = dict(event)
            event["timestamp"] = datetime.now().isoformat()
            event["question_hash"] = _hash_text(event.get("question", ""))
            event["sql_hash"] = _hash_text(event.get("sql_query", ""))

            # Write line log (human-friendly)
            line = (
                f"{event['timestamp']} | sess={event.get('session_id','')} msg={event.get('message_id','')} "
                f"prov={event.get('provider','')} model={event.get('model','')} meth={event.get('generation_method','')} "
                f"tok={event.get('tokens_total',0)} time_ms={event.get('execution_time_ms',0)} "
                f"cache={'Y' if event.get('cache_hit') else 'N'} safety={'Y' if event.get('safety_blocked') else 'N'} "
                f"qhash={event.get('question_hash','')} sqlhash={event.get('sql_hash','')}"
            )

            with open(AUDIT_LOG, 'a', encoding='utf-8') as f:
                f.write(line + "\n")

            # Append JSON event
            events = []
            if AUDIT_EVENTS.exists():
                try:
                    with open(AUDIT_EVENTS, 'r', encoding='utf-8') as jf:
                        events = json.load(jf)
                except Exception:
                    events = []

            events.append(event)
            with open(AUDIT_EVENTS, 'w', encoding='utf-8') as jf:
                json.dump(events, jf, indent=2, ensure_ascii=False)

            # Best-effort dual-write to SQLite knowledge store
            try:
                from src.knowledge_store import insert_audit_event, init_store
                init_store()
                insert_audit_event(event)
            except Exception:
                pass

        except Exception as e:
            logger.warning(f"Telemetry logging failed: {e}")

    @staticmethod
    def log_prompt_metadata(session_id: str, message_id: str, question: str, prompt_text: str, generation_method: str = "llm"):
        """Record prompt metadata with hashes and method."""
        try:
            _ensure_audit_dir()
            event = {
                "session_id": session_id,
                "message_id": message_id,
                "question": question,
                "generation_method": generation_method,
                "prompt_hash": _hash_text(prompt_text),
                "question_hash": _hash_text(question),
                "timestamp": datetime.now().isoformat()
            }
            # Append to audit_events.json for correlation
            TelemetryLogger.log_audit_event(event)
        except Exception:
            pass
