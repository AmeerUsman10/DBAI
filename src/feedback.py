"""
Feedback Management System
Handles user feedback collection, storage, and analytics for DBAI responses.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
from src.utils.atomic_write import atomic_write_json, atomic_read_json

logger = logging.getLogger(__name__)

# Feedback storage location
FEEDBACK_DIR = Path(__file__).parent.parent / "logs" / "feedback"
FEEDBACK_FILE = FEEDBACK_DIR / "feedback_data.json"
SUGGESTIONS_DIR = Path(__file__).parent.parent / "logs" / "training"
SUGGESTIONS_FILE = SUGGESTIONS_DIR / "rule_suggestions.json"

def ensure_feedback_dir():
    """Ensure feedback directory exists."""
    FEEDBACK_DIR.mkdir(parents=True, exist_ok=True)
    SUGGESTIONS_DIR.mkdir(parents=True, exist_ok=True)

def load_feedback_data() -> Dict:
    """Load feedback data from file."""
    ensure_feedback_dir()
    try:
        data = atomic_read_json(FEEDBACK_FILE, default={"feedback_events": [], "statistics": {}})
        if data is None:
            data = {"feedback_events": [], "statistics": {}}
        return data
    except Exception as e:
        logger.error(f"Error loading feedback data: {e}")
        return {"feedback_events": [], "statistics": {}}

def save_feedback_data(data: Dict):
    """Save feedback data to file."""
    ensure_feedback_dir()
    try:
        atomic_write_json(FEEDBACK_FILE, data)
    except Exception as e:
        logger.error(f"Error saving feedback data: {e}")

def save_feedback(
    message_id: str,
    feedback_type: str,
    question: str,
    sql_query: Optional[str] = None,
    response: Optional[str] = None,
    feedback_text: Optional[str] = None,
    session_id: Optional[str] = None
) -> bool:
    """
    Save user feedback for a specific message.
    
    Args:
        message_id: Unique identifier for the message
        feedback_type: "thumbs_up" or "thumbs_down"
        question: User's original question
        sql_query: Generated SQL query (if applicable)
        response: AI response text
        feedback_text: Optional detailed feedback from user
        session_id: Session identifier
    
    Returns:
        True if saved successfully
    """
    try:
        data = load_feedback_data()
        
        # Create feedback event
        event = {
            "message_id": message_id,
            "timestamp": datetime.now().isoformat(),
            "feedback_type": feedback_type,
            "question": question,
            "sql_query": sql_query,
            "response_preview": response[:200] if response else None,
            "feedback_text": feedback_text,
            "session_id": session_id
        }
        
        # Add to events
        data["feedback_events"].append(event)
        
        # Update statistics
        update_statistics(data)
        
        # Save to file
        save_feedback_data(data)

        # Best-effort dual-write to SQLite knowledge store
        try:
            from src.knowledge_store import insert_feedback_event, init_store
            init_store()
            insert_feedback_event(event)
        except Exception:
            pass
        
        # Generate rule suggestion from negative feedback with comments
        try:
            if feedback_type == "thumbs_down" and feedback_text:
                suggestion = {
                    "timestamp": event["timestamp"],
                    "message_id": message_id,
                    "question": question,
                    "suggested_rule": f"For queries like '{question}': {feedback_text}",
                    "source": "feedback",
                    "session_id": session_id
                }
                _append_rule_suggestion(suggestion)
        except Exception as e:
            logger.warning(f"Failed to generate rule suggestion: {e}")

        logger.info(f"Feedback saved: {feedback_type} for message {message_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error saving feedback: {e}")
        return False

def update_statistics(data: Dict):
    """Update feedback statistics."""
    events = data["feedback_events"]
    total = len(events)
    
    if total == 0:
        data["statistics"] = {
            "total_feedback": 0,
            "thumbs_up": 0,
            "thumbs_down": 0,
            "satisfaction_rate": 0.0,
            "feedback_with_comments": 0,
            "last_updated": datetime.now().isoformat()
        }
        return
    
    thumbs_up = sum(1 for e in events if e["feedback_type"] == "thumbs_up")
    thumbs_down = sum(1 for e in events if e["feedback_type"] == "thumbs_down")
    with_comments = sum(1 for e in events if e.get("feedback_text"))
    
    data["statistics"] = {
        "total_feedback": total,
        "thumbs_up": thumbs_up,
        "thumbs_down": thumbs_down,
        "satisfaction_rate": round((thumbs_up / total * 100), 1) if total > 0 else 0.0,
        "feedback_with_comments": with_comments,
        "last_updated": datetime.now().isoformat()
    }

def get_feedback_statistics() -> Dict:
    """Get current feedback statistics."""
    data = load_feedback_data()
    return data.get("statistics", {
        "total_feedback": 0,
        "thumbs_up": 0,
        "thumbs_down": 0,
        "satisfaction_rate": 0.0,
        "feedback_with_comments": 0
    })

def get_recent_feedback(limit: int = 10) -> List[Dict]:
    """Get most recent feedback events."""
    data = load_feedback_data()
    events = data.get("feedback_events", [])
    
    # Sort by timestamp descending
    sorted_events = sorted(
        events,
        key=lambda x: x.get("timestamp", ""),
        reverse=True
    )
    
    return sorted_events[:limit]

def get_negative_feedback_with_comments(limit: int = 20) -> List[Dict]:
    """Get recent negative feedback with user comments."""
    data = load_feedback_data()
    events = data.get("feedback_events", [])
    
    # Filter for thumbs down with comments
    negative_with_comments = [
        e for e in events
        if e.get("feedback_type") == "thumbs_down" and e.get("feedback_text")
    ]
    
    # Sort by timestamp descending
    sorted_events = sorted(
        negative_with_comments,
        key=lambda x: x.get("timestamp", ""),
        reverse=True
    )
    
    return sorted_events[:limit]

def format_feedback_for_display(stats: Dict) -> str:
    """Format feedback statistics for markdown display."""
    total = stats.get("total_feedback", 0)
    
    if total == 0:
        return "### 📊 Feedback Statistics\n\nNo feedback collected yet. Users can provide feedback using 👍/👎 buttons after each response."
    
    thumbs_up = stats.get("thumbs_up", 0)
    thumbs_down = stats.get("thumbs_down", 0)
    satisfaction = stats.get("satisfaction_rate", 0)
    with_comments = stats.get("feedback_with_comments", 0)
    
    # Satisfaction emoji
    if satisfaction >= 80:
        emoji = "🌟"
    elif satisfaction >= 60:
        emoji = "😊"
    elif satisfaction >= 40:
        emoji = "😐"
    else:
        emoji = "😟"
    
    return f"""### 📊 Feedback Statistics

