"""
Query Performance Optimizer

Caching layer for query results and SQL generation to reduce LLM costs and improve response time.
Implements intelligent caching with fuzzy matching for similar queries.
"""

import json
import hashlib
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple, Any
from difflib import SequenceMatcher
from src.utils.atomic_write import atomic_write_json, atomic_read_json

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).parent.parent / "cache"
RESULT_CACHE_FILE = CACHE_DIR / "query_results.json"
SQL_CACHE_FILE = CACHE_DIR / "sql_cache.json"
CACHE_EXPIRY_HOURS = 24  # Results expire after 24 hours


def _ensure_cache_dir():
    """Ensure cache directory exists."""
    CACHE_DIR.mkdir(exist_ok=True)


def _load_cache(cache_file: Path) -> Dict:
    """Load cache from file."""
    try:
        return atomic_read_json(cache_file, default={})
    except Exception as e:
        logger.error(f"Error loading cache from {cache_file}: {e}")
        return {}


def _save_cache(cache_file: Path, data: Dict):
    """Save cache to file."""
    try:
        _ensure_cache_dir()
        atomic_write_json(cache_file, data)
    except Exception as e:
        logger.error(f"Error saving cache to {cache_file}: {e}")


def _is_expired(timestamp_str: str, expiry_hours: int = CACHE_EXPIRY_HOURS) -> bool:
    """Check if cached item has expired."""
    try:
        timestamp = datetime.fromisoformat(timestamp_str)
        return datetime.now() - timestamp > timedelta(hours=expiry_hours)
    except:
        return True


def _fuzzy_match_query(query1: str, query2: str, threshold: float = 0.90) -> bool:
    """Check if two queries are similar enough to be considered the same."""
    similarity = SequenceMatcher(None, query1.lower(), query2.lower()).ratio()
    return similarity >= threshold


def cache_query_result(question: str, sql: str, result: Any, metadata: Dict = None):
    """
    Cache a query result for future use.

    Args:
        question: Natural language question
        sql: SQL query executed
        result: Query result (dict with 'rows' and 'columns')
        metadata: Additional metadata (execution time, token count, etc.)
    """
    try:
        cache = _load_cache(RESULT_CACHE_FILE)

        # Create cache key from question hash
        cache_key = hashlib.md5(question.lower().encode()).hexdigest()

        cache[cache_key] = {
            "question": question,
            "sql": sql,
            "result": result,
            "metadata": metadata or {},
            "timestamp": datetime.now().isoformat(),
            "hit_count": cache.get(cache_key, {}).get("hit_count", 0)
        }

        _save_cache(RESULT_CACHE_FILE, cache)
        logger.info(f"Cached result for query: {question[:50]}...")

    except Exception as e:
        logger.error(f"Error caching query result: {e}")


def get_cached_result(question: str, fuzzy_match: bool = True) -> Optional[Tuple[str, Any, Dict]]:
    """
    Retrieve cached result for a query.

    Args:
        question: Natural language question
        fuzzy_match: If True, use fuzzy matching to find similar queries

    Returns:
        Tuple of (sql, result, metadata) if found, None otherwise
    """
    try:
        cache = _load_cache(RESULT_CACHE_FILE)

        # Try exact match first
        cache_key = hashlib.md5(question.lower().encode()).hexdigest()
        if cache_key in cache:
            cached = cache[cache_key]
            if not _is_expired(cached["timestamp"]):
                # Update hit count
                cached["hit_count"] = cached.get("hit_count", 0) + 1
                cached["last_hit"] = datetime.now().isoformat()
                _save_cache(RESULT_CACHE_FILE, cache)

                logger.info(f"Cache HIT (exact): {question[:50]}...")
                return (cached["sql"], cached["result"], cached["metadata"])

        # Try fuzzy matching if enabled
        if fuzzy_match:
            for key, cached in cache.items():
                if not _is_expired(cached["timestamp"]):
                    if _fuzzy_match_query(question, cached["question"]):
                        # Update hit count
                        cached["hit_count"] = cached.get("hit_count", 0) + 1
                        cached["last_hit"] = datetime.now().isoformat()
                        _save_cache(RESULT_CACHE_FILE, cache)

                        logger.info(f"Cache HIT (fuzzy): {question[:50]}... matched {cached['question'][:50]}...")
                        return (cached["sql"], cached["result"], cached["metadata"])

        logger.info(f"Cache MISS: {question[:50]}...")
        return None

    except Exception as e:
        logger.error(f"Error retrieving cached result: {e}")
        return None


def cache_sql_generation(question: str, sql: str, metadata: Dict = None):
    """
    Cache an LLM-generated SQL query.

    Args:
        question: Natural language question
        sql: Generated SQL query
        metadata: Additional metadata (tokens used, model, etc.)
    """
    try:
        cache = _load_cache(SQL_CACHE_FILE)

        cache_key = hashlib.md5(question.lower().encode()).hexdigest()

        cache[cache_key] = {
            "question": question,
            "sql": sql,
            "metadata": metadata or {},
            "timestamp": datetime.now().isoformat(),
            "reuse_count": cache.get(cache_key, {}).get("reuse_count", 0)
        }

        _save_cache(SQL_CACHE_FILE, cache)
        logger.info(f"Cached SQL generation for: {question[:50]}...")

    except Exception as e:
        logger.error(f"Error caching SQL generation: {e}")


