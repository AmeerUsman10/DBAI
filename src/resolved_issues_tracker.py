"""
Resolved Issues Tracker
Prevents displaying already-fixed issues in diagnostics.
"""
import json
import logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

RESOLVED_ISSUES_FILE = Path(__file__).parent.parent / "logs" / "resolved_issues.json"


def load_resolved_issues():
    """Load list of resolved issue hashes."""
    if not RESOLVED_ISSUES_FILE.exists():
        return {"resolved": [], "last_cleared": datetime.now().isoformat()}

    try:
        with open(RESOLVED_ISSUES_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading resolved issues: {e}")
        return {"resolved": [], "last_cleared": datetime.now().isoformat()}


def save_resolved_issues(data):
    """Save resolved issues list."""
    try:
        RESOLVED_ISSUES_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(RESOLVED_ISSUES_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving resolved issues: {e}")


def hash_issue(query: str, issue_type: str) -> str:
    """Create a hash for a feedback issue to track resolution."""
    import hashlib
    content = f"{query}:{issue_type}".lower().strip()
    return hashlib.md5(content.encode()).hexdigest()[:12]


def is_issue_resolved(query: str, issue_type: str) -> bool:
    """Check if an issue has been marked as resolved."""
    issue_hash = hash_issue(query, issue_type)
    resolved = load_resolved_issues()
    return issue_hash in resolved.get("resolved", [])


def mark_issue_resolved(query: str, issue_type: str):
    """Mark an issue as resolved (don't show again)."""
    issue_hash = hash_issue(query, issue_type)
    resolved = load_resolved_issues()
    if issue_hash not in resolved["resolved"]:
        resolved["resolved"].append(issue_hash)
        resolved["last_updated"] = datetime.now().isoformat()
        save_resolved_issues(resolved)
        logger.info(f"Marked issue as resolved: {query[:30]}... ({issue_type})")


def clear_resolved_issues():
    """Clear all resolved issues (for fresh session)."""
    default_data = {"resolved": [], "last_cleared": datetime.now().isoformat()}
    save_resolved_issues(default_data)
    logger.info("Cleared all resolved issues - fresh session started")


def get_session_summary():
    """Get summary of resolved issues in this session."""
    resolved = load_resolved_issues()
    return {
        "total_resolved": len(resolved.get("resolved", [])),
        "last_cleared": resolved.get("last_cleared"),
        "last_updated": resolved.get("last_updated")
    }
