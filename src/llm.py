"""
LLM Utilities
Prompt templates and chain factories for SQL, presentation, and description tasks.
"""
import logging
import json
import re
from typing import Optional, Any
from langchain.chains import create_sql_query_chain
from langchain.prompts import PromptTemplate

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

def validate_sql(query: str) -> tuple[bool, str]:
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
    Create a SQL query generation chain.
    
    Args:
        llm: Language model instance
        db: SQLDatabase instance
        
    Returns:
        SQL query chain
    """
    try:
        # Use LangChain's built-in SQL chain
        chain = create_sql_query_chain(llm, db)
        return chain
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
        Extracted SQL query
    """
    # Try to find SQL in code blocks
    code_block_match = re.search(r'```sql\s*(.*?)\s*```', response, re.DOTALL | re.IGNORECASE)
    if code_block_match:
        return code_block_match.group(1).strip()
    
    code_block_match = re.search(r'```\s*(.*?)\s*```', response, re.DOTALL)
    if code_block_match:
        return code_block_match.group(1).strip()
    
    # Return the whole response if no code block found
    return response.strip()
