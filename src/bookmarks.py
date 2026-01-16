"""
Query Bookmarking System

Allows users to save, organize, and quickly access favorite queries.
"""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

BOOKMARKS_FILE = Path(__file__).parent.parent / "query_bookmarks.json"


def load_bookmarks() -> Dict:
    """Load bookmarks from file."""
    try:
        if BOOKMARKS_FILE.exists():
            with open(BOOKMARKS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return _create_default_structure()
    except Exception as e:
        logger.error(f"Error loading bookmarks: {e}")
        return _create_default_structure()


def _create_default_structure() -> Dict:
    """Create default bookmarks structure."""
    return {
        "version": "1.0",
        "bookmarks": [],
        "folders": {
            "daily_reports": {"name": "Daily Reports", "queries": []},
            "kpis": {"name": "Key Metrics", "queries": []},
            "inventory": {"name": "Inventory Queries", "queries": []},
            "suppliers": {"name": "Supplier Analysis", "queries": []},
            "custom": {"name": "My Queries", "queries": []}
        },
        "metadata": {
            "total_bookmarks": 0,
            "last_updated": None
        }
    }


def save_bookmark(
    question: str,
    sql: str = "",
    folder: str = "custom",
    name: str = "",
    description: str = "",
    tags: List[str] = None
) -> bool:
    """
    Save a query as a bookmark.
    
    Args:
        question: The natural language query
        sql: The SQL query (optional)
        folder: Folder to save in
        name: Custom name for the bookmark
        description: Description of what this query does
        tags: List of tags for categorization
        
    Returns:
        True if saved successfully
    """
    try:
        data = load_bookmarks()
        
        bookmark_id = len(data["bookmarks"]) + 1
        
        bookmark = {
            "id": bookmark_id,
            "name": name or question[:50],
            "question": question,
            "sql": sql,
            "description": description,
            "folder": folder,
            "tags": tags or [],
            "created_at": datetime.now().isoformat(),
            "last_used": None,
            "use_count": 0
        }
        
        data["bookmarks"].append(bookmark)
        
        # Add to folder
        if folder in data["folders"]:
            data["folders"][folder]["queries"].append(bookmark_id)
        
        data["metadata"]["total_bookmarks"] = len(data["bookmarks"])
        data["metadata"]["last_updated"] = datetime.now().isoformat()
        
        with open(BOOKMARKS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Saved bookmark: {name or question[:30]}")
        return True
        
    except Exception as e:
        logger.error(f"Error saving bookmark: {e}")
        return False


def get_bookmark(bookmark_id: int) -> Optional[Dict]:
    """Get a specific bookmark by ID."""
    try:
        data = load_bookmarks()
        for bookmark in data["bookmarks"]:
            if bookmark["id"] == bookmark_id:
                return bookmark
        return None
    except Exception as e:
        logger.error(f"Error getting bookmark: {e}")
        return None


def update_bookmark_usage(bookmark_id: int):
    """Update usage statistics for a bookmark."""
    try:
        data = load_bookmarks()
        
        for bookmark in data["bookmarks"]:
            if bookmark["id"] == bookmark_id:
                bookmark["use_count"] = bookmark.get("use_count", 0) + 1
                bookmark["last_used"] = datetime.now().isoformat()
                break
        
        with open(BOOKMARKS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
    except Exception as e:
        logger.error(f"Error updating bookmark usage: {e}")


def delete_bookmark(bookmark_id: int) -> bool:
    """Delete a bookmark."""
    try:
        data = load_bookmarks()
        
        # Remove from bookmarks list
        data["bookmarks"] = [b for b in data["bookmarks"] if b["id"] != bookmark_id]
        
        # Remove from folders
        for folder in data["folders"].values():
            if bookmark_id in folder["queries"]:
                folder["queries"].remove(bookmark_id)
        
        data["metadata"]["total_bookmarks"] = len(data["bookmarks"])
        data["metadata"]["last_updated"] = datetime.now().isoformat()
        
        with open(BOOKMARKS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Deleted bookmark: {bookmark_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error deleting bookmark: {e}")
        return False


def get_bookmarks_by_folder(folder: str = None) -> List[Dict]:
    """Get all bookmarks, optionally filtered by folder."""
    try:
        data = load_bookmarks()
        
        if folder:
            if folder in data["folders"]:
                bookmark_ids = data["folders"][folder]["queries"]
                return [b for b in data["bookmarks"] if b["id"] in bookmark_ids]
            return []
        
        return data["bookmarks"]
        
    except Exception as e:
        logger.error(f"Error getting bookmarks by folder: {e}")
        return []


def get_most_used_bookmarks(limit: int = 10) -> List[Dict]:
    """Get most frequently used bookmarks."""
    try:
        data = load_bookmarks()
        bookmarks = data["bookmarks"]
        bookmarks.sort(key=lambda x: x.get("use_count", 0), reverse=True)
        return bookmarks[:limit]
    except Exception as e:
        logger.error(f"Error getting most used bookmarks: {e}")
        return []


def search_bookmarks(query: str) -> List[Dict]:
    """Search bookmarks by name, question, description, or tags."""
    try:
        data = load_bookmarks()
        query_lower = query.lower()
        
        results = []
        for bookmark in data["bookmarks"]:
            if (query_lower in bookmark["name"].lower() or
                query_lower in bookmark["question"].lower() or
                query_lower in bookmark.get("description", "").lower() or
                any(query_lower in tag.lower() for tag in bookmark.get("tags", []))):
                results.append(bookmark)
        
        return results
        
    except Exception as e:
        logger.error(f"Error searching bookmarks: {e}")
        return []
