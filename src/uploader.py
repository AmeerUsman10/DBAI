"""
Excel File Uploader and Database Importer
Handles Excel file preview, schema inference, and database import.
"""
import logging
import re
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any
import pandas as pd
from sqlalchemy import inspect, text

logger = logging.getLogger(__name__)

def sanitize_table_name(name: str) -> str:
    """
    Sanitize table name for SQL Server.
    
    Args:
        name: Original table name
        
    Returns:
        Sanitized table name
    """
    # Remove extension
    name = Path(name).stem
    
    # Replace spaces and special chars with underscore
    name = re.sub(r'[^\w]', '_', name)
    
    # Ensure it doesn't start with a number
    if name and name[0].isdigit():
        name = f"tbl_{name}"
    
    # Add prefix
    name = f"import_{name}"
    
    return name[:128]  # Limit length

def read_excel_file(file_path: str) -> Tuple[bool, Any]:
    """
    Read Excel file and return DataFrame.
    
    Args:
        file_path: Path to Excel file
        
    Returns:
        Tuple of (success: bool, result: DataFrame or error message)
    """
    try:
        ext = Path(file_path).suffix.lower()
        
        # Try to read based on extension
        if ext == '.xlsx':
            df = pd.read_excel(file_path, engine='openpyxl')
        elif ext == '.xls':
            df = pd.read_excel(file_path, engine='xlrd')
        else:
            # Try both engines
            try:
                df = pd.read_excel(file_path, engine='openpyxl')
            except:
                df = pd.read_excel(file_path, engine='xlrd')
        
        logger.info(f"Successfully read Excel file: {file_path}")
        return True, df
        
    except Exception as e:
        error_msg = f"Error reading Excel file: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return False, error_msg

def preview_dataframe(df: pd.DataFrame, max_rows: int = 10) -> str:
    """
    Create a preview string of DataFrame.
    
    Args:
        df: DataFrame to preview
        max_rows: Maximum rows to show
        
    Returns:
        Preview string
    """
    preview = f"Shape: {df.shape[0]} rows × {df.shape[1]} columns\n\n"
    preview += "Column Types:\n"
    
    for col, dtype in df.dtypes.items():
        preview += f"  {col}: {dtype}\n"
    
    preview += f"\nFirst {min(max_rows, len(df))} rows:\n"
    preview += df.head(max_rows).to_string()
    
    return preview

def infer_sql_type(dtype) -> str:
    """
    Infer SQL Server type from pandas dtype.
    
    Args:
        dtype: Pandas dtype
        
    Returns:
        SQL Server type string
    """
    dtype_str = str(dtype)
    
    if 'int' in dtype_str:
        return 'INT'
    elif 'float' in dtype_str:
        return 'FLOAT'
    elif 'datetime' in dtype_str:
        return 'DATETIME'
    elif 'bool' in dtype_str:
        return 'BIT'
    else:
        return 'NVARCHAR(MAX)'

def generate_create_table_sql(table_name: str, df: pd.DataFrame) -> str:
    """
    Generate CREATE TABLE SQL from DataFrame.
    
    Args:
        table_name: Name for the table
        df: DataFrame with data
        
    Returns:
        CREATE TABLE SQL statement
    """
    sql = f"CREATE TABLE [{table_name}] (\n"
    
    columns = []
    for col, dtype in df.dtypes.items():
        sql_type = infer_sql_type(dtype)
        # Sanitize column name
        col_name = re.sub(r'[^\w]', '_', str(col))
        columns.append(f"    [{col_name}] {sql_type}")
    
    sql += ",\n".join(columns)
    sql += "\n);"
    
    return sql

def check_table_exists(engine, table_name: str) -> bool:
    """
    Check if table exists in database.
    
    Args:
        engine: SQLAlchemy engine
        table_name: Table name to check
        
    Returns:
        True if table exists
    """
    try:
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        return table_name.lower() in [t.lower() for t in tables]
    except Exception as e:
        logger.error(f"Error checking table existence: {e}")
        return False

def import_dataframe_to_db(
    engine,
    df: pd.DataFrame,
    table_name: str,
    if_exists: str = 'fail'
) -> Tuple[bool, str]:
    """
    Import DataFrame to database.
    
    Args:
        engine: SQLAlchemy engine
        df: DataFrame to import
        table_name: Target table name
        if_exists: How to handle existing table ('fail', 'replace', 'append')
        
    Returns:
        Tuple of (success: bool, message: str)
    """
    try:
        # Sanitize column names
        df_clean = df.copy()
        df_clean.columns = [re.sub(r'[^\w]', '_', str(col)) for col in df.columns]
        
        # Import to database
        df_clean.to_sql(
            table_name,
            engine,
            if_exists=if_exists,
            index=False,
            method='multi',
            chunksize=1000
        )
        
        logger.info(f"Successfully imported {len(df)} rows to table '{table_name}'")
        return True, f"Successfully imported {len(df)} rows to table '{table_name}'"
        
    except Exception as e:
        error_msg = f"Import failed: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return False, error_msg

def process_excel_files(file_paths: List[str]) -> Dict[str, Any]:
    """
    Process multiple Excel files and prepare import data.
    
    Args:
        file_paths: List of file paths to process
        
    Returns:
        Dictionary with file analysis results
    """
    results = {}
    
    for file_path in file_paths:
        file_name = Path(file_path).name
        
        success, df_or_error = read_excel_file(file_path)
        
        if success:
            df = df_or_error
            table_name = sanitize_table_name(file_name)
            
            results[file_name] = {
                'success': True,
                'table_name': table_name,
                'dataframe': df,
                'preview': preview_dataframe(df, max_rows=5),
                'create_sql': generate_create_table_sql(table_name, df),
                'row_count': len(df),
                'column_count': len(df.columns)
            }
        else:
            results[file_name] = {
                'success': False,
                'error': df_or_error
            }
    
    return results
