"""
Multi-Database Manager for DBAI
Supports MSSQL and Oracle with unified interface
Build 30 - Phase 1
"""

import os
import yaml
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote_plus

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

# Setup logging
logger = logging.getLogger(__name__)


# =============================================================================
# ABSTRACT BASE CLASS
# =============================================================================

class DatabaseAdapter(ABC):
    """Abstract base class for database adapters"""
    
    @abstractmethod
    def create_engine(self, config: Dict[str, Any]) -> Engine:
        """Create SQLAlchemy engine for this database type"""
        pass
    
    @abstractmethod
    def test_connection(self, engine: Engine) -> Tuple[bool, str]:
        """Test database connection, return (success, message)"""
        pass
    
    @abstractmethod
    def get_tables(self, engine: Engine) -> List[str]:
        """Get list of table names"""
        pass
    
    @abstractmethod
    def get_sample_query(self) -> str:
        """Get a sample query for this database type"""
        pass
    
    @property
    @abstractmethod
    def dialect_name(self) -> str:
        """Return the SQLAlchemy dialect name"""
        pass


# =============================================================================
# MSSQL ADAPTER
# =============================================================================

class MSSQLAdapter(DatabaseAdapter):
    """Microsoft SQL Server adapter"""
    
    @property
    def dialect_name(self) -> str:
        return "mssql"
    
    def create_engine(self, config: Dict[str, Any]) -> Engine:
        """Create MSSQL engine using pyodbc"""
        server = config.get("server", "localhost")
        database = config.get("database", "")
        driver = config.get("driver", "ODBC Driver 18 for SQL Server")
        username = config.get("username", "")
        password = config.get("password", "")
        timeout = config.get("timeout_seconds", 30)
        
        # Build connection string
        conn_str = (
            f"DRIVER={{{driver}}};"
            f"SERVER={server};"
            f"DATABASE={database};"
            f"UID={username};"
            f"PWD={password};"
            f"TrustServerCertificate=yes;"
            f"Connection Timeout={timeout};"
        )
        
        quoted = quote_plus(conn_str)
        engine_url = f"mssql+pyodbc:///?odbc_connect={quoted}"
        
        return create_engine(engine_url, echo=False)
    
    def test_connection(self, engine: Engine) -> Tuple[bool, str]:
        """Test MSSQL connection"""
        try:
            with engine.connect() as conn:
                result = conn.execute(text("SELECT @@VERSION"))
                version = result.scalar()
                return True, f"Connected to MSSQL: {version[:50]}..."
        except Exception as e:
            return False, f"MSSQL connection failed: {str(e)}"
    
    def get_tables(self, engine: Engine) -> List[str]:
        """Get MSSQL tables"""
        query = """
            SELECT TABLE_NAME 
            FROM INFORMATION_SCHEMA.TABLES 
            WHERE TABLE_TYPE = 'BASE TABLE'
            ORDER BY TABLE_NAME
        """
        try:
            with engine.connect() as conn:
                result = conn.execute(text(query))
                return [row[0] for row in result.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get MSSQL tables: {e}")
            return []
    
    def get_sample_query(self) -> str:
        return "SELECT TOP 10 * FROM your_table"


# =============================================================================
# ORACLE ADAPTER
# =============================================================================

class OracleAdapter(DatabaseAdapter):
    """Oracle Database adapter with connection pooling"""
    
    def __init__(self):
        self._pool = None
    
    @property
    def dialect_name(self) -> str:
        return "oracle"
    
    def create_engine(self, config: Dict[str, Any]) -> Engine:
        """Create Oracle engine with connection pooling"""
        host = config.get("host", "localhost")
        port = config.get("port", 1521)
        service_name = config.get("service_name", "")
        username = config.get("username", "")
        password = config.get("password", "")
        
        pool_min = config.get("pool_min", 2)
        pool_max = config.get("pool_max", 10)
        pool_increment = config.get("pool_increment", 1)
        
        # Oracle connection string format
        dsn = f"{host}:{port}/{service_name}"
        engine_url = f"oracle+oracledb://{username}:{quote_plus(password)}@{dsn}"
        
        return create_engine(
            engine_url,
            echo=False,
            pool_size=pool_min,
            max_overflow=pool_max - pool_min,
            pool_pre_ping=True  # Verify connections before use
        )
    
    def test_connection(self, engine: Engine) -> Tuple[bool, str]:
        """Test Oracle connection"""
        try:
            with engine.connect() as conn:
                result = conn.execute(text("SELECT BANNER FROM V$VERSION WHERE ROWNUM = 1"))
                version = result.scalar()
                return True, f"Connected to Oracle: {version}"
        except Exception as e:
            return False, f"Oracle connection failed: {str(e)}"
    
    def get_tables(self, engine: Engine) -> List[str]:
        """Get Oracle tables"""
        query = """
            SELECT TABLE_NAME 
            FROM USER_TABLES 
            ORDER BY TABLE_NAME
        """
        try:
            with engine.connect() as conn:
                result = conn.execute(text(query))
                return [row[0] for row in result.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get Oracle tables: {e}")
            return []
    
    def get_sample_query(self) -> str:
        return "SELECT * FROM your_table WHERE ROWNUM <= 10"


# =============================================================================
# DATABASE MANAGER
# =============================================================================

class DatabaseManager:
    """
    Unified database manager for multi-database support.
    Manages active database connection and provides routing.
    """
    
    _instance = None
    
    # Registry of available adapters
    ADAPTERS = {
        "mssql": MSSQLAdapter,
        "oracle": OracleAdapter
    }
    
    def __new__(cls):
        """Singleton pattern for database manager"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._config: Dict[str, Any] = {}
        self._active_db: Optional[str] = None
        self._engine: Optional[Engine] = None
        self._adapter: Optional[DatabaseAdapter] = None
        self._initialized = True
        
        logger.info("DatabaseManager initialized")
    
    def load_config(self, config_path: str = "config.yaml") -> Dict[str, Any]:
        """Load configuration from YAML file"""
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Config file not found: {config_path}")
        
        with open(config_path, "r") as f:
            self._config = yaml.safe_load(f) or {}
        
        logger.info(f"Configuration loaded from {config_path}")
        return self._config
    
    @property
    def config(self) -> Dict[str, Any]:
        """Get current configuration"""
        return self._config
    
    @property
    def active_database(self) -> Optional[str]:
        """Get name of active database"""
        return self._active_db
    
    @property
    def engine(self) -> Optional[Engine]:
        """Get current SQLAlchemy engine"""
        return self._engine
    
    @property
    def adapter(self) -> Optional[DatabaseAdapter]:
        """Get current database adapter"""
        return self._adapter
    
    def get_enabled_databases(self) -> List[str]:
        """Get list of enabled database names"""
        databases = self._config.get("databases", {})
        return [
            name for name, cfg in databases.items()
            if cfg.get("enabled", False)
        ]
    
    def switch_database(self, db_name: str) -> Tuple[bool, str]:
        """
        Switch to a different database.
        
        Args:
            db_name: Name of database to switch to ("mssql" or "oracle")
            
        Returns:
            Tuple of (success, message)
        """
        if db_name not in self.ADAPTERS:
            return False, f"Unknown database type: {db_name}"
        
        databases = self._config.get("databases", {})
        db_config = databases.get(db_name, {})
        
        if not db_config.get("enabled", False):
            return False, f"Database '{db_name}' is not enabled in config"
        
        # Dispose old engine if exists
        if self._engine is not None:
            try:
                self._engine.dispose()
                logger.info(f"Disposed previous {self._active_db} engine")
            except Exception as e:
                logger.warning(f"Error disposing engine: {e}")
        
        # Create new adapter and engine
        try:
            adapter_class = self.ADAPTERS[db_name]
            self._adapter = adapter_class()
            self._engine = self._adapter.create_engine(db_config)
            self._active_db = db_name
            
            # Test connection immediately
            success, message = self._adapter.test_connection(self._engine)
            if not success:
                self._engine = None
                self._adapter = None
                self._active_db = None
                return False, message
            
            logger.info(f"Switched to {db_name} database")
            return True, message
            
        except Exception as e:
            self._engine = None
            self._adapter = None
            self._active_db = None
            error_msg = f"Failed to connect to {db_name}: {str(e)}"
            logger.error(error_msg)
            return False, error_msg
    
    def initialize(self) -> Tuple[bool, str]:
        """
        Initialize connection to the active database from config.
        
        Returns:
            Tuple of (success, message)
        """
        if not self._config:
            return False, "Configuration not loaded"
        
        # Support both new and legacy config formats
        active_db = self._config.get("active_database")
        
        if active_db:
            # New multi-database format
            return self.switch_database(active_db)
        elif "database" in self._config:
            # Legacy single-database format - treat as MSSQL
            logger.info("Using legacy config format (MSSQL)")
            self._config["databases"] = {
                "mssql": {
                    **self._config["database"],
                    "enabled": True
                }
            }
            self._config["active_database"] = "mssql"
            return self.switch_database("mssql")
        else:
            return False, "No database configured"
    
    def run_query(self, query: str) -> Dict[str, Any]:
        """
        Execute a SQL query and return results.
        
        Args:
            query: SQL query string
            
        Returns:
            Dict with 'columns' and 'rows' keys, or 'message' for non-SELECT
        """
        if self._engine is None:
            return {"message": "No active database connection"}
        
        try:
            with self._engine.connect() as conn:
                result = conn.execute(text(query))
                
                if result.returns_rows:
                    columns = list(result.keys())
                    rows = [list(row) for row in result.fetchall()]
                    return {"columns": columns, "rows": rows}
                else:
                    conn.commit()
                    return {"message": f"Query executed successfully. Rows affected: {result.rowcount}"}
                    
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Query execution error: {error_msg}")
            return {"message": f"Query error: {error_msg}"}
    
    def get_tables(self) -> List[str]:
        """Get list of tables from active database"""
        if self._adapter is None or self._engine is None:
            return []
        return self._adapter.get_tables(self._engine)
    
    def test_connection(self) -> Tuple[bool, str]:
        """Test current database connection"""
        if self._adapter is None or self._engine is None:
            return False, "No active database connection"
        return self._adapter.test_connection(self._engine)
    
    def get_database_info(self) -> Dict[str, Any]:
        """Get information about current database connection"""
        if self._active_db is None:
            return {"status": "disconnected"}
        
        databases = self._config.get("databases", {})
        db_config = databases.get(self._active_db, {})
        
        info = {
            "status": "connected",
            "type": self._active_db,
            "dialect": self._adapter.dialect_name if self._adapter else None
        }
        
        # Add connection details (hide password)
        if self._active_db == "mssql":
            info["server"] = db_config.get("server", "")
            info["database"] = db_config.get("database", "")
        elif self._active_db == "oracle":
            info["host"] = db_config.get("host", "")
            info["port"] = db_config.get("port", 1521)
            info["service_name"] = db_config.get("service_name", "")
        
        return info
    
    def reload(self, config_path: str = "config.yaml") -> Tuple[bool, str]:
        """Reload configuration and reconnect"""
        self.load_config(config_path)
        return self.initialize()


# =============================================================================
# CONVENIENCE FUNCTIONS (for backward compatibility)
# =============================================================================

def get_db_manager() -> DatabaseManager:
    """Get the singleton DatabaseManager instance"""
    return DatabaseManager()


def initialize_database(config_path: str = "config.yaml") -> Tuple[bool, str]:
    """Initialize database from config file"""
    manager = get_db_manager()
    manager.load_config(config_path)
    return manager.initialize()


def run_query(query: str) -> Dict[str, Any]:
    """Run a query using the active database"""
    return get_db_manager().run_query(query)


def get_current_database_type() -> Optional[str]:
    """Get the type of the currently active database"""
    return get_db_manager().active_database
