"""
Database Management
Centralized SQLAlchemy engine creation and query execution.
Supports both legacy single-database and new multi-database config formats.
Build 30 - Phase 1: Multi-Database Support
"""
import logging
import json
from typing import Optional, Tuple, Any
from urllib.parse import quote_plus
import yaml
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from langchain_community.utilities import SQLDatabase
from src.llm import validate_sql

logger = logging.getLogger(__name__)

# Global engine and database instances
_engine: Optional[Engine] = None
_sql_database: Optional[SQLDatabase] = None

# Multi-database manager (lazy-loaded)
_db_manager = None

def _use_multi_db_config() -> bool:
    """Check if config uses new multi-database format."""
    config_path = Path(__file__).parent.parent / "config.yaml"
    if not config_path.exists():
        return False
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f) or {}
        return "active_database" in config or "databases" in config
    except:
        return False

def _get_db_manager():
    """Get or create DatabaseManager instance."""
    global _db_manager
    if _db_manager is None:
        from src.db_manager import DatabaseManager
        _db_manager = DatabaseManager()
        config_path = str(Path(__file__).parent.parent / "config.yaml")
        _db_manager.load_config(config_path)
    return _db_manager

def load_config() -> dict:
    """Load configuration from config.yaml."""
    config_path = Path(__file__).parent.parent / "config.yaml"
    
    if not config_path.exists():
        logger.warning("config.yaml not found, using defaults")
        return {
            'database': {
                'server': 'localhost',
                'database': 'master',
                'driver': 'ODBC Driver 17 for SQL Server',
                'username': '',
                'password': ''
            }
        }
    
    try:
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)
    except Exception as e:
        logger.error(f"Error loading config: {e}")
        return {'database': {}}

def create_connection_string(config: dict) -> str:
    """
    Create SQLAlchemy connection string from config.
    
    Args:
        config: Database configuration dictionary
        
    Returns:
        Connection string
    """
    db_config = config.get('database', {})
    
    server = db_config.get('server', 'localhost')
    database = db_config.get('database', 'master')
    driver = db_config.get('driver', 'ODBC Driver 17 for SQL Server')
    username = db_config.get('username', '')
    password = db_config.get('password', '')
    
    # Build connection string
    driver_encoded = quote_plus(driver)
    
    if username and password:
        password_encoded = quote_plus(password)
        conn_str = (
            f"mssql+pyodbc://{username}:{password_encoded}@{server}/{database}"
            f"?driver={driver_encoded}&TrustServerCertificate=yes"
        )
    else:
        # Windows Authentication
        conn_str = (
            f"mssql+pyodbc://{server}/{database}"
            f"?driver={driver_encoded}&Trusted_Connection=yes&TrustServerCertificate=yes"
        )
    
    return conn_str

def get_engine() -> Optional[Engine]:
    """
    Get or create SQLAlchemy engine.
    Uses multi-DB manager if available, otherwise falls back to legacy.
    
    Returns:
        SQLAlchemy engine instance or None if creation fails
    """
    global _engine
    
    # Check for multi-database config
    if _use_multi_db_config():
        manager = _get_db_manager()
        if manager.engine is None:
            manager.initialize()
        return manager.engine
    
    # Legacy single-database behavior
    if _engine is None:
        try:
            config = load_config()
            conn_str = create_connection_string(config)
            _engine = create_engine(conn_str, echo=False)
            logger.info("Database engine created successfully")
        except Exception as e:
            logger.error(f"Error creating database engine: {e}", exc_info=True)
            return None
    
    return _engine

def get_sql_database() -> Optional[SQLDatabase]:
    """
    Get or create SQLDatabase instance for LangChain.
    
    Returns:
        SQLDatabase instance or None if creation fails
    """
    global _sql_database
    
    if _sql_database is None:
        engine = get_engine()
        if engine:
            try:
                _sql_database = SQLDatabase(engine)
                logger.info("SQLDatabase instance created successfully")
            except Exception as e:
                logger.error(f"Error creating SQLDatabase: {e}", exc_info=True)
                return None
    
    return _sql_database

