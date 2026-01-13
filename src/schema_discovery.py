"""
Schema Discovery Module
Auto-discovers database schema structure for MySQL and Oracle databases.
"""
import logging
from typing import List, Dict, Optional
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


def discover_tables(engine: Engine) -> List[str]:
    """
    Get all table names from the database.

    Args:
        engine: SQLAlchemy engine

    Returns:
        List of table names
    """
    try:
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        logger.info(f"Discovered {len(tables)} tables")
        return tables
    except Exception as e:
        logger.error(f"Error discovering tables: {e}", exc_info=True)
        return []


def discover_columns(engine: Engine, table_name: str) -> List[Dict]:
    """
    Get all columns for a specific table with their types.

    Args:
        engine: SQLAlchemy engine
        table_name: Name of the table

    Returns:
        List of column dictionaries with name, type, nullable, default
    """
    try:
        inspector = inspect(engine)
        columns = inspector.get_columns(table_name)

        result = []
        for col in columns:
            result.append({
                "name": col["name"],
                "type": str(col["type"]),
                "nullable": col.get("nullable", True),
                "default": str(col.get("default", "")) if col.get("default") else None
            })

        logger.info(f"Discovered {len(result)} columns for table {table_name}")
        return result
    except Exception as e:
        logger.error(f"Error discovering columns for {table_name}: {e}", exc_info=True)
        return []


def get_schema_summary(engine: Engine) -> Dict:
    """
    Get complete schema overview including all tables and their columns.

    Args:
        engine: SQLAlchemy engine

    Returns:
        Dictionary with schema structure:
        {
            "tables": [
                {
                    "name": "table_name",
                    "columns": [
                        {"name": "col_name", "type": "VARCHAR", ...}
                    ]
                }
            ]
        }
    """
    try:
        tables = discover_tables(engine)

        schema = {
            "tables": []
        }

        for table_name in tables:
            columns = discover_columns(engine, table_name)
            schema["tables"].append({
                "name": table_name,
                "columns": columns
            })

        logger.info(f"Schema summary: {len(schema['tables'])} tables")
        return schema
    except Exception as e:
        logger.error(f"Error getting schema summary: {e}", exc_info=True)
        return {"tables": []}


def get_table_info_string(engine: Engine) -> str:
    """
    Get schema information as a formatted string for LLM prompts.

    Args:
        engine: SQLAlchemy engine

    Returns:
        Formatted string describing the schema
    """
    try:
        schema = get_schema_summary(engine)

        if not schema["tables"]:
            return "No tables found in database."

        output = "Database Schema:\n\n"

        for table in schema["tables"]:
            output += f"Table: {table['name']}\n"
            output += "Columns:\n"
            for col in table["columns"]:
                nullable = "NULL" if col["nullable"] else "NOT NULL"
                default = f" DEFAULT {col['default']}" if col["default"] else ""
                output += f"  - {col['name']}: {col['type']} {nullable}{default}\n"
            output += "\n"

        return output
    except Exception as e:
        logger.error(f"Error formatting schema info: {e}", exc_info=True)
        return f"Error retrieving schema: {str(e)}"