def get_cached_sql(question: str, fuzzy_match: bool = True, threshold: float = 0.92) -> Optional[Tuple[str, Dict]]:
    """
    Retrieve cached SQL for a question.

    Args:
        question: Natural language question
        fuzzy_match: If True, use fuzzy matching
        threshold: Similarity threshold for fuzzy matching (0.0-1.0)

    Returns:
        Tuple of (sql, metadata) if found, None otherwise
    """
    try:
        cache = _load_cache(SQL_CACHE_FILE)

        # Try exact match
        cache_key = hashlib.md5(question.lower().encode()).hexdigest()
        if cache_key in cache:
            cached = cache[cache_key]
            if not _is_expired(cached["timestamp"], expiry_hours=168):  # SQL cache lasts 1 week
                cached["reuse_count"] = cached.get("reuse_count", 0) + 1
                cached["last_reuse"] = datetime.now().isoformat()
                _save_cache(SQL_CACHE_FILE, cache)

                logger.info(f"SQL Cache HIT (exact): {question[:50]}...")
                return (cached["sql"], cached["metadata"])

        # Try fuzzy matching
        if fuzzy_match:
            for key, cached in cache.items():
                if not _is_expired(cached["timestamp"], expiry_hours=168):
                    similarity = SequenceMatcher(None, question.lower(), cached["question"].lower()).ratio()
                    if similarity >= threshold:
                        cached["reuse_count"] = cached.get("reuse_count", 0) + 1
                        cached["last_reuse"] = datetime.now().isoformat()
                        _save_cache(SQL_CACHE_FILE, cache)

                        logger.info(f"SQL Cache HIT (fuzzy {similarity:.2f}): {question[:50]}...")
                        return (cached["sql"], cached["metadata"])

        logger.info(f"SQL Cache MISS: {question[:50]}...")
        return None

    except Exception as e:
        logger.error(f"Error retrieving cached SQL: {e}")
        return None


def get_cache_stats() -> Dict:
    """Get statistics about cache usage and effectiveness."""
    try:
        result_cache = _load_cache(RESULT_CACHE_FILE)
        sql_cache = _load_cache(SQL_CACHE_FILE)

        # Calculate stats
        total_result_entries = len(result_cache)
        total_sql_entries = len(sql_cache)

        total_result_hits = sum(entry.get("hit_count", 0) for entry in result_cache.values())
        total_sql_reuses = sum(entry.get("reuse_count", 0) for entry in sql_cache.values())

        # Find most popular
        most_used_result = max(result_cache.values(), key=lambda x: x.get("hit_count", 0)) if result_cache else None
        most_reused_sql = max(sql_cache.values(), key=lambda x: x.get("reuse_count", 0)) if sql_cache else None

        return {
            "result_cache": {
                "total_entries": total_result_entries,
                "total_hits": total_result_hits,
                "most_popular": most_used_result["question"] if most_used_result else None,
                "most_popular_hits": most_used_result.get("hit_count", 0) if most_used_result else 0
            },
            "sql_cache": {
                "total_entries": total_sql_entries,
                "total_reuses": total_sql_reuses,
                "most_reused": most_reused_sql["question"] if most_reused_sql else None,
                "most_reused_count": most_reused_sql.get("reuse_count", 0) if most_reused_sql else 0
            },
            "cache_size_mb": (
                (RESULT_CACHE_FILE.stat().st_size if RESULT_CACHE_FILE.exists() else 0) +
                (SQL_CACHE_FILE.stat().st_size if SQL_CACHE_FILE.exists() else 0)
            ) / (1024 * 1024)
        }

    except Exception as e:
        logger.error(f"Error getting cache stats: {e}")
        return {}


def clear_expired_cache():
    """Remove expired entries from both caches."""
    try:
        # Clean result cache
        result_cache = _load_cache(RESULT_CACHE_FILE)
        result_cache = {k: v for k, v in result_cache.items() if not _is_expired(v["timestamp"])}
        _save_cache(RESULT_CACHE_FILE, result_cache)

        # Clean SQL cache
        sql_cache = _load_cache(SQL_CACHE_FILE)
        sql_cache = {k: v for k, v in sql_cache.items() if not _is_expired(v["timestamp"], expiry_hours=168)}
        _save_cache(SQL_CACHE_FILE, sql_cache)

        logger.info("Cleared expired cache entries")
        return True

    except Exception as e:
        logger.error(f"Error clearing expired cache: {e}")
        return False


def clear_all_cache():
    """Clear all cached data."""
    try:
        _save_cache(RESULT_CACHE_FILE, {})
        _save_cache(SQL_CACHE_FILE, {})
        logger.info("Cleared all cache")
        return True
    except Exception as e:
        logger.error(f"Error clearing cache: {e}")
        return False