**Overall Satisfaction**: {emoji} **{satisfaction}%**

| Metric | Count |
|--------|-------|
| 👍 Positive Feedback | {thumbs_up} ({thumbs_up/total*100:.1f}%) |
| 👎 Negative Feedback | {thumbs_down} ({thumbs_down/total*100:.1f}%) |
| 💬 Detailed Comments | {with_comments} |
| 📈 Total Responses Rated | {total} |

*Last updated: {stats.get('last_updated', 'Unknown')[:19]}*
"""

def format_recent_feedback(events: List[Dict]) -> str:
    """Format recent feedback events for display."""
    if not events:
        return "No recent feedback to display."
    
    output = "### 📝 Recent Feedback\n\n"
    
    for event in events:
        feedback_type = event.get("feedback_type", "unknown")
        icon = "👍" if feedback_type == "thumbs_up" else "👎"
        timestamp = event.get("timestamp", "")[:19]
        question = event.get("question", "")[:80]
        feedback_text = event.get("feedback_text", "")
        
        output += f"**{icon} {timestamp}**\n"
        output += f"- Question: _{question}_\n"
        
        if feedback_text:
            output += f"- Comment: {feedback_text}\n"
        
        output += "\n"
    
    return output

# --- Rule Suggestions Helpers ---

def _append_rule_suggestion(suggestion: Dict):
    """Append a rule suggestion to the suggestions store."""
    ensure_feedback_dir()
    try:
        suggestions = atomic_read_json(SUGGESTIONS_FILE, default=[])
        if suggestions is None:
            suggestions = []
        suggestions.append(suggestion)
        atomic_write_json(SUGGESTIONS_FILE, suggestions)
    except Exception as e:
        logger.error(f"Error saving rule suggestion: {e}")


def get_rule_suggestions(limit: int = 20) -> List[Dict]:
    """Retrieve recent rule suggestions generated from feedback."""
    ensure_feedback_dir()
    try:
        suggestions = atomic_read_json(SUGGESTIONS_FILE, default=[])
        if not suggestions:
            return []
        # Sort newest first
        suggestions = sorted(suggestions, key=lambda s: s.get("timestamp",""), reverse=True)
        return suggestions[:limit]
    except Exception as e:
        logger.error(f"Error loading rule suggestions: {e}")
        return []
