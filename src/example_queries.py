"""
Example Queries Module
Manages example-based learning - stores successful query patterns for reuse.
Replaces learnings.py and quick_training.py with a simpler approach.
"""
import json
import logging
import uuid
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional
from difflib import SequenceMatcher
from src.utils.atomic_write import atomic_write_json, atomic_read_json

logger = logging.getLogger(__name__)

EXAMPLES_FILE = Path(__file__).parent.parent / "example_queries.json"


def _create_default_structure() -> Dict:
    """Create default examples structure."""
    return {
        "version": "1.0",
        "examples": [],
        "metadata": {
            "total_examples": 0,
            "last_updated": None
        }
    }


def load_examples() -> Dict:
    """
    Load example queries from file.
    
    Returns:
        Dictionary with examples array
    """
    try:
        if EXAMPLES_FILE.exists():
            data = atomic_read_json(EXAMPLES_FILE, default=_create_default_structure())
            if data is None:
                return _create_default_structure()
            return data
        else:
            default = _create_default_structure()
            save_examples(default)
            return default
    except Exception as e:
        logger.error(f"Error loading examples: {e}", exc_info=True)
        return _create_default_structure()


def save_examples(examples_data: Dict) -> bool:
    """
    Save example queries to file.
    
    Args:
        examples_data: Dictionary with examples array
        
    Returns:
        True if saved successfully
    """
    try:
        atomic_write_json(EXAMPLES_FILE, examples_data)
        logger.info("Example queries saved successfully")
        return True
    except Exception as e:
        logger.error(f"Error saving examples: {e}", exc_info=True)
        return False


def add_example(
    user_query: str,
    sql_query: str,
    database_type: str,
    explanation: str = "",
    source: str = "manual"
) -> str:
    """
    Add a new example query.
    
    Args:
        user_query: Natural language query
        sql_query: Corresponding SQL query
        database_type: "mssql" or "oracle" or "mysql"
        explanation: Optional explanation of what the query does
        source: Where this example came from ("manual", "uploaded_report", "chat")
        
    Returns:
        Example ID
    """
    try:
        data = load_examples()
        
        example_id = str(uuid.uuid4())[:8]
        new_example = {
            "id": example_id,
            "user_query": user_query,
            "sql_query": sql_query,
            "database_type": database_type.lower(),
            "explanation": explanation,
            "created_at": datetime.now().isoformat(),
            "usage_count": 0,
            "success_rate": 1.0,
            "source": source
        }
        
        data["examples"].append(new_example)
        data["metadata"]["total_examples"] = len(data["examples"])
        data["metadata"]["last_updated"] = datetime.now().isoformat()
        
        if save_examples(data):
            logger.info(f"Added example: {example_id}")
            return example_id
        else:
            logger.error("Failed to save example")
            return ""
    except Exception as e:
        logger.error(f"Error adding example: {e}", exc_info=True)
        return ""


def get_relevant_examples(user_query: str, limit: int = 3) -> List[Dict]:
    """
    Find relevant examples for a user query using similarity matching.
    
    Args:
        user_query: Current user query
        limit: Maximum number of examples to return
        
    Returns:
        List of relevant example dictionaries, sorted by relevance
    """
    try:
        data = load_examples()
        examples = data.get("examples", [])
        
        if not examples:
            return []
        
        # Calculate similarity scores
        scored_examples = []
        query_lower = user_query.lower()
        query_words = set(query_lower.split())
        
        for example in examples:
            example_query = example.get("user_query", "").lower()
            example_words = set(example_query.split())
            
            # Calculate similarity
            similarity = SequenceMatcher(None, query_lower, example_query).ratio()
            
            # Word overlap bonus
            if query_words and example_words:
                word_overlap = len(query_words & example_words) / max(len(query_words), len(example_words))
                similarity += word_overlap * 0.2
            
            # Usage count boost (popular patterns)
            usage_boost = min(example.get("usage_count", 0) * 0.01, 0.15)
            similarity += usage_boost
            
            # Success rate boost
            success_rate = example.get("success_rate", 1.0)
            similarity += success_rate * 0.1
            
            # Only include if reasonably relevant
            if similarity > 0.3:
                scored_examples.append((similarity, example))
        
        # Sort by similarity and return top results
        scored_examples.sort(key=lambda x: x[0], reverse=True)
        relevant = [example for score, example in scored_examples[:limit]]
        
        logger.info(f"Found {len(relevant)} relevant examples for: {user_query[:50]}")
        return relevant
        
    except Exception as e:
        logger.error(f"Error getting relevant examples: {e}", exc_info=True)
        return []


