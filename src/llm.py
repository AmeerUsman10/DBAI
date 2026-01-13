"""
LLM Utilities
Prompt templates and chain factories for SQL, presentation, and description tasks.
"""
import logging
import json
import re
from typing import Optional, Any, Tuple
from langchain_core.prompts import PromptTemplate

logger = logging.getLogger(__name__)

# SQL Generation Prompt Template
SQL_PROMPT_TEMPLATE = """Given the database schema below, write a SQL Server query to answer the user's question.

Database Schema:
{schema}

Question: {question}

Instructions:
- Write only the SQL query, no explanations
- Use SQL Server syntax
- Use appropriate JOINs if needed
- Ensure the query is safe and doesn't modify data

SQL Query:"""

# Presentation Prompt Template
PRESENTATION_PROMPT_TEMPLATE = """You are a data presentation expert. Given the following query results, present them in a clear, formatted way.

Query: {query}

Results:
{results}

Please format these results in a clear, readable manner with:
- A brief summary of what the data shows
- Key insights or patterns
- Properly formatted tables or lists

Response:"""

# Database Description Prompt Template
DESCRIBE_PROMPT_TEMPLATE = """You are a database expert. Analyze the following data sample and provide insights.

Table/File: {name}

Data Sample:
{sample}

Schema Information:
{schema}

Please provide:
1. A brief description of what this data represents
2. Key columns and their likely purpose
3. Any data quality observations
4. Suggested use cases

Description:"""

def validate_sql(query: str) -> Tuple[bool, str]:
    """
    Validate SQL query for safety.
    
    Args:
        query: SQL query to validate
        
    Returns:
        Tuple of (is_valid: bool, message: str)
    """
    query_upper = query.upper().strip()
    
    # Check for dangerous operations
    dangerous_keywords = ['DROP', 'DELETE', 'TRUNCATE', 'ALTER', 'CREATE', 'INSERT', 'UPDATE']
    
    for keyword in dangerous_keywords:
        if re.search(rf'\b{keyword}\b', query_upper):
            return False, f"Query contains potentially dangerous keyword: {keyword}"
    
    # Check for semicolons (multiple statements)
    if ';' in query and not query.strip().endswith(';'):
        return False, "Multiple statements not allowed"
    
    return True, "Query appears safe"

def safe_json_loads(json_str: str) -> Optional[Any]:
    """
    Safely parse JSON string.
    
    Args:
        json_str: JSON string to parse
        
    Returns:
        Parsed JSON object or None if parsing fails
    """
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        logger.error(f"JSON parsing error: {e}")
        return None

def make_sql_chain(llm, db):
    """
    Create a SQL query generation chain with generic schema mapping and example-based learning.
    
    Args:
        llm: Language model instance
        db: SQLDatabase instance
        
    Returns:
        SQL query chain function
    """
    try:
        from src.schema_discovery import get_table_info_string
        from src.schema_mapper import format_mappings_for_prompt, get_all_mappings
        from src.example_queries import get_relevant_examples, format_examples_for_prompt
        from src.database import get_engine
        
        # Get schema information
        schema = db.get_table_info()
        
        # Get database type for determining SQL dialect
        engine = get_engine()
        db_type = "mssql"  # Default, will be detected from engine if possible
        
        # Build generic prompt template
        def build_generic_prompt(question: str, persona_overlay: str = "") -> Tuple[str, list]:
            # Get schema mappings
            mappings = get_all_mappings()
            mappings_text = format_mappings_for_prompt()
            
            # Get relevant examples
            examples = get_relevant_examples(question, limit=3)
            examples_text = format_examples_for_prompt(examples)
            
            # Track which examples were used (for usage tracking)
            example_ids = [ex.get("id") for ex in examples]
            
            # Build persona section
            persona_section = f"\n\nPERSONA OVERLAY:\n{persona_overlay}\n" if persona_overlay else ""
            
            # Determine SQL dialect from engine or config
            sql_dialect = "SQL Server (MSSQL)"  # Default
            try:
                if engine:
                    dialect = engine.dialect.name
                    if dialect == "oracle":
                        sql_dialect = "Oracle"
                    elif dialect == "mysql":
                        sql_dialect = "MySQL"
            except:
                pass

            generic_template = f"""Given the database schema below, write a {sql_dialect} query to answer the user's question.

Database Schema:
{schema}
{persona_section}
{mappings_text}
{examples_text}

User Question: {question}

Instructions:
1. Use actual table/column names from schema (not aliases in the query itself)
2. Apply mappings to understand what the user means when they use natural language terms
3. Follow patterns from example queries above
4. Generate {sql_dialect} syntax as appropriate
5. Return ONLY SQL query, no explanations, no comments
6. Ensure the query is safe and doesn't modify data (SELECT only)
7. Use appropriate JOINs if multiple tables are needed
8. Use clear, descriptive column aliases in the SELECT clause

SQL Query:"""
            
            return generic_template, example_ids
        
        # Simple chain that formats prompt and calls LLM
        def sql_chain(inputs: dict) -> dict:
            question = inputs.get("question", "")
            persona_overlay = inputs.get("persona_overlay", "")
            formatted_prompt, example_ids = build_generic_prompt(question, persona_overlay)
            
            # Log prompt metadata (hash only)
            try:
                from src.session_tracker import get_session_tracker
                from src.telemetry import TelemetryLogger
                tracker = get_session_tracker()
                TelemetryLogger.log_prompt_metadata(
                    session_id=tracker.session_id,
                    message_id=inputs.get("message_id", ""),
                    question=question,
                    prompt_text=formatted_prompt,
                    generation_method="llm"
                )
            except Exception:
                pass
            
            response = llm.invoke(formatted_prompt)
            
            # Extract content from response
            if hasattr(response, 'content'):
                result = response.content
            elif isinstance(response, str):
                result = response
            else:
                result = str(response)
            
            # Return both result and raw response for token tracking
            # Note: example_ids can be used to track which examples were applied
            return {"result": result, "response": response, "examples_applied": example_ids}
        
        return sql_chain
        
    except Exception as e:
        logger.error(f"Error creating SQL chain: {e}", exc_info=True)
        raise

