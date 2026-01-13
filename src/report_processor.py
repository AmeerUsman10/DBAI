"""
Report Processor Module
Processes uploaded Excel files + SQL queries with AI-driven clarification workflow.
"""
import logging
import re
import pandas as pd
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from sqlalchemy import create_engine

logger = logging.getLogger(__name__)


def extract_excel_structure(excel_path: str) -> Dict:
    """
    Extract structure and sample data from Excel file.
    
    Args:
        excel_path: Path to Excel file
        
    Returns:
        Dictionary with columns, sample data, and data types
    """
    try:
        df = pd.read_excel(excel_path, nrows=10)  # Read first 10 rows for analysis
        
        return {
            "columns": list(df.columns),
            "sample_data": df.head(5).to_dict('records'),
            "data_types": {col: str(dtype) for col, dtype in df.dtypes.items()},
            "row_count_preview": len(df),
            "success": True
        }
    except Exception as e:
        logger.error(f"Error reading Excel file: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e)
        }


def parse_sql_query(sql_query: str) -> Dict:
    """
    Parse SQL query to extract tables, columns, and logic.
    
    Args:
        sql_query: SQL query string
        
    Returns:
        Dictionary with parsed information
    """
    try:
        sql_upper = sql_query.upper()
        
        # Extract table names (FROM and JOIN clauses)
        tables = []
        from_match = re.search(r'\bFROM\s+(\w+)', sql_upper)
        if from_match:
            tables.append(from_match.group(1))
        
        join_matches = re.findall(r'\bJOIN\s+(\w+)', sql_upper)
        tables.extend(join_matches)
        
        # Extract column names (SELECT clause)
        select_match = re.search(r'\bSELECT\s+(.*?)\s+FROM', sql_upper, re.DOTALL)
        columns = []
        if select_match:
            select_clause = select_match.group(1)
            # Simple extraction - split by comma and clean
            col_parts = [col.strip().split()[0] for col in select_clause.split(',')]
            columns = [col for col in col_parts if col and not col.upper() in ['DISTINCT', 'TOP']]
        
        # Extract WHERE conditions
        where_match = re.search(r'\bWHERE\s+(.*?)(?:\s+GROUP\s+BY|\s+ORDER\s+BY|\s+HAVING|$)', sql_upper, re.DOTALL)
        where_clause = where_match.group(1) if where_match else None
        
        # Extract aggregations
        has_aggregations = bool(re.search(r'\b(SUM|COUNT|AVG|MAX|MIN)\s*\(', sql_upper))
        
        # Extract calculations
        calculations = []
        calc_pattern = r'(\w+)\s*([+\-*/])\s*(\w+)'
        calc_matches = re.findall(calc_pattern, sql_query)
        calculations = [f"{a} {op} {b}" for a, op, b in calc_matches]
        
        return {
            "tables": list(set(tables)),  # Remove duplicates
            "columns": columns,
            "where_clause": where_clause,
            "has_aggregations": has_aggregations,
            "calculations": calculations,
            "success": True
        }
    except Exception as e:
        logger.error(f"Error parsing SQL: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e)
        }


def analyze_with_ai(
    excel_structure: Dict,
    sql_info: Dict,
    description: str,
    llm
) -> Dict:
    """
    Use LLM to analyze the report and identify ambiguities.
    
    Args:
        excel_structure: Excel file structure
        sql_info: Parsed SQL information
        description: User's description of the report
        llm: Language model instance
        
    Returns:
        Dictionary with analysis results and questions
    """
    try:
        excel_cols = ", ".join(excel_structure.get("columns", []))
        tables_used = ", ".join(sql_info.get("tables", []))
        columns_used = ", ".join(sql_info.get("columns", []))
        
        prompt = f"""I have an Excel report and a SQL query. Analyze them and identify what needs clarification.

Excel Report Columns: {excel_cols}
User Description: {description}

SQL Query Analysis:
- Tables used: {tables_used}
- Columns referenced: {columns_used}
- Has aggregations: {sql_info.get('has_aggregations', False)}
- Calculations: {', '.join(sql_info.get('calculations', []))}
- WHERE clause: {sql_info.get('where_clause', 'None')}

Please analyze and provide:
1. What tables/columns does this query use?
2. What business logic is implied?
3. What's ambiguous or unclear?
4. What mappings should be created?

Format your response as JSON with this structure:
{{
  "identified_tables": ["table1", "table2"],
  "identified_columns": ["col1", "col2"],
  "business_logic": "description of what this report calculates",
  "ambiguities": [
    {{
      "type": "table_mapping",
      "question": "What should users call table 'ord_tbl'?",
      "context": "Used in FROM clause"
    }},
    {{
      "type": "column_mapping",
      "question": "What does column 'tot_amt' represent?",
      "context": "Used in SELECT clause"
    }},
    {{
      "type": "business_rule",
      "question": "What does status = 1 mean?",
      "context": "Used in WHERE clause"
    }}
  ],
  "suggested_mappings": {{
    "table_aliases": {{"orders": "ord_tbl"}},
    "column_aliases": {{"total amount": {{"table": "ord_tbl", "column": "tot_amt"}}}}
  }}
}}"""
        
        response = llm.invoke(prompt)
        
        # Extract content
        if hasattr(response, 'content'):
            result_text = response.content
        else:
            result_text = str(response)
        
        # Try to extract JSON from response
        json_match = re.search(r'\{.*\}', result_text, re.DOTALL)
        if json_match:
            import json
            try:
                analysis = json.loads(json_match.group(0))
                return {
                    "success": True,
                    "analysis": analysis
                }
            except json.JSONDecodeError:
                pass
        
        # Fallback: return text analysis
        return {
            "success": True,
            "analysis": {
                "raw_analysis": result_text,
                "ambiguities": []
            }
        }
        
    except Exception as e:
        logger.error(f"Error in AI analysis: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e)
        }


