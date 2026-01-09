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
    Create a SQL query generation chain with enhanced context.
    
    Args:
        llm: Language model instance
        db: SQLDatabase instance
        
    Returns:
        SQL query chain function
    """
    try:
        from src.database import load_metadata
        from src.learnings import get_relevant_learnings, format_learnings_for_prompt
        from src.quick_training import get_training_rules_for_prompt, get_approved_rules, get_relevant_approved_rules
        
        # Get schema information
        schema = db.get_table_info()
        
        # Load metadata for enhanced context
        metadata = load_metadata()
        
        # Build enhanced prompt template
        def build_enhanced_prompt(question: str, persona_overlay: str = "") -> Tuple[str, list]:
            # Get relevant learnings for this question
            learnings = get_relevant_learnings(question, limit=3)
            learnings_text = format_learnings_for_prompt(learnings)
            
            # Get quick training rules
            # Build training rules section and track applied rule indices
            # Use a small, relevant subset of rules for this question
            relevant_rules = get_relevant_approved_rules(question, max_rules=3)
            training_rules = ""
            applied_indices = []
            if relevant_rules:
                training_rules = "\n### User-Defined Training Rules (Approved):\nThe user has provided the following specific instructions on how to interpret queries:\n\n"
                for global_idx, rule in relevant_rules:
                    training_rules += f"{global_idx}. {rule['instruction']}\n"
                    applied_indices.append(global_idx)
                training_rules += "\nIMPORTANT: Follow these rules precisely when generating SQL queries.\n"
            
            # Build metadata context
            metadata_context = ""
            if metadata.get("tables"):
                metadata_context = "\n\nCOLUMN METADATA & BUSINESS CONTEXT:\n"
                for table_name, table_data in metadata["tables"].items():
                    metadata_context += f"\n{table_name}:\n"
                    
                    # Add column descriptions
                    if table_data.get("columns"):
                        metadata_context += "  Columns:\n"
                        for col, desc in table_data["columns"].items():
                            metadata_context += f"    - {col}: {desc}\n"
                    
                    # Add business terms
                    if table_data.get("business_terms"):
                        metadata_context += "  Business Terms:\n"
                        for term, meaning in table_data["business_terms"].items():
                            metadata_context += f"    - {term}: {meaning}\n"
                    
                    # Add common query patterns
                    if table_data.get("common_queries"):
                        metadata_context += "  Common Patterns:\n"
                        for pattern in table_data["common_queries"]:
                            # Handle both old format (vague/interpretation) and new format (pattern/intent)
                            if isinstance(pattern, dict):
                                if 'vague' in pattern and 'interpretation' in pattern:
                                    metadata_context += f"    - \"{pattern['vague']}\" usually means: {pattern['interpretation']}\n"
                                elif 'pattern' in pattern and 'intent' in pattern:
                                    metadata_context += f"    - \"{pattern['pattern']}\" usually means: {pattern['intent']}\n"
            
            # Build full prompt
            persona_section = f"\n\nPERSONA OVERLAY:\n{persona_overlay}\n" if persona_overlay else ""

            enhanced_template = f"""Given the database schema below, write a SQL Server query to answer the user's question.

Database Schema:
{schema}
{metadata_context}
{persona_section}

{learnings_text}

{training_rules}

Question: {question}

CRITICAL INSTRUCTIONS - READ CAREFULLY:
1. Generate ONLY ONE SQL query - nothing else
2. NO explanations, NO comments, NO multiple queries
3. Answer EXACTLY what the user asked - don't add extra information
4. Use SQL Server syntax (MSSQL)
5. Pay attention to the column metadata and business terms above
6. Consider learned patterns from past queries
7. Use appropriate JOINs if needed - they are REQUIRED for multi-table answers
8. Ensure the query is safe and doesn't modify data
9. ALWAYS include supplier information when querying transactions/inventory
10. When joining tables, verify relationship fields (supplier_id, transaction_id, etc.)

MULTI-TABLE JOIN RULES (CRITICAL):
- When user asks about SUPPLIERS + INVENTORY/TRANSACTIONS: Use INNER JOIN linking suppliers to transaction tables
- Do NOT return supplier data without transaction details or vice versa
- Use: SELECT supplier_name, [transaction_fields] FROM suppliers INNER JOIN YarnData ON suppliers.supplier_id = YarnData.supplier_id
- Include ALL related columns from both tables in results, NOT just one table
- When comparing or aggregating: Include source table identification in aliases

CRITICAL - Column Naming Rules (MUST FOLLOW EXACTLY):
You MUST use human-readable column aliases with units. DO NOT use names like 'TotalYarnWeight' or 'sum_amount'.

REQUIRED FORMAT for YARN queries (YarnData table):
  - SUM(LBS) as 'Yarn Total LBS'
  - SUM(AMOUNT) as 'Yarn Total PKR'
  - SUM(BAGS) as 'Yarn Total Bags'
  - COUNT(*) as 'Yarn Count'