def make_presentation_chain(llm):
    """
    Create a results presentation chain.
    
    Args:
        llm: Language model instance
        
    Returns:
        Presentation chain
    """
    try:
        prompt = PromptTemplate(
            input_variables=["query", "results"],
            template=PRESENTATION_PROMPT_TEMPLATE
        )
        
        # Simple chain that formats with LLM
        def presentation_chain(query: str, results: Any) -> str:
            formatted_prompt = prompt.format(query=query, results=str(results))
            response = llm.invoke(formatted_prompt)
            
            # Extract content from response
            if hasattr(response, 'content'):
                return response.content
            elif isinstance(response, str):
                return response
            else:
                return str(response)
        
        return presentation_chain
        
    except Exception as e:
        logger.error(f"Error creating presentation chain: {e}", exc_info=True)
        raise

def make_describe_chain(llm):
    """
    Create a data description chain.
    
    Args:
        llm: Language model instance
        
    Returns:
        Description chain
    """
    try:
        prompt = PromptTemplate(
            input_variables=["name", "sample", "schema"],
            template=DESCRIBE_PROMPT_TEMPLATE
        )
        
        # Simple chain that describes data with LLM
        def describe_chain(name: str, sample: str, schema: str = "") -> str:
            formatted_prompt = prompt.format(name=name, sample=sample, schema=schema)
            response = llm.invoke(formatted_prompt)
            
            # Extract content from response
            if hasattr(response, 'content'):
                return response.content
            elif isinstance(response, str):
                return response
            else:
                return str(response)
        
        return describe_chain
        
    except Exception as e:
        logger.error(f"Error creating describe chain: {e}", exc_info=True)
        raise

def extract_sql_from_response(response: str) -> str:
    """
    Extract SQL query from LLM response.
    
    Args:
        response: LLM response text
        
    Returns:
        Extracted SQL query (first query only if multiple found)
    """
    # Try to find SQL in code blocks
    code_block_match = re.search(r'```sql\s*(.*?)\s*```', response, re.DOTALL | re.IGNORECASE)
    if code_block_match:
        sql = code_block_match.group(1).strip()
    else:
        code_block_match = re.search(r'```\s*(.*?)\s*```', response, re.DOTALL)
        if code_block_match:
            sql = code_block_match.group(1).strip()
        else:
            sql = response.strip()
    
    # If multiple queries found (separated by GO or semicolons), take only the first SELECT
    lines = sql.split('\n')
    query_lines = []
    in_query = False
    
    for line in lines:
        line_stripped = line.strip()
        
        # Skip empty lines and comments
        if not line_stripped or line_stripped.startswith('--'):
            continue
        
        # Start capturing when we see SELECT
        if line_stripped.upper().startswith('SELECT'):
            in_query = True
            query_lines.append(line)
        elif in_query:
            # Stop if we hit another SELECT, GO, or explanatory text
            if (line_stripped.upper().startswith('SELECT') or 
                line_stripped.upper() == 'GO' or
                any(word in line_stripped.lower() for word in ['this query', 'explanation:', 'note:', 'result:'])):
                break
            query_lines.append(line)
    
    if query_lines:
        extracted_sql = '\n'.join(query_lines).strip()
    else:
        extracted_sql = sql
    
    # POST-PROCESS: Fix bad column aliases to match our requirements
    # This ensures proper column names even if LLM ignores instructions
    extracted_sql = fix_column_aliases(extracted_sql)
    
    return extracted_sql


def fix_column_aliases(sql: str) -> str:
    """
    Fix column aliases to use human-readable format.
    Generic version - no domain-specific assumptions.
    
    Args:
        sql: SQL query string
        
    Returns:
        SQL with corrected column aliases (currently passes through unchanged)
    """
    # Generic version - no hardcoded domain-specific fixes
    # Users can define their own alias preferences through examples
    return sql