def process_upload(
    excel_path: str,
    sql_query: str,
    description: str,
    db_type: str,
    llm
) -> Dict:
    """
    Process uploaded Excel + SQL with AI analysis.
    
    Args:
        excel_path: Path to Excel file
        sql_query: SQL query string
        description: User's description
        db_type: "mssql", "oracle", or "mysql"
        llm: Language model instance
        
    Returns:
        Dictionary with processing results and clarification questions
    """
    try:
        # Step 1: Extract Excel structure
        excel_structure = extract_excel_structure(excel_path)
        if not excel_structure.get("success"):
            return {
                "success": False,
                "error": f"Excel parsing failed: {excel_structure.get('error')}"
            }
        
        # Step 2: Parse SQL
        sql_info = parse_sql_query(sql_query)
        if not sql_info.get("success"):
            return {
                "success": False,
                "error": f"SQL parsing failed: {sql_info.get('error')}"
            }
        
        # Step 3: AI Analysis
        ai_analysis = analyze_with_ai(excel_structure, sql_info, description, llm)
        
        return {
            "success": True,
            "excel_structure": excel_structure,
            "sql_info": sql_info,
            "ai_analysis": ai_analysis,
            "clarification_questions": ai_analysis.get("analysis", {}).get("ambiguities", [])
        }
        
    except Exception as e:
        logger.error(f"Error processing upload: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e)
        }


def validate_sql_against_schema(sql_query: str, engine) -> Tuple[bool, List[str]]:
    """
    Validate that tables/columns in SQL exist in actual database schema.
    
    Args:
        sql_query: SQL query to validate
        engine: SQLAlchemy engine
        
    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    try:
        from src.schema_discovery import get_schema_summary
        
        schema = get_schema_summary(engine)
        schema_tables = {t["name"].lower() for t in schema.get("tables", [])}
        
        sql_info = parse_sql_query(sql_query)
        sql_tables = {t.lower() for t in sql_info.get("tables", [])}
        
        errors = []
        for table in sql_tables:
            if table not in schema_tables:
                errors.append(f"Table '{table}' not found in database schema")
        
        return len(errors) == 0, errors
        
    except Exception as e:
        logger.error(f"Error validating SQL: {e}", exc_info=True)
        return False, [f"Validation error: {str(e)}"]


def create_mappings_from_answers(
    questions: List[Dict],
    answers: Dict[str, str]
) -> Dict:
    """
    Create schema mappings from user answers to clarification questions.
    
    Args:
        questions: List of clarification questions
        answers: Dictionary mapping question index to answer
        
    Returns:
        Dictionary with mappings to create
    """
    mappings = {
        "table_aliases": {},
        "column_aliases": {}
    }
    
    for i, question in enumerate(questions):
        answer = answers.get(str(i), "").strip()
        if not answer:
            continue
        
        q_type = question.get("type", "")
        context = question.get("context", "")
        
        if q_type == "table_mapping":
            # Extract table name from context or question
            table_match = re.search(r"table\s+['\"]?(\w+)['\"]?", question.get("question", ""), re.IGNORECASE)
            if table_match:
                actual_table = table_match.group(1)
                mappings["table_aliases"][answer.lower()] = actual_table
        
        elif q_type == "column_mapping":
            # Extract column name from context
            col_match = re.search(r"column\s+['\"]?(\w+)['\"]?", question.get("question", ""), re.IGNORECASE)
            table_match = re.search(r"table\s+['\"]?(\w+)['\"]?", context, re.IGNORECASE)
            if col_match and table_match:
                actual_column = col_match.group(1)
                actual_table = table_match.group(1)
                mappings["column_aliases"][answer.lower()] = {
                    "table": actual_table,
                    "column": actual_column
                }
    
    return mappings