def reload_engine() -> Tuple[bool, str]:
    """
    Reload database engine with current config.
    Useful when database settings change.
    
    Returns:
        Tuple of (success: bool, message: str)
    """
    global _engine, _sql_database, _db_manager
    
    logger.info("Reloading database engine...")
    
    # Check for multi-database config
    if _use_multi_db_config():
        _db_manager = None  # Force reload
        manager = _get_db_manager()
        success, message = manager.initialize()
        if success:
            _sql_database = None  # Reset SQLDatabase
        return success, message
    
    # Legacy single-database behavior
    # Close existing engine
    if _engine:
        try:
            _engine.dispose()
        except Exception as e:
            logger.warning(f"Error disposing old engine: {e}")
    
    _engine = None
    _sql_database = None
    
    # Create new engine
    try:
        config = load_config()
        conn_str = create_connection_string(config)
        _engine = create_engine(conn_str, echo=False)
        
        # Test connection
        with _engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        
        # Create new SQLDatabase
        _sql_database = SQLDatabase(_engine)
        
        logger.info("Database engine reloaded successfully")
        return True, "Database connection successful!"
        
    except Exception as e:
        error_msg = f"Failed to connect to database: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return False, error_msg

def run_query(query: str) -> Tuple[bool, Any]:
    """
    Execute a SQL query and return results.
    
    Args:
        query: SQL query to execute
        
    Returns:
        Tuple of (success: bool, result: Any)
    """
    engine = get_engine()
    
    if not engine:
        return False, "Database engine not available"
    
    try:
        # Safety net: validate SQL here as well
        is_valid, safety_msg = validate_sql(query)
        if not is_valid:
            logger.warning(f"Query blocked by safety validator in database.run_query: {safety_msg}")
            return False, f"Query blocked: {safety_msg}"

        with engine.connect() as conn:
            result = conn.execute(text(query))
            
            # For SELECT queries, fetch all results
            if result.returns_rows:
                rows = result.fetchall()
                columns = result.keys()
                return True, {"columns": list(columns), "rows": [list(row) for row in rows]}
            else:
                # For INSERT, UPDATE, DELETE, etc.
                conn.commit()
                return True, {"message": f"Query executed successfully. Rows affected: {result.rowcount}"}
                
    except Exception as e:
        error_msg = f"Query execution failed: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return False, error_msg

def test_connection() -> Tuple[bool, str]:
    """
    Test database connectivity.
    
    Returns:
        Tuple of (success: bool, message: str)
    """
    # Check for multi-database config
    if _use_multi_db_config():
        manager = _get_db_manager()
        if manager.engine is None:
            manager.initialize()
        return manager.test_connection()
    
    # Legacy single-database behavior
    try:
        engine = get_engine()
        if not engine:
            return False, "Engine not available"
        
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        
        return True, "Database connection successful!"
        
    except Exception as e:
        error_msg = f"Connection test failed: {str(e)}"
        logger.error(error_msg)
        return False, error_msg


def get_active_database_type() -> Optional[str]:
    """
    Get the type of the currently active database.
    
    Returns:
        "mssql", "oracle", or None if not using multi-db config
    """
    if _use_multi_db_config():
        manager = _get_db_manager()
        return manager.active_database
    return "mssql"  # Legacy config is always MSSQL


def get_database_info() -> dict:
    """
    Get information about current database connection.
    
    Returns:
        Dictionary with connection details
    """
    if _use_multi_db_config():
        manager = _get_db_manager()
        return manager.get_database_info()
    
    # Legacy format info
    config = load_config()
    db_config = config.get('database', {})
    return {
        "status": "connected" if _engine else "disconnected",
        "type": "mssql",
        "server": db_config.get('server', ''),
        "database": db_config.get('database', '')
    }


def switch_database(db_name: str) -> Tuple[bool, str]:
    """
    Switch to a different database (multi-db config only).
    
    Args:
        db_name: Name of database to switch to ("mssql" or "oracle")
        
    Returns:
        Tuple of (success, message)
    """
    global _sql_database
    
    if not _use_multi_db_config():
        return False, "Multi-database config not enabled"
    
    manager = _get_db_manager()
    success, message = manager.switch_database(db_name)
    
    if success:
        _sql_database = None  # Reset SQLDatabase so it's recreated
    
    return success, message


def load_metadata() -> dict:
    """Load column metadata from metadata.json file."""
    metadata_file = Path(__file__).parent.parent / "metadata.json"
    try:
        if metadata_file.exists():
            with open(metadata_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                logger.info(f"Loaded metadata with {len(data.get('tables', {}))} tables")
                return data
        logger.warning("metadata.json not found, returning empty metadata")
        return {"tables": {}, "version": "1.0"}
    except Exception as e:
        logger.error(f"Error loading metadata: {e}")
        return {"tables": {}, "version": "1.0"}


def save_metadata(metadata: dict) -> bool:
    """Save column metadata to metadata.json file."""
    metadata_file = Path(__file__).parent.parent / "metadata.json"
    try:
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        logger.info("Metadata saved successfully")
        return True
    except Exception as e:
        logger.error(f"Error saving metadata: {e}")
        return False
