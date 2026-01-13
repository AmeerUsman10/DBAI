"""
Conversation Learning System

Intelligent learning module that captures and applies query patterns from user interactions.
Designed to improve AI responses over time through pattern recognition and user feedback.
"""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)

LEARNINGS_FILE = Path(__file__).parent.parent / "conversation_learnings.json"


def load_learnings() -> Dict:
    """Load all conversation learnings with error handling."""
    try:
        if LEARNINGS_FILE.exists():
            with open(LEARNINGS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        logger.info("Creating new learnings file")
        return _create_default_structure()
    except Exception as e:
        logger.error(f"Error loading learnings: {e}")
        return _create_default_structure()


def _create_default_structure() -> Dict:
    """Create default learnings structure."""
    return {
        "version": "1.0",
        "learnings": [],
        "metadata": {
            "total_learnings": 0,
            "last_updated": None,
            "total_queries_processed": 0,
            "clarifications_provided": 0,
            "successful_patterns": 0
        },
        "categories": {
            "supplier_queries": [],
            "amount_calculations": [],
            "inventory_checks": [],
            "department_analysis": [],
            "time_based_queries": []
        }
    }


def save_learning(
    original_query: str,
    clarified_query: str,
    sql_query: str,
    feedback: str = "positive",
    category: str = "general"
) -> bool:
    """
    Save a learning pattern from successful query interaction.

    Args:
        original_query: The original vague/unclear query
        clarified_query: The clarified interpretation
        sql_query: The SQL query that was generated
        feedback: User feedback (positive/negative/neutral)
        category: Query category for better organization

    Returns:
        True if saved successfully
    """
    try:
        data = load_learnings()

        # Check for similar existing learning
        similar_learning = _find_similar_learning(data["learnings"], original_query)

        if similar_learning:
            # Update existing learning
            similar_learning["usage_count"] = similar_learning.get("usage_count", 0) + 1
            similar_learning["last_used"] = datetime.now().isoformat()
            similar_learning["clarified_query"] = clarified_query
            similar_learning["sql_query"] = sql_query
            similar_learning["feedback_history"].append({
                "timestamp": datetime.now().isoformat(),
                "feedback": feedback
            })
            logger.info(f"Updated existing learning: {original_query}")
        else:
            # Create new learning
            new_learning = {
                "id": len(data["learnings"]) + 1,
                "timestamp": datetime.now().isoformat(),
                "original_query": original_query,
                "clarified_query": clarified_query,
                "sql_query": sql_query,
                "category": category,
                "feedback": feedback,
                "usage_count": 1,
                "last_used": datetime.now().isoformat(),
                "feedback_history": [{
                    "timestamp": datetime.now().isoformat(),
                    "feedback": feedback
                }]
            }
            data["learnings"].append(new_learning)

            # Add to category
            if category in data["categories"]:
                data["categories"][category].append(new_learning["id"])

            logger.info(f"Saved new learning: {original_query} -> {clarified_query}")

        # Update metadata
        data["metadata"]["total_learnings"] = len(data["learnings"])
        data["metadata"]["last_updated"] = datetime.now().isoformat()
        data["metadata"]["total_queries_processed"] = data["metadata"].get("total_queries_processed", 0) + 1
        if feedback == "positive":
            data["metadata"]["successful_patterns"] = data["metadata"].get("successful_patterns", 0) + 1

        # Save to file
        with open(LEARNINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        # Best-effort dual-write to SQLite knowledge store
        try:
            from src.knowledge_store import insert_learning, init_store
            init_store()
            insert_learning({
                "original_query": original_query,
                "clarified_query": clarified_query,
                "sql": sql_query,
                "outcome": feedback,
                "usage_count": 1
            })
        except Exception:
            pass

        return True

    except Exception as e:
        logger.error(f"Error saving learning: {e}", exc_info=True)
        return False


def _find_similar_learning(learnings: List[Dict], query: str) -> Optional[Dict]:
    """Find similar learning using fuzzy matching."""
    query_lower = query.lower()

    for learning in learnings:
        similarity = SequenceMatcher(
            None,
            learning["original_query"].lower(),
            query_lower
        ).ratio()

        # 85% similarity threshold
        if similarity > 0.85:
            return learning

    return None


def get_relevant_learnings(query: str, limit: int = 5) -> List[Dict]:
    """
    Find relevant past learnings for a query using intelligent matching.

    Args:
        query: Current user query
        limit: Maximum number of learnings to return

    Returns:
        List of relevant learning dictionaries, sorted by relevance
    """
    try:
        data = load_learnings()
        learnings = data.get("learnings", [])

        if not learnings:
            return []

        # Calculate relevance scores
        scored_learnings = []
        query_lower = query.lower()
        query_words = set(query_lower.split())

        for learning in learnings:
            original_lower = learning["original_query"].lower()
            original_words = set(original_lower.split())

            # Calculate similarity score
            similarity = SequenceMatcher(None, query_lower, original_lower).ratio()

            # Word overlap bonus
            word_overlap = len(query_words & original_words) / max(len(query_words), len(original_words))
            similarity += word_overlap * 0.2

            # Substring match bonus
            if query_lower in original_lower or original_lower in query_lower:
                similarity += 0.2

            # Usage count boost (popular patterns)
            usage_boost = min(learning.get("usage_count", 1) * 0.01, 0.15)
            similarity += usage_boost

            # Positive feedback boost
            if learning.get("feedback") == "positive":
                similarity += 0.05

            # Only include if reasonably relevant
            if similarity > 0.3:
                scored_learnings.append((similarity, learning))

        # Sort by similarity and return top results
        scored_learnings.sort(key=lambda x: x[0], reverse=True)
        relevant = [learning for score, learning in scored_learnings[:limit]]

        logger.info(f"Found {len(relevant)} relevant learnings for: {query}")
        return relevant

    except Exception as e:
        logger.error(f"Error getting relevant learnings: {e}")
        return []


def format_learnings_for_prompt(learnings: List[Dict]) -> str:
    """
    Format learnings into context for LLM prompts.

    Args:
        learnings: List of learning dictionaries

    Returns:
        Formatted string for prompt injection
    """
    if not learnings:
        return ""

    formatted = "\nLEARNED QUERY PATTERNS (from past team interactions):\n"
    for learning in learnings:
        formatted += f"  • When user says \"{learning['original_query']}\"\n"
        formatted += f"    They usually mean: \"{learning['clarified_query']}\"\n"
        formatted += f"    Example SQL: {learning['sql_query']}\n"
        formatted += f"    (Used {learning.get('usage_count', 1)} times successfully)\n"

    return formatted


def get_learning_stats() -> Dict:
    """Get comprehensive statistics about stored learnings."""
    try:
        data = load_learnings()
        metadata = data.get("metadata", {})

        # Find most used pattern
        learnings = data.get("learnings", [])
        most_used = max(learnings, key=lambda x: x.get("usage_count", 0)) if learnings else None

        return {
            "total": metadata.get("total_learnings", 0),
            "last_updated": metadata.get("last_updated"),
            "total_queries": metadata.get("total_queries_processed", 0),
            "clarifications": metadata.get("clarifications_provided", 0),
            "successful": metadata.get("successful_patterns", 0),
            "most_used": most_used
        }
    except Exception as e:
        logger.error(f"Error getting learning stats: {e}")
        return {
            "total": 0,
            "last_updated": None,
            "total_queries": 0,
            "clarifications": 0,
            "successful": 0,
            "most_used": None
        }


def categorize_query(query: str) -> str:
    """Automatically categorize a query for better organization."""
    query_lower = query.lower()

    if 'supplier' in query_lower:
        return 'supplier_queries'
    elif any(term in query_lower for term in ['amount', 'total', 'sum', 'price']):
        return 'amount_calculations'
    elif any(term in query_lower for term in ['stock', 'inventory', 'lbs', 'meters', 'bags']):
        return 'inventory_checks'
    elif 'department' in query_lower:
        return 'department_analysis'
    elif any(term in query_lower for term in ['date', 'month', 'year', 'recent', 'last']):
        return 'time_based_queries'
    else:
        return 'general'


def export_learnings_report() -> str:
    """Generate a human-readable report of all learnings."""
    try:
        data = load_learnings()
        stats = get_learning_stats()

        report = "=== CONVERSATION LEARNING REPORT ===\n\n"
        report += f"Total Patterns Learned: {stats['total']}\n"
        report += f"Total Queries Processed: {stats['total_queries']}\n"
        report += f"Successful Patterns: {stats['successful']}\n"
        report += f"Last Updated: {stats['last_updated']}\n\n"

        if stats['most_used']:
            report += f"Most Used Pattern:\n"
            report += f"  '{stats['most_used']['original_query']}' → '{stats['most_used']['clarified_query']}'\n"
            report += f"  Used {stats['most_used']['usage_count']} times\n\n"

        report += "=== LEARNED PATTERNS BY CATEGORY ===\n\n"
        for category, ids in data.get("categories", {}).items():
            if ids:
                report += f"{category.upper().replace('_', ' ')}:\n"
                category_learnings = [l for l in data["learnings"] if l["id"] in ids]
                for learning in category_learnings[:5]:  # Top 5 per category
                    report += f"  • {learning['original_query']} → {learning['clarified_query']}\n"
                report += "\n"

        return report

    except Exception as e:
        logger.error(f"Error generating report: {e}")
        return "Error generating learning report"