def format_examples_for_prompt(examples: List[Dict]) -> str:
    """
    Format examples for inclusion in LLM prompts.
    
    Args:
        examples: List of example dictionaries
        
    Returns:
        Formatted string for prompt injection
    """
    if not examples:
        return ""
    
    formatted = "\nExample Queries (successful patterns to follow):\n\n"
    for i, example in enumerate(examples, 1):
        formatted += f"Example {i}:\n"
        formatted += f"  User said: \"{example['user_query']}\"\n"
        formatted += f"  SQL used: {example['sql_query']}\n"
        if example.get("explanation"):
            formatted += f"  Note: {example['explanation']}\n"
        formatted += "\n"
    
    formatted += "Follow these patterns when generating SQL for similar queries.\n"
    
    return formatted


def increment_usage(example_id: str, success: bool = True) -> None:
    """
    Increment usage count for an example and update success rate.
    
    Args:
        example_id: ID of the example
        success: Whether the usage was successful
    """
    try:
        data = load_examples()
        examples = data.get("examples", [])
        
        for example in examples:
            if example.get("id") == example_id:
                example["usage_count"] = example.get("usage_count", 0) + 1
                
                # Update success rate (simple moving average)
                current_rate = example.get("success_rate", 1.0)
                usage_count = example["usage_count"]
                if usage_count == 1:
                    example["success_rate"] = 1.0 if success else 0.0
                else:
                    # Weighted average: (old_rate * (count-1) + new_result) / count
                    example["success_rate"] = ((current_rate * (usage_count - 1)) + (1.0 if success else 0.0)) / usage_count
                
                data["metadata"]["last_updated"] = datetime.now().isoformat()
                save_examples(data)
                logger.info(f"Updated usage for example {example_id}")
                return
        
        logger.warning(f"Example {example_id} not found for usage update")
    except Exception as e:
        logger.error(f"Error incrementing usage: {e}", exc_info=True)


def delete_example(example_id: str) -> bool:
    """
    Delete an example by ID.
    
    Args:
        example_id: ID of the example to delete
        
    Returns:
        True if deleted successfully
    """
    try:
        data = load_examples()
        examples = data.get("examples", [])
        
        original_count = len(examples)
        data["examples"] = [e for e in examples if e.get("id") != example_id]
        
        if len(data["examples"]) < original_count:
            data["metadata"]["total_examples"] = len(data["examples"])
            data["metadata"]["last_updated"] = datetime.now().isoformat()
            if save_examples(data):
                logger.info(f"Deleted example {example_id}")
                return True
        
        return False
    except Exception as e:
        logger.error(f"Error deleting example: {e}", exc_info=True)
        return False


def get_example_stats() -> Dict:
    """
    Get statistics about stored examples.
    
    Returns:
        Dictionary with statistics
    """
    try:
        data = load_examples()
        examples = data.get("examples", [])
        
        total_usage = sum(e.get("usage_count", 0) for e in examples)
        avg_success = sum(e.get("success_rate", 1.0) for e in examples) / len(examples) if examples else 0.0
        
        return {
            "total_examples": len(examples),
            "total_usage": total_usage,
            "average_success_rate": round(avg_success, 2),
            "last_updated": data["metadata"].get("last_updated")
        }
    except Exception as e:
        logger.error(f"Error getting example stats: {e}", exc_info=True)
        return {
            "total_examples": 0,
            "total_usage": 0,
            "average_success_rate": 0.0,
            "last_updated": None
        }
