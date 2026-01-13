"""
Schema Mapping Module
Manages natural language to database schema mappings (table and column aliases).
"""
import json
import logging
from pathlib import Path
from typing import Dict, Optional, Tuple
from src.utils.atomic_write import atomic_write_json, atomic_read_json

logger = logging.getLogger(__name__)

MAPPINGS_FILE = Path(__file__).parent.parent / "schema_mappings.json"


def _create_default_mappings() -> Dict:
    """Create default empty mappings structure."""
    return {
        "table_aliases": {},
        "column_aliases": {},
        "version": "1.0"
    }


def load_mappings() -> Dict:
    """
    Load schema mappings from file.
    
    Returns:
        Dictionary with table_aliases and column_aliases
    """
    try:
        if MAPPINGS_FILE.exists():
            data = atomic_read_json(MAPPINGS_FILE, default=_create_default_mappings())
            if data is None:
                return _create_default_mappings()
            return data
        else:
            # Create default file
            default = _create_default_mappings()
            save_mappings(default)
            return default
    except Exception as e:
        logger.error(f"Error loading mappings: {e}", exc_info=True)
        return _create_default_mappings()


def save_mappings(mappings: Dict) -> bool:
    """
    Save schema mappings to file.
    
    Args:
        mappings: Dictionary with table_aliases and column_aliases
        
    Returns:
        True if saved successfully
    """
    try:
        atomic_write_json(MAPPINGS_FILE, mappings)
        logger.info("Schema mappings saved successfully")
        return True
    except Exception as e:
        logger.error(f"Error saving mappings: {e}", exc_info=True)
        return False


def save_table_mapping(alias: str, actual_table: str) -> bool:
    """
    Save a table alias mapping.
    
    Args:
        alias: Natural language term (e.g., "customers")
        actual_table: Actual table name (e.g., "cust_tbl_2024")
        
    Returns:
        True if saved successfully
    """
    try:
        mappings = load_mappings()
        mappings["table_aliases"][alias.lower()] = actual_table
        return save_mappings(mappings)
    except Exception as e:
        logger.error(f"Error saving table mapping: {e}", exc_info=True)
        return False


def save_column_mapping(alias: str, table_name: str, column_name: str) -> bool:
    """
    Save a column alias mapping.
    
    Args:
        alias: Natural language term (e.g., "customer name")
        table_name: Actual table name (e.g., "cust_tbl_2024")
        column_name: Actual column name (e.g., "cust_nm")
        
    Returns:
        True if saved successfully
    """
    try:
        mappings = load_mappings()
        mappings["column_aliases"][alias.lower()] = {
            "table": table_name,
            "column": column_name
        }
        return save_mappings(mappings)
    except Exception as e:
        logger.error(f"Error saving column mapping: {e}", exc_info=True)
        return False


def resolve_table_alias(user_term: str) -> Optional[str]:
    """
    Resolve a natural language term to actual table name.
    
    Args:
        user_term: Natural language term (e.g., "customers")
        
    Returns:
        Actual table name if found, None otherwise
    """
    try:
        mappings = load_mappings()
        return mappings["table_aliases"].get(user_term.lower())
    except Exception as e:
        logger.error(f"Error resolving table alias: {e}", exc_info=True)
        return None


def resolve_column_alias(user_term: str) -> Optional[Dict]:
    """
    Resolve a natural language term to actual table and column.
    
    Args:
        user_term: Natural language term (e.g., "customer name")
        
    Returns:
        Dictionary with "table" and "column" keys if found, None otherwise
    """
    try:
        mappings = load_mappings()
        return mappings["column_aliases"].get(user_term.lower())
    except Exception as e:
        logger.error(f"Error resolving column alias: {e}", exc_info=True)
        return None


def delete_table_mapping(alias: str) -> bool:
    """
    Delete a table alias mapping.
    
    Args:
        alias: Natural language term to remove
        
    Returns:
        True if deleted successfully
    """
    try:
        mappings = load_mappings()
        if alias.lower() in mappings["table_aliases"]:
            del mappings["table_aliases"][alias.lower()]
            return save_mappings(mappings)
        return False
    except Exception as e:
        logger.error(f"Error deleting table mapping: {e}", exc_info=True)
        return False


def delete_column_mapping(alias: str) -> bool:
    """
    Delete a column alias mapping.
    
    Args:
        alias: Natural language term to remove
        
    Returns:
        True if deleted successfully
    """
    try:
        mappings = load_mappings()
        if alias.lower() in mappings["column_aliases"]:
            del mappings["column_aliases"][alias.lower()]
            return save_mappings(mappings)
        return False
    except Exception as e:
        logger.error(f"Error deleting column mapping: {e}", exc_info=True)
        return False


def get_all_mappings() -> Dict:
    """
    Get all current mappings.
    
    Returns:
        Dictionary with table_aliases and column_aliases
    """
    return load_mappings()


def format_mappings_for_prompt() -> str:
    """
    Format mappings for inclusion in LLM prompts.
    
    Returns:
        Formatted string describing mappings
    """
    try:
        mappings = load_mappings()
        output = ""
        
        if mappings["table_aliases"]:
            output += "Table Mappings (what users call things):\n"
            for alias, actual in mappings["table_aliases"].items():
                output += f"  - When user says '{alias}' → use table '{actual}'\n"
            output += "\n"
        
        if mappings["column_aliases"]:
            output += "Column Mappings (what users call things):\n"
            for alias, info in mappings["column_aliases"].items():
                output += f"  - When user says '{alias}' → use table '{info['table']}', column '{info['column']}'\n"
            output += "\n"
        
        return output
    except Exception as e:
        logger.error(f"Error formatting mappings: {e}", exc_info=True)
        return ""