REQUIRED FORMAT for GREIGE/FABRIC queries (GreigeData table):
  - SUM(METER) as 'Greige Total Meters'
  - SUM(AMOUNT) as 'Greige Total PKR'
  - COUNT(*) as 'Greige Count'

REQUIRED FORMAT for SUPPLIER QUERIES:
  - Include 'supplier_name' or 'supplier_id' in SELECT
  - Use aliases with source context: 'Total LBS from Supplier', 'Total PKR by Supplier'
  - Add CONVERT(date, column_name) for date columns

EXAMPLES - Copy this format EXACTLY:
  ✅ CORRECT: SELECT SUM(LBS) as 'Yarn Total LBS' FROM YarnData WHERE ENTRY_TYPE='Yarn Arrival'
  ✅ CORRECT: SELECT TOP 10 supplier_name, SUM(amount) as 'Total PKR' FROM suppliers JOIN YarnData ON suppliers.supplier_id=YarnData.supplier_id GROUP BY supplier_name ORDER BY SUM(amount) DESC
  ❌ WRONG: SELECT SUM(LBS) as TotalYarnWeight FROM YarnData
  ❌ WRONG: SELECT SUM(LBS) as 'Total_LBS' FROM YarnData
  ❌ WRONG: SELECT supplier_name FROM suppliers (without transaction data)

SQL Query:"""
            
            return enhanced_template, applied_indices
        
        # Simple chain that formats prompt and calls LLM
        def sql_chain(inputs: dict) -> dict:
            question = inputs.get("question", "")
            persona_overlay = inputs.get("persona_overlay", "")
            formatted_prompt, applied_indices = build_enhanced_prompt(question, persona_overlay)
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
            return {"result": result, "response": response, "rules_applied": applied_indices}
        
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
    Fix column aliases to use human-readable format with units.
    Replaces technical names like 'TotalYarnWeight' with 'Yarn Total LBS'.
    
    Args:
        sql: SQL query string
        
    Returns:
        SQL with corrected column aliases
    """
    import re
    
    # Pattern to match AS alias (with or without quotes)
    # Matches: AS TotalYarnWeight, AS 'TotalYarnWeight', AS "TotalYarnWeight", AS Total_LBS, etc.
    
    # Fix common yarn aggregates
    sql = re.sub(r'\bAS\s+["\']?TotalYarnWeight["\']?', "AS 'Yarn Total LBS'", sql, flags=re.IGNORECASE)
    sql = re.sub(r'\bAS\s+["\']?Total_?Yarn_?Weight["\']?', "AS 'Yarn Total LBS'", sql, flags=re.IGNORECASE)
    sql = re.sub(r'\bAS\s+["\']?YarnTotal["\']?', "AS 'Yarn Total LBS'", sql, flags=re.IGNORECASE)
    
    sql = re.sub(r'\bAS\s+["\']?TotalYarnAmount["\']?', "AS 'Yarn Total PKR'", sql, flags=re.IGNORECASE)
    sql = re.sub(r'\bAS\s+["\']?Total_?Yarn_?Amount["\']?', "AS 'Yarn Total PKR'", sql, flags=re.IGNORECASE)
    
    sql = re.sub(r'\bAS\s+["\']?TotalBags["\']?', "AS 'Yarn Total Bags'", sql, flags=re.IGNORECASE)
    sql = re.sub(r'\bAS\s+["\']?Total_?Bags["\']?', "AS 'Yarn Total Bags'", sql, flags=re.IGNORECASE)
    
    # Fix greige aggregates
    sql = re.sub(r'\bAS\s+["\']?TotalMeters?["\']?', "AS 'Greige Total Meters'", sql, flags=re.IGNORECASE)
    sql = re.sub(r'\bAS\s+["\']?Total_?Meters?["\']?', "AS 'Greige Total Meters'", sql, flags=re.IGNORECASE)
    sql = re.sub(r'\bAS\s+["\']?GreigeTotal["\']?', "AS 'Greige Total Meters'", sql, flags=re.IGNORECASE)
    
    sql = re.sub(r'\bAS\s+["\']?TotalGreigeAmount["\']?', "AS 'Greige Total PKR'", sql, flags=re.IGNORECASE)
    sql = re.sub(r'\bAS\s+["\']?Total_?Greige_?Amount["\']?', "AS 'Greige Total PKR'", sql, flags=re.IGNORECASE)
    
    # Fix generic amount/total patterns
    sql = re.sub(r'\bAS\s+["\']?TotalAmount["\']?', "AS 'Total PKR'", sql, flags=re.IGNORECASE)
    sql = re.sub(r'\bAS\s+["\']?Total_?Amount["\']?', "AS 'Total PKR'", sql, flags=re.IGNORECASE)
    
    # Fix generic LBS patterns when not already fixed
    sql = re.sub(r'\bAS\s+["\']?Total_?LBS["\']?(?!\s*FROM\s+YarnData)', "AS 'Total LBS'", sql, flags=re.IGNORECASE)
    
    return sql

