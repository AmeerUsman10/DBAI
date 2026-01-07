"""
Gradio UI for DBAI Application
Provides a multi-tab interface for chat, settings, training, data import, and diagnostics.
"""
import logging
import os
import json
import io
import csv
from typing import List, Optional, Tuple
import gradio as gr
import yaml
from pathlib import Path
from dotenv import load_dotenv, set_key

from src.providers import create_provider
from src.database import reload_engine, test_connection, get_engine, run_query, get_sql_database, load_metadata, save_metadata
from src.llm import make_sql_chain, make_presentation_chain, make_describe_chain, extract_sql_from_response
from src.uploader import process_excel_files, check_table_exists, import_dataframe_to_db
from src.trainer import save_training_example
from src.diagnostics import collect_diagnostics
from src.clarity import analyze_query_clarity, needs_clarification
from src.learnings import save_learning, get_learning_stats
from src.quick_training import add_training_rule, get_training_stats, format_rules_display
from src.session_tracker import get_session_tracker, reset_session_tracker
from src.query_classifier import classify_query, needs_movement_clarification, get_clarification_for_classification
from src.query_templates import generate_sql_from_template

logger = logging.getLogger(__name__)
load_dotenv()

# Global state
current_provider = None
current_llm = None
session_tokens = {"total": 0, "prompt": 0, "completion": 0}  # Token tracking
session_tracker = get_session_tracker()  # Initialize session tracking
pending_clarification = {"question": None, "options": [], "original_query": None}  # Clarification state
last_query_info = {"question": None, "sql": None, "result": None}  # For corrections
last_query_result_data = None  # Store result data for CSV export
training_mode_enabled = False  # Live training mode toggle

# Persona definitions
PERSONAS = {
    "default": {
        "name": "Default Assistant",
        "prompt": "You are a helpful AI assistant for database queries. Provide clear, accurate answers."
    },
    "data_analyst": {
        "name": "Data Analyst",
        "prompt": "You are a senior data analyst. Provide detailed, technical answers. Focus on data quality, integrity, statistical insights, and trends. Use technical terminology and explain data patterns."
    },
    "business_executive": {
        "name": "Business Executive",
        "prompt": "You are a business executive. Provide high-level summaries focused on KPIs, business impact, and strategic insights. Keep answers concise and actionable. Emphasize ROI and business value."
    },
    "inventory_manager": {
        "name": "Inventory Manager",
        "prompt": "You are an inventory manager. Focus on stock levels, supplier performance, reorder points, and supply chain logistics. Provide practical recommendations for inventory optimization."
    },
    "sql_expert": {
        "name": "SQL Expert",
        "prompt": "You are a SQL database expert. Focus on query optimization, indexing strategies, and database performance. Explain technical details about joins, subqueries, and execution plans."
    },
    "financial_analyst": {
        "name": "Financial Analyst",
        "prompt": "You are a financial analyst. Focus on financial metrics, cost analysis, profitability, cash flow, and financial trends. Provide insights on financial performance and risks."
    },
    "operations_manager": {
        "name": "Operations Manager",
        "prompt": "You are an operations manager. Focus on efficiency, throughput, bottlenecks, and process optimization. Provide actionable recommendations to improve operational performance."
    },
    "compliance_officer": {
        "name": "Compliance Officer",
        "prompt": "You are a compliance and data governance officer. Focus on data privacy, regulatory compliance, audit trails, and data security. Highlight any compliance concerns."
    }
}

def load_system_instructions() -> str:
    """Load system instructions from file."""
    try:
        instructions_file = Path(__file__).parent.parent / "system_instructions.txt"
        if instructions_file.exists():
            with open(instructions_file, 'r') as f:
                return f.read().strip()
    except Exception as e:
        logger.error(f"Error loading system instructions: {e}")
    return ""

def save_system_instructions(instructions: str) -> Tuple[bool, str]:
    """Save system instructions to file."""
    try:
        instructions_file = Path(__file__).parent.parent / "system_instructions.txt"
        with open(instructions_file, 'w') as f:
            f.write(instructions)
        return True, "✅ System instructions saved successfully!"
    except Exception as e:
        logger.error(f"Error saving system instructions: {e}")
        return False, f"❌ Error: {str(e)}"

def load_config() -> dict:
    """Load configuration from config.yaml."""
    config_path = Path(__file__).parent.parent / "config.yaml"
    
    if not config_path.exists():
        # Create default config
        default_config = {
            'database': {
                'server': 'localhost',
                'database': 'master',
                'driver': 'ODBC Driver 18 for SQL Server',
                'username': '',
                'password': ''
            },
            'llm': {
                'provider': 'openai',
                'model': 'gpt-4o-mini',
                'temperature': 0.1,
                'max_tokens': 2000
            }
        }
        
        with open(config_path, 'w') as f:
            yaml.dump(default_config, f, default_flow_style=False)
        
        return default_config
    
    try:
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)
    except Exception as e:
        logger.error(f"Error loading config: {e}")
        return {}

def save_config(config: dict) -> bool:
    """Save configuration to config.yaml."""
    config_path = Path(__file__).parent.parent / "config.yaml"
    
    try:
        with open(config_path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False)
        return True
    except Exception as e:
        logger.error(f"Error saving config: {e}")
        return False

# Chat Tab Functions
def toggle_training_mode(enabled: bool) -> str:
    """Toggle live training mode on/off."""
    global training_mode_enabled
    training_mode_enabled = enabled
    
    if enabled:
        return "🎓 **Live Training Mode ACTIVE** - Feedback controls enabled"
    else:
        return "💬 Chat Mode - Standard responses"


def export_to_csv():
    """Export last query result to CSV file."""
    global last_query_result_data
    
    if last_query_result_data is None or last_query_result_data.empty:
        logger.warning("No data to export")
        return None
    
    try:
        from datetime import datetime
        
        # Create CSV in memory
        output = io.StringIO()
        last_query_result_data.to_csv(output, index=False)
        csv_content = output.getvalue()
        output.close()
        
        # Create temporary file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"query_result_{timestamp}.csv"
        filepath = f"logs/{filename}"
        
        os.makedirs("logs", exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(csv_content)
        
        logger.info(f"Exported {len(last_query_result_data)} rows to {filepath}")
        return filepath
    
    except Exception as e:
        logger.error(f"Export error: {e}")
        return None


def submit_correction(feedback_type: str, correction_text: str) -> str:
    """
    Submit feedback/correction for the last AI response.
    
    Args:
        feedback_type: 'thumbs_up', 'thumbs_down', or 'correction'
        correction_text: User's correction or feedback
        
    Returns:
        Confirmation message
    """
    global last_query_info, session_tracker
    
    if not last_query_info["question"]:
        return "❌ No recent query to provide feedback on"
    
    try:
        from src.quick_training import add_training_rule
        
        if feedback_type == "thumbs_up":
            # Positive feedback - log but don't create rule
            session_tracker.track_training_event(
                event_type="positive_feedback",
                details={"question": last_query_info["question"], "sql": last_query_info["sql"]}
            )
            return "✅ Positive feedback recorded - this approach will be reinforced"
        
        elif feedback_type == "thumbs_down" and correction_text.strip():
            # Negative feedback with correction - create training rule
            rule = f"CORRECTION: For queries like '{last_query_info['question']}': {correction_text.strip()}"
            success, message = add_training_rule(rule)
            
            # Track in session
            session_tracker.track_training_event(
                event_type="correction_submitted",
                details={
                    "question": last_query_info["question"],
                    "sql": last_query_info["sql"],
                    "correction": correction_text.strip(),
                    "rule_created": success
                }
            )
            
            if success:
                return f"✅ Training rule created from your correction\n\n**Rule:** {rule}"
            else:
                return f"❌ {message}"
        
        elif feedback_type == "thumbs_down":
            # Negative feedback without correction
            session_tracker.track_training_event(
                event_type="negative_feedback",
                details={"question": last_query_info["question"], "sql": last_query_info["sql"]}
            )
            return "👎 Negative feedback recorded. Please provide a correction to create a training rule."
        
        else:
            return "❌ Invalid feedback type"
            
    except Exception as e:
        logger.error(f"Error submitting correction: {e}")
        return f"❌ Error: {str(e)}"


def extract_token_usage(response) -> dict:
    """Extract token usage from LLM response if available."""
    tokens = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    
    try:
        # OpenAI responses have usage_metadata or response_metadata
        if hasattr(response, 'response_metadata'):
            usage = response.response_metadata.get('token_usage', {})
            tokens['prompt_tokens'] = usage.get('prompt_tokens', 0)
            tokens['completion_tokens'] = usage.get('completion_tokens', 0)
            tokens['total_tokens'] = usage.get('total_tokens', 0)
        elif hasattr(response, 'usage_metadata'):
            usage = response.usage_metadata
            tokens['prompt_tokens'] = getattr(usage, 'input_tokens', 0)
            tokens['completion_tokens'] = getattr(usage, 'output_tokens', 0)
            tokens['total_tokens'] = tokens['prompt_tokens'] + tokens['completion_tokens']
    except Exception as e:
        logger.debug(f"Could not extract token usage: {e}")
    
    return tokens

def chat_query(question: str, history: List, persona: str = "default") -> Tuple[str, List]:
    """
    Process a natural language query with clarity checking and learning.
    
    Args:
        question: User's question
        history: Chat history
        persona: Selected persona
        
    Returns:
        Tuple of (response, updated_history)
    """
    global current_llm, current_provider, session_tokens, pending_clarification, session_tracker
    
    if not question.strip():
        return "", history
    
    # Initialize tracking variables
    import time
    start_time = time.time()
    clarity_data = None
    llm_data = None
    execution_data = None
    error_data = None
    
    # Check if this is a response to a clarification request (user typed a number 1-4)
    if pending_clarification["question"] and question.strip().isdigit():
        choice_num = int(question.strip())
        if 1 <= choice_num <= len(pending_clarification["options"]):
            # User selected an option - use the clarified query
            original_query = pending_clarification["original_query"]
            question = pending_clarification["options"][choice_num - 1]
            
            # Clear pending state but remember original for learning
            pending_clarification["question"] = None
            pending_clarification["options"] = []
            # Keep original_query for learning after successful execution
    
    # Analyze query clarity (skip if already clarified above)
    if not pending_clarification.get("original_query"):
        # CLASSIFY FIRST to detect breakdown/template potential
        classification = classify_query(question)
        logger.info(f"Query classified as: {classification['type']} (confidence: {classification['confidence']}%)")
        
        # Skip clarity check if breakdown detected or high-confidence template
        skip_clarity = (
            classification.get('params', {}).get('breakdown') or 
            classification['confidence'] >= 80
        )
        
        if not skip_clarity:
            clarity_score, reason, clarifications = analyze_query_clarity(question)
            
            # Track clarity analysis
            clarity_data = {
                "score": clarity_score,
                "needs_clarification": needs_clarification(clarity_score, threshold=70),
                "reason": reason,
                "clarifications_offered": clarifications
            }
            
            # If query needs clarification (score < 70)
            if needs_clarification(clarity_score, threshold=70) and clarifications:
                # Store clarification state
                pending_clarification["question"] = question
                pending_clarification["options"] = clarifications
                pending_clarification["original_query"] = question
                
                # Generate clarification message
                response = f"I'd like to better understand your query: **\"{question}\"**\n\n"
                response += f"Could you clarify which of these you're looking for?\n\n"
                
                for i, option in enumerate(clarifications, 1):
                    response += f"**{i}.** {option}\n"
                
                response += "\n*Simply reply with the number (1-4) that matches your intent, or rephrase your question.*"
                
                # Track clarification request
                session_tracker.track_query(
                    user_question=question,
                    clarity_analysis=clarity_data,
                    llm_interaction=None,
                    execution=None,
                    response={"type": "clarification_request", "text": response},
                    performance={"total_time_ms": int((time.time() - start_time) * 1000)},
                    error=None
                )
                
                history.append({"role": "user", "content": question})
                history.append({"role": "assistant", "content": response})
                
                return "", history
    
    try:
        # Load config and initialize provider if needed
        config = load_config()
        llm_config = config.get('llm', {})
        
        provider_name = llm_config.get('provider', 'openai')
        model = llm_config.get('model', 'gpt-4o-mini')
        temperature = llm_config.get('temperature', 0.1)
        max_tokens = llm_config.get('max_tokens', 2000)
        
        if current_provider is None or current_llm is None:
            current_provider = create_provider(provider_name)
            current_llm = current_provider.get_llm(model, temperature, max_tokens)
        
        # Get database
        db = get_sql_database()
        if not db:
            response = "❌ Database not available. Please check your database settings."
            history.append({"role": "user", "content": question})
            history.append({"role": "assistant", "content": response})
            return "", history
        
        # Track tokens for this response
        response_tokens = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        
        # LOG: User question
        logger.info(f"USER QUERY: {question}")
        
        # HYBRID APPROACH: Try template-based generation first
        # (classification already done before clarity check)
        sql_query = None
        llm_raw_response = None
        generation_method = "llm"  # Default
        
        # Check if needs movement type clarification (via classification, not clarity system)
        if needs_movement_clarification(classification):
            # Use classification-based clarification
            clarifications = get_clarification_for_classification(classification)
            
            # Store clarification state
            pending_clarification["question"] = question
            pending_clarification["options"] = clarifications
            pending_clarification["original_query"] = question
            
            # Generate clarification message
            response = f"I'd like to better understand your query: **\"{question}\"**\n\n"
            response += f"Could you clarify which of these you're looking for?\n\n"
            
            for i, option in enumerate(clarifications, 1):
                response += f"**{i}.** {option}\n"
            
            response += "\n*Simply reply with the number (1-4) that matches your intent, or rephrase your question.*"
            
            # Track clarification request
            session_tracker.track_query(
                user_question=question,
                clarity_analysis={"score": classification['confidence'], "needs_clarification": True, "reason": "Movement type required for supplier ranking"},
                llm_interaction=None,
                execution=None,
                response={"type": "clarification_request", "text": response},
                performance={"total_time_ms": int((time.time() - start_time) * 1000)},
                error=None
            )
            
            history.append({"role": "user", "content": question})
            history.append({"role": "assistant", "content": response})
            
            return "", history
        
        # Try template generation for high-confidence classifications
        if classification['confidence'] >= 80:
            template_sql = generate_sql_from_template(classification)
            if template_sql:
                sql_query = template_sql
                generation_method = "template"
                logger.info(f"✅ Using TEMPLATE generation (no LLM needed)")
        
        # Fall back to LLM if template didn't work
        if not sql_query:
            logger.info(f"⚠️ Template not available, using LLM generation")
            # Generate SQL using LLM
            sql_chain = make_sql_chain(current_llm, db)
            sql_response_obj = sql_chain({"question": question})
            
            # Extract token usage from SQL generation
            if isinstance(sql_response_obj, dict) and 'response' in sql_response_obj:
                tokens = extract_token_usage(sql_response_obj['response'])
                response_tokens['prompt_tokens'] += tokens['prompt_tokens']
                response_tokens['completion_tokens'] += tokens['completion_tokens']
                response_tokens['total_tokens'] += tokens['total_tokens']
            
            # Extract SQL from response
            if isinstance(sql_response_obj, dict):
                sql_query = sql_response_obj.get('result', '')
                llm_raw_response = str(sql_response_obj)
            else:
                sql_query = str(sql_response_obj)
                llm_raw_response = sql_query
            
            # LOG: Raw LLM response before extraction
            logger.debug(f"LLM RAW RESPONSE: {sql_query[:500]}")
            
            sql_query = extract_sql_from_response(sql_query)
        
        # LOG: Generated SQL query
        logger.info(f"GENERATED SQL ({generation_method}): {sql_query}")
        
        # Track LLM interaction
        llm_data = {
            "provider": provider_name if generation_method == "llm" else "template",
            "model": model if generation_method == "llm" else "rule-based",
            "temperature": temperature,
            "sql_generated": sql_query,
            "tokens": response_tokens,
            "generation_method": generation_method  # NEW: track if template or LLM
        }
        # Add raw response only if tier 2 enabled
        from src.session_tracker import get_observability_config
        config = get_observability_config()
        if config.get("capture_llm_prompts", False) and llm_raw_response:
            llm_data["raw_response"] = llm_raw_response
        
        # Execute query
        query_start = time.time()
        success, result = run_query(sql_query)
        query_time_ms = int((time.time() - query_start) * 1000)
        
        # Track execution
        execution_data = {
            "sql_query": sql_query,
            "success": success,
            "execution_time_ms": query_time_ms
        }
        
        if success:
            if isinstance(result, dict) and 'rows' in result:
                execution_data["rows_returned"] = len(result.get('rows', []))
                execution_data["columns"] = result.get('columns', [])
                
                # Add sample data only if tier 2 enabled
                if config.get("capture_sample_data", False) and result.get('rows'):
                    execution_data["sample_rows"] = result['rows'][:3]
                
                logger.info(f"QUERY SUCCESS: {len(result.get('rows', []))} rows returned")
                # Log first few rows for debugging
                if result.get('rows'):
                    logger.debug(f"SAMPLE RESULTS: {result['rows'][:3]}")
            else:
                execution_data["result"] = str(result)
                logger.info(f"QUERY SUCCESS: {result}")
        else:
            execution_data["error_message"] = str(result)
            logger.error(f"QUERY FAILED: {result}")
        
        if success:
            # Generate conversational explanation first (if data returned)
            conversational_response = ""
            
            if isinstance(result, dict) and 'columns' in result and 'rows' in result and result['rows']:
                try:
                    # Create a summary of the data for the LLM
                    data_summary = {
                        "user_question": question,
                        "sql_query": sql_query,
                        "columns": result['columns'],
                        "row_count": len(result['rows']),
                        "sample_rows": result['rows'][:3]  # First 3 rows for context
                    }
                    
                    # Ask LLM to explain the results conversationally
                    explain_prompt = f"""The user asked: "{question}"

The database returned {len(result['rows'])} rows with these columns: {', '.join(result['columns'])}

Sample data:
{result['rows'][:3]}

Provide a BRIEF, PROFESSIONAL business summary (1-2 sentences maximum) that:
1. Directly answers the user's question with specific numbers
2. Uses professional textile/manufacturing terminology
3. States facts without commentary or enthusiasm

REQUIREMENTS:
- Maximum 2 sentences
- Professional tone (business reporting, not casual chat)
- No phrases like "quite substantial", "fascinating", "interesting"
- No exclamation marks
- Focus on facts: totals, counts, trends
- Use industry terms: inventory, production, procurement, supply chain

Example good response: "The yarn department has a total inventory of 22.37 million LBS valued at 7.31 billion PKR across 2,784 records."

Example bad response: "The total is quite substantial! It's fascinating to think about..."

Keep it concise and factual."""
                    
                    explanation = current_llm.invoke(explain_prompt)
                    conversational_text = explanation.content if hasattr(explanation, 'content') else str(explanation)
                    
                    # Extract token usage from explanation
                    explain_tokens = extract_token_usage(explanation)
                    response_tokens['prompt_tokens'] += explain_tokens['prompt_tokens']
                    response_tokens['completion_tokens'] += explain_tokens['completion_tokens']
                    response_tokens['total_tokens'] += explain_tokens['total_tokens']
                    
                    conversational_response = f"{conversational_text}\n\n---\n\n"
                    
                except Exception as e:
                    logger.warning(f"Failed to generate conversational response: {e}")
                    # Continue with just the data table
            
            # Format response with smart unit detection
            response = conversational_response
            
            # Try to detect column units from metadata or column name
            def get_column_unit(col_name):
                """Get unit for a column from metadata or intelligent detection."""
                # First try metadata
                try:
                    metadata = load_metadata()
                    for table_name, table_data in metadata.get('tables', {}).items():
                        columns = table_data.get('columns', table_data)
                        if col_name in columns:
                            col_info = columns[col_name]
                            if isinstance(col_info, dict):
                                unit = col_info.get('unit')
                                if unit:
                                    return unit
                except:
                    pass
                
                # Smart detection from column name (order matters - most specific first!)
                col_lower = col_name.lower()
                if 'lbs' in col_lower or 'weight' in col_lower:
                    return 'LBS'
                elif 'yarn' in col_lower and 'amount' not in col_lower:
                    return 'LBS'  # Yarn columns usually refer to weight unless amount
                elif 'meter' in col_lower or 'greige' in col_lower or 'fabric' in col_lower:
                    return 'Meters'
                elif 'bag' in col_lower:
                    return 'Bags'
                elif 'amount' in col_lower or 'pkr' in col_lower or 'price' in col_lower:
                    return 'PKR'
                
                return None
            
            if isinstance(result, dict):
                if 'columns' in result and 'rows' in result:
                    response += f"**Query Results** ({len(result['rows'])} rows)\n\n"
                    
                    # Special handling for single aggregate results - format numbers directly in table
                    is_single_aggregate = len(result['rows']) == 1 and len(result['columns']) == 1
                    
                    # Create properly formatted table
                    if result['rows']:
                        # For single aggregates, format the value with commas
                        display_rows = result['rows']
                        if is_single_aggregate:
                            value = result['rows'][0][0]
                            if isinstance(value, (int, float)):
                                formatted_value = f"{value:,}"
                                display_rows = [[formatted_value]]
                        
                        # Calculate column widths for better alignment
                        col_widths = {}
                        for i, col in enumerate(result['columns']):
                            col_widths[i] = max(
                                len(str(col)),
                                max((len(str(row[i])) for row in display_rows[:20]), default=0)
                            )
                        
                        # Header
                        header_cells = [str(col).ljust(col_widths[i]) for i, col in enumerate(result['columns'])]
                        response += "| " + " | ".join(header_cells) + " |\n"
                        
                        # Separator
                        separator_cells = ["-" * col_widths[i] for i in range(len(result['columns']))]
                        response += "| " + " | ".join(separator_cells) + " |\n"
                        
                        # Rows (limit to 20)
                        for row in display_rows[:20]:
                            row_cells = [str(v).ljust(col_widths[i]) for i, v in enumerate(row)]
                            response += "| " + " | ".join(row_cells) + " |\n"
                        
                        if len(result['rows']) > 20:
                            response += f"\n*Showing 20 of {len(result['rows'])} rows*"
                else:
                    response += f"**Result:** {result.get('message', 'Success')}"
            else:
                response += f"**Result:** {result}"
        else:
            response = f"❌ **Error:** {result}"
        
        # Save learning if this was a clarified query
        if pending_clarification.get("original_query") and success:
            original = pending_clarification["original_query"]
            save_learning(original, question, sql_query, "positive")
            pending_clarification["original_query"] = None  # Clear after saving
        
        # Add learning and training stats
        stats = get_learning_stats()
        training_stats = get_training_stats()
        
        # Add generation method indicator
        method_icon = "⚡" if generation_method == "template" else "🤖"
        method_text = "Template" if generation_method == "template" else "LLM"
        
        if stats["total"] > 0 or training_stats["total"] > 0:
            response += f"\n\n<sub>🧠 Knowledge: {stats['total']} learned patterns · {training_stats['total']} training rules · {method_icon} {method_text}</sub>"
        else:
            response += f"\n\n<sub>{method_icon} Generated via {method_text}</sub>"
        
        # Add token usage info if available (only for OpenAI and LLM generation)
        if generation_method == "llm" and provider_name == 'openai' and response_tokens['total_tokens'] > 0:
            session_tokens['prompt'] += response_tokens['prompt_tokens']
            session_tokens['completion'] += response_tokens['completion_tokens']
            session_tokens['total'] += response_tokens['total_tokens']
            
            response += f"\n\n<sub>🔹 Tokens: {response_tokens['total_tokens']} · Session: {session_tokens['total']:,}</sub>"
        elif generation_method == "template":
            response += f"\n\n<sub>⚡ Zero tokens used (template-based)</sub>"
        
        # LOG: Final response sent to user
        logger.info(f"RESPONSE SENT: {len(response)} chars | Success: {success} | Tokens: {response_tokens.get('total_tokens', 0)}")
        logger.debug(f"RESPONSE PREVIEW: {response[:200]}")
        
        # Save last query info for live training mode corrections
        global last_query_info, last_query_result_data
        last_query_info = {
            "question": question,
            "sql": sql_query,
            "result": response,
            "success": success
        }
        
        # Store result data for export
        if success and isinstance(result, dict) and 'rows' in result and 'columns' in result:
            import pandas as pd
            last_query_result_data = pd.DataFrame(result['rows'], columns=result['columns'])
        else:
            last_query_result_data = None
        
        # Track complete query lifecycle
        total_time_ms = int((time.time() - start_time) * 1000)
        session_tracker.track_query(
            user_question=question,
            clarity_analysis=clarity_data,
            llm_interaction=llm_data,
            execution=execution_data,
            response={
                "type": "data" if success else "error",
                "text": response,
                "length_chars": len(response)
            },
            performance={
                "total_time_ms": total_time_ms,
                "query_time_ms": execution_data.get("execution_time_ms", 0),
                "tokens": response_tokens
            },
            error=None
        )
        
        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": response})
        return "", history
        
    except Exception as e:
        logger.error(f"Chat query error: {e}", exc_info=True)
        response = f"❌ Error: {str(e)}"
        
        # Track error
        total_time_ms = int((time.time() - start_time) * 1000)
        error_data = {
            "type": type(e).__name__,
            "message": str(e),
            "traceback": str(e)
        }
        
        session_tracker.track_query(
            user_question=question,
            clarity_analysis=clarity_data,
            llm_interaction=llm_data,
            execution=execution_data,
            response={"type": "error", "text": response},
            performance={"total_time_ms": total_time_ms},
            error=error_data
        )
        
        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": response})
        return "", history

# Settings Tab Functions
def get_available_models(provider: str) -> List[str]:
    """Get available models for the selected provider."""
    try:
        prov = create_provider(provider)
        models = prov.list_models()
        return models if models else ["No models available"]
    except Exception as e:
        logger.error(f"Error getting models: {e}")
        return ["Error loading models"]

def test_provider_connection(provider: str, model: str, api_key: str) -> str:
    """Test provider connectivity."""
    try:
        if not api_key or api_key.strip() == "":
            return "❌ Please enter an API key"
        
        prov = create_provider(provider, api_key)
        success, message = prov.test_connection(model)
        
        if success:
            return f"✅ {message}"
        else:
            return f"❌ {message}"
    except Exception as e:
        logger.error(f"Provider test error: {e}", exc_info=True)
        return f"❌ Error: {str(e)}"

def save_api_key(provider: str, api_key: str) -> str:
    """Save API key to .env file."""
    try:
        env_path = Path(__file__).parent.parent / ".env"
        
        # Create .env if it doesn't exist
        if not env_path.exists():
            env_path.touch()
        
        # Save key
        key_name = f"{provider.upper()}_API_KEY"
        set_key(env_path, key_name, api_key)
        
        # Reload environment
        load_dotenv(override=True)
        
        return f"✅ API key saved for {provider}"
    except Exception as e:
        logger.error(f"Error saving API key: {e}")
        return f"❌ Error saving API key: {str(e)}"

def save_settings(
    provider: str,
    model: str,
    temperature: float,
    max_tokens: int,
    db_server: str,
    db_name: str,
    db_driver: str,
    db_username: str,
    db_password: str
) -> str:
    """Save all settings and reload database connection."""
    global current_provider, current_llm, session_tracker
    
    try:
        # Update config
        config = load_config()
        
        # Track old settings for comparison
        old_llm_config = config.get('llm', {})
        old_db_config = config.get('database', {})
        
        config['llm'] = {
            'provider': provider,
            'model': model,
            'temperature': temperature,
            'max_tokens': max_tokens
        }
        
        config['database'] = {
            'server': db_server,
            'database': db_name,
            'driver': db_driver,
            'username': db_username,
            'password': db_password
        }
        
        if save_config(config):
            # Track configuration changes
            changes = {}
            if old_llm_config.get('provider') != provider:
                changes['provider'] = {'old': old_llm_config.get('provider'), 'new': provider}
            if old_llm_config.get('model') != model:
                changes['model'] = {'old': old_llm_config.get('model'), 'new': model}
            if old_db_config.get('database') != db_name:
                changes['database'] = {'old': old_db_config.get('database'), 'new': db_name}
            
            if changes:
                session_tracker.update_app_state(
                    provider=provider,
                    model=model,
                    database=db_name,
                    changes=changes
                )
            
            # Reset LLM instances to force reload
            current_provider = None
            current_llm = None
            
            # Reload database engine
            db_success, db_message = reload_engine()
            
            if db_success:
                return f"✅ Settings saved successfully!\n{db_message}"
            else:
                return f"⚠️ Settings saved but database connection failed:\n{db_message}"
        else:
            return "❌ Failed to save settings"
            
    except Exception as e:
        logger.error(f"Error saving settings: {e}")
        return f"❌ Error: {str(e)}"

def load_settings() -> Tuple:
    """Load current settings from config."""
    config = load_config()
    
    llm_config = config.get('llm', {})
    db_config = config.get('database', {})
    
    return (
        llm_config.get('provider', 'openai'),
        llm_config.get('model', 'gpt-4o-mini'),
        llm_config.get('temperature', 0.1),
        llm_config.get('max_tokens', 2000),
        db_config.get('server', 'localhost'),
        db_config.get('database', 'master'),
        db_config.get('driver', 'ODBC Driver 18 for SQL Server'),
        db_config.get('username', ''),
        db_config.get('password', '')
    )

# Import Data Tab Functions
def analyze_files(files: List) -> str:
    """Analyze uploaded Excel files."""
    if not files:
        return "No files uploaded"
    
    try:
        file_paths = [f.name for f in files]
        results = process_excel_files(file_paths)
        
        output = "# File Analysis Results\n\n"
        
        for file_name, result in results.items():
            output += f"## {file_name}\n\n"
            
            if result['success']:
                output += f"**Table Name:** `{result['table_name']}`\n\n"
                output += f"**Size:** {result['row_count']} rows × {result['column_count']} columns\n\n"
                output += f"**Preview:**\n```\n{result['preview']}\n```\n\n"
                output += f"**CREATE TABLE SQL:**\n```sql\n{result['create_sql']}\n```\n\n"
            else:
                output += f"❌ **Error:** {result['error']}\n\n"
            
            output += "---\n\n"
        
        return output
        
    except Exception as e:
        logger.error(f"File analysis error: {e}", exc_info=True)
        return f"❌ Error analyzing files: {str(e)}"

def describe_files_ai(files: List) -> str:
    """Use AI to describe uploaded files."""
    global current_llm, current_provider
    
    if not files:
        return "No files uploaded"
    
    try:
        # Load config and initialize provider if needed
        config = load_config()
        llm_config = config.get('llm', {})
        
        provider_name = llm_config.get('provider', 'groq')
        model = llm_config.get('model', 'llama-3.1-8b-instant')
        
        if current_provider is None or current_llm is None:
            current_provider = create_provider(provider_name)
            current_llm = current_provider.get_llm(model, 0.1, 2000)
        
        file_paths = [f.name for f in files]
        results = process_excel_files(file_paths)
        
        describe_chain = make_describe_chain(current_llm)
        
        output = "# AI-Powered Data Analysis\n\n"
        
        for file_name, result in results.items():
            output += f"## {file_name}\n\n"
            
            if result['success']:
                df = result['dataframe']
                sample = df.head(10).to_string()
                schema = str(df.dtypes.to_dict())
                
                description = describe_chain(file_name, sample, schema)
                output += f"{description}\n\n"
            else:
                output += f"❌ **Error:** {result['error']}\n\n"
            
            output += "---\n\n"
        
        return output
        
    except Exception as e:
        logger.error(f"AI description error: {e}", exc_info=True)
        return f"❌ Error: {str(e)}"

def import_files_to_db(files: List, overwrite: bool) -> str:
    """Import files to database."""
    if not files:
        return "No files uploaded"
    
    try:
        engine = get_engine()
        if not engine:
            return "❌ Database engine not available"
        
        file_paths = [f.name for f in files]
        results = process_excel_files(file_paths)
        
        output = "# Import Results\n\n"
        
        for file_name, result in results.items():
            output += f"## {file_name}\n\n"
            
            if result['success']:
                table_name = result['table_name']
                df = result['dataframe']
                
                # Check if table exists
                exists = check_table_exists(engine, table_name)
                
                if exists and not overwrite:
                    output += f"⚠️ Table `{table_name}` already exists. Enable overwrite to replace.\n\n"
                else:
                    if_exists = 'replace' if overwrite else 'fail'
                    success, message = import_dataframe_to_db(engine, df, table_name, if_exists)
                    
                    if success:
                        output += f"✅ {message}\n\n"
                    else:
                        output += f"❌ {message}\n\n"
            else:
                output += f"❌ **Error:** {result['error']}\n\n"
            
            output += "---\n\n"
        
        return output
        
    except Exception as e:
        logger.error(f"Import error: {e}", exc_info=True)
        return f"❌ Error: {str(e)}"

# Diagnostics Tab Functions
def collect_and_download_diagnostics() -> Optional[str]:
    """Collect diagnostics and return file path for download."""
    try:
        diag_file = collect_diagnostics()
        return diag_file
    except Exception as e:
        logger.error(f"Diagnostics collection error: {e}", exc_info=True)
        return None

# Build UI
def build_ui():
    """Build and return the Gradio interface."""
    
    with gr.Blocks(title="DBAI - Database AI Assistant", theme=gr.themes.Default()) as demo:
        gr.Markdown("# 🤖 DBAI - Database AI Assistant")
        gr.Markdown("Ask questions about your database in natural language!")
        
        with gr.Tabs():
            # Chat Tab
            with gr.Tab("💬 Chat"):
                with gr.Row():
                    persona_selector = gr.Dropdown(
                        choices=[(p["name"], k) for k, p in PERSONAS.items()],
                        value="default",
                        label="🎭 Persona",
                        scale=1
                    )
                
                chatbot = gr.Chatbot(height=400, label="Conversation")
                
                with gr.Row():
                    question_input = gr.Textbox(
                        placeholder="Ask a question about your database...",
                        label="Your Question",
                        scale=4
                    )
                    export_csv_btn = gr.DownloadButton(
                        "📥 Export CSV",
                        variant="secondary",
                        scale=1,
                        size="sm"
                    )
                
                with gr.Row():
                    send_stop_btn = gr.Button("▶ Send", variant="primary", scale=2)
                    clear_btn = gr.Button("Clear Chat", size="sm", variant="secondary", scale=1)
                
                # Live Training Mode Controls
                with gr.Row():
                    with gr.Column(scale=2):
                        training_mode_toggle = gr.Checkbox(
                            label="🎓 Live Training Mode",
                            value=False,
                            info="Enable feedback controls to improve AI responses in real-time"
                        )
                        training_mode_status = gr.Markdown("💬 Chat Mode - Standard responses")
                    
                    with gr.Column(scale=3, visible=False) as feedback_panel:
                        gr.Markdown("### Provide Feedback on Last Response")
                        with gr.Row():
                            thumbs_up_btn = gr.Button("👍 Good Response", size="sm", scale=1)
                            thumbs_down_btn = gr.Button("👎 Needs Improvement", size="sm", scale=1)
                        
                        correction_input = gr.Textbox(
                            placeholder="Explain what was wrong and how it should be...",
                            label="Correction / Feedback",
                            lines=2,
                            visible=False
                        )
                        submit_correction_btn = gr.Button("Submit Correction", visible=False, variant="primary")
                        correction_status = gr.Markdown("")
                
                # Toggle training mode visibility
                training_mode_toggle.change(
                    lambda enabled: (
                        gr.update(visible=enabled),
                        "🎓 **Live Training Mode ACTIVE** - Feedback controls enabled" if enabled else "💬 Chat Mode - Standard responses"
                    ),
                    inputs=[training_mode_toggle],
                    outputs=[feedback_panel, training_mode_status]
                ).then(
                    toggle_training_mode,
                    inputs=[training_mode_toggle],
                    outputs=[]
                )
                
                # Thumbs up feedback
                thumbs_up_btn.click(
                    lambda: submit_correction("thumbs_up", ""),
                    outputs=[correction_status]
                )
                
                # Thumbs down - show correction input
                thumbs_down_btn.click(
                    lambda: (gr.update(visible=True), gr.update(visible=True), "👎 Please explain what was wrong..."),
                    outputs=[correction_input, submit_correction_btn, correction_status]
                )
                
                # Submit correction
                submit_correction_btn.click(
                    lambda text: submit_correction("thumbs_down", text),
                    inputs=[correction_input],
                    outputs=[correction_status]
                ).then(
                    lambda: (gr.update(value="", visible=False), gr.update(visible=False)),
                    outputs=[correction_input, submit_correction_btn]
                )
                
                # Query event tracking
                is_running = gr.State(False)
                
                # Handle button click
                send_stop_btn.click(
                    lambda: (gr.update(value="⏹ Stop", variant="stop"), True),
                    outputs=[send_stop_btn, is_running]
                ).then(
                    chat_query,
                    inputs=[question_input, chatbot, persona_selector],
                    outputs=[question_input, chatbot]
                ).then(
                    lambda: (False, gr.update(value="▶ Send", variant="primary")),
                    outputs=[is_running, send_stop_btn]
                )
                
                question_input.submit(
                    lambda: (gr.update(value="⏹ Stop", variant="stop"), True),
                    outputs=[send_stop_btn, is_running]
                ).then(
                    chat_query,
                    inputs=[question_input, chatbot, persona_selector],
                    outputs=[question_input, chatbot]
                ).then(
                    lambda: (False, gr.update(value="▶ Send", variant="primary")),
                    outputs=[is_running, send_stop_btn]
                )
                
                clear_btn.click(lambda: [], outputs=chatbot)
                
                # Export CSV button
                export_csv_btn.click(
                    fn=export_to_csv,
                    outputs=export_csv_btn
                )
            
            # Settings Tab
            with gr.Tab("⚙️ Settings"):
                gr.Markdown("## LLM Provider Settings")
                
                with gr.Row():
                    provider_dropdown = gr.Dropdown(
                        choices=["openai", "groq"],
                        label="Provider",
                        value="openai"
                    )
                    model_dropdown = gr.Dropdown(
                        choices=[],
                        label="Model",
                        value="gpt-4o-mini",
                        allow_custom_value=True
                    )
                
                with gr.Row():
                    temperature_slider = gr.Slider(
                        minimum=0,
                        maximum=1,
                        value=0.1,
                        step=0.1,
                        label="Temperature"
                    )
                    max_tokens_slider = gr.Slider(
                        minimum=100,
                        maximum=4000,
                        value=2000,
                        step=100,
                        label="Max Tokens"
                    )
                
                gr.Markdown("### API Key Management")
                gr.Markdown("*API key loaded from environment variable by default. Override here if needed.*")
                
                with gr.Row():
                    api_key_input = gr.Textbox(
                        label="API Key (optional - uses env var if empty)",
                        type="password",
                        placeholder="Leave empty to use environment variable",
                        value=""
                    )
                    save_key_btn = gr.Button("Save API Key")
                    test_btn = gr.Button("Test Connection")
                
                test_output = gr.Textbox(label="Connection Status", interactive=False)
                
                gr.Markdown("## Database Settings")
                
                with gr.Row():
                    db_server = gr.Textbox(label="Server", value="localhost")
                    db_name = gr.Textbox(label="Database", value="master")
                
                with gr.Row():
                    db_driver = gr.Textbox(
                        label="Driver",
                        value="ODBC Driver 18 for SQL Server"
                    )
                
                with gr.Row():
                    db_username = gr.Textbox(label="Username (optional)")
                    db_password = gr.Textbox(label="Password (optional)", type="password")
                
                save_settings_btn = gr.Button("Save Settings", variant="primary")
                settings_output = gr.Textbox(label="Status", interactive=False)
                
                # Event handlers
                def update_models(provider):
                    models = get_available_models(provider)
                    return gr.Dropdown(choices=models, value=models[0] if models else "")
                
                provider_dropdown.change(
                    update_models,
                    inputs=[provider_dropdown],
                    outputs=[model_dropdown]
                )
                
                save_key_btn.click(
                    save_api_key,
                    inputs=[provider_dropdown, api_key_input],
                    outputs=[test_output]
                )
                
                test_btn.click(
                    test_provider_connection,
                    inputs=[provider_dropdown, model_dropdown, api_key_input],
                    outputs=[test_output]
                )
                
                save_settings_btn.click(
                    save_settings,
                    inputs=[
                        provider_dropdown, model_dropdown, temperature_slider, max_tokens_slider,
                        db_server, db_name, db_driver, db_username, db_password
                    ],
                    outputs=[settings_output]
                )
                
                # Load current settings on page load
                demo.load(
                    load_settings,
                    outputs=[
                        provider_dropdown, model_dropdown, temperature_slider, max_tokens_slider,
                        db_server, db_name, db_driver, db_username, db_password
                    ]
                )
                
                # Update model list when provider changes
                demo.load(
                    lambda: get_available_models("openai"),
                    outputs=[model_dropdown]
                )
            
            # Train Tab - Quick Setup
            with gr.Tab("🎓 Train"):
                gr.Markdown("## AI Training & Configuration")
                gr.Markdown("Configure how the AI understands and interacts with your database.")
                
                with gr.Tabs():
                    # Quick Training Tab (FREE-FORM INSTRUCTIONS)
                    with gr.Tab("⚡ Quick Training"):
                        gr.Markdown("""### Write Training Instructions in Plain English
Tell the AI exactly how to interpret your queries. These rules apply immediately!

**Examples:**
- "When I ask 'total greige rcvd', always return meters of greige fabric received"
- "When I say 'arrival yarn', I mean LBS of yarn received, not amount in PKR"
- "Stock check should show current inventory in both LBS and bags"
""")
                        
                        training_instruction = gr.Textbox(
                            label="Training Instruction",
                            placeholder='Example: When I ask "total arrival yarn", return total LBS received, NOT total amount in PKR.',
                            lines=3
                        )
                        
                        with gr.Row():
                            add_training_btn = gr.Button("💾 Add Training Rule", variant="primary", size="lg")
                            clear_training_input_btn = gr.Button("🔄 Clear", variant="secondary")
                        
                        training_status = gr.Markdown("")
                        
                        gr.Markdown("---")
                        gr.Markdown("### Active Training Rules")
                        training_rules_display = gr.Markdown("")
                        
                        def add_training(instruction):
                            """Add a quick training rule."""
                            # LOG: User adding training rule
                            logger.info(f"USER TRAINING: Adding rule - '{instruction[:100]}'")
                            
                            success, msg = add_training_rule(instruction)
                            
                            if success:
                                logger.info(f"TRAINING SUCCESS: Rule added - {msg}")
                                
                                # Track training event
                                session_tracker.track_training_event(
                                    event_type="quick_training_rule_added",
                                    details={
                                        "instruction": instruction,
                                        "success": True,
                                        "message": msg
                                    }
                                )
                                
                                # Get stats to show in message
                                stats = get_training_stats()
                                display_msg = f"{msg}\n\n🎉 **New training event!** This rule is now active."
                                return display_msg, format_rules_display(), ""
                            else:
                                logger.warning(f"TRAINING FAILED: {msg}")
                                
                                # Track failed training attempt
                                session_tracker.track_training_event(
                                    event_type="quick_training_rule_failed",
                                    details={
                                        "instruction": instruction,
                                        "success": False,
                                        "error": msg
                                    }
                                )
                                
                                return f"❌ {msg}", format_rules_display(), instruction
                        
                        add_training_btn.click(
                            add_training,
                            inputs=[training_instruction],
                            outputs=[training_status, training_rules_display, training_instruction]
                        )
                        
                        clear_training_input_btn.click(
                            lambda: "",
                            outputs=[training_instruction]
                        )
                        
                        # Load rules on page load
                        demo.load(
                            format_rules_display,
                            outputs=[training_rules_display]
                        )
                    
                    # System Instructions Tab
                    with gr.Tab("📝 System Instructions"):
                        gr.Markdown("""### Database Context
Provide information about your database to help the AI understand your data better.""")
                        
                        instructions_input = gr.Textbox(
                            label="System Instructions",
                            placeholder="""Example:
This is a textile manufacturing database with the following main tables:
- GreigeData: Contains information about greige fabric suppliers and inventory
- YarnData: Tracks yarn suppliers, types, and stock levels
- Orders: Customer orders and delivery tracking

Key business rules:
- Minimum stock level for yarn is 1000 kg
- Greige fabric lead time is 30 days
- Priority customers get 20% discount""",
                            lines=15,
                            value=load_system_instructions()
                        )
                        
                        with gr.Row():
                            save_instructions_btn = gr.Button("💾 Save Instructions", variant="primary")
                            clear_instructions_btn = gr.Button("🗑️ Clear", variant="secondary")
                        
                        instructions_status = gr.Markdown("")
                        
                        def save_instructions(text):
                            success, msg = save_system_instructions(text)
                            return msg
                        
                        save_instructions_btn.click(
                            save_instructions,
                            inputs=[instructions_input],
                            outputs=[instructions_status]
                        )
                        
                        clear_instructions_btn.click(
                            lambda: ("", "Instructions cleared"),
                            outputs=[instructions_input, instructions_status]
                        )
                    
                    # Interactive Column Training Tab
                    with gr.Tab("📊 Column Training"):
                        gr.Markdown("""### Interactive Column Training
View your database schema and add training descriptions for tables and columns.
These descriptions help the AI understand your data better.""")
                        
                        # Load schema button
                        load_schema_btn = gr.Button("📥 Load Database Schema", variant="primary", size="lg")
                        
                        with gr.Row():
                            with gr.Column(scale=1):
                                gr.Markdown("#### Select Table & Column")
                                table_dropdown = gr.Dropdown(
                                    label="Table",
                                    choices=[],
                                    interactive=True
                                )
                                column_dropdown = gr.Dropdown(
                                    label="Column",
                                    choices=[],
                                    interactive=True
                                )
                                column_type_display = gr.Textbox(
                                    label="Column Type",
                                    interactive=False,
                                    value=""
                                )
                            
                            with gr.Column(scale=2):
                                gr.Markdown("#### Training Description")
                                description_input = gr.Textbox(
                                    label="What does this column represent?",
                                    placeholder="Example: This column stores the supplier name (e.g., 'Ahmed Textile', 'XYZ Fabrics'). Used for filtering and grouping orders by supplier.",
                                    lines=4
                                )
                                unit_input = gr.Textbox(
                                    label="Unit (if applicable)",
                                    placeholder="e.g., PKR, LBS, meters, inches"
                                )
                                examples_input = gr.Textbox(
                                    label="Example Values",
                                    placeholder="e.g., Ahmed Textile, XYZ Mills, ABC Fabrics"
                                )
                                
                                with gr.Row():
                                    save_training_btn = gr.Button("💾 Save Training", variant="primary")
                                    clear_training_btn = gr.Button("🔄 Clear", variant="secondary")
                                
                                training_status = gr.Markdown("")
                        
                        gr.Markdown("---")
                        gr.Markdown("#### Current Training Data")
                        training_display = gr.Markdown("")
                        
                        # Functions for column training
                        def load_schema_for_training():
                            """Load database schema and return table names."""
                            try:
                                db = get_sql_database()
                                if not db:
                                    return (
                                        gr.Dropdown(choices=[], value=None),
                                        gr.Dropdown(choices=[], value=None),
                                        "",
                                        "❌ Database not available"
                                    )
                                
                                # Get table info
                                schema_info = db.get_table_info()
                                
                                # Parse table names from schema
                                tables = []
                                for line in schema_info.split('\n'):
                                    if 'CREATE TABLE' in line:
                                        # Extract table name
                                        parts = line.split('CREATE TABLE')[1].strip().split('(')[0].strip()
                                        # Remove schema prefix if exists
                                        table_name = parts.split('.')[-1].strip('[]')
                                        if table_name and table_name not in tables:
                                            tables.append(table_name)
                                
                                if not tables:
                                    return (
                                        gr.Dropdown(choices=[], value=None),
                                        gr.Dropdown(choices=[], value=None),
                                        "",
                                        "❌ No tables found in database"
                                    )
                                
                                return (
                                    gr.Dropdown(choices=tables, value=tables[0] if tables else None),
                                    gr.Dropdown(choices=[], value=None),
                                    "",
                                    f"✅ Loaded {len(tables)} tables"
                                )
                                
                            except Exception as e:
                                logger.error(f"Schema load error: {e}", exc_info=True)
                                return (
                                    gr.Dropdown(choices=[], value=None),
                                    gr.Dropdown(choices=[], value=None),
                                    "",
                                    f"❌ Error: {str(e)}"
                                )
                        
                        def get_columns_for_table(table_name):
                            """Get columns for selected table."""
                            if not table_name:
                                return gr.Dropdown(choices=[], value=None), "", ""
                            
                            try:
                                db = get_sql_database()
                                if not db:
                                    return gr.Dropdown(choices=[], value=None), "", "❌ Database not available"
                                
                                # Get table info
                                schema_info = db.get_table_info()
                                
                                # Parse columns for this table
                                columns = []
                                in_table = False
                                for line in schema_info.split('\n'):
                                    if f'CREATE TABLE' in line and table_name in line:
                                        in_table = True
                                        continue
                                    
                                    if in_table:
                                        if line.strip().startswith(')'):
                                            break
                                        
                                        # Extract column name and type
                                        cleaned = line.strip().strip(',').strip()
                                        if cleaned and not cleaned.startswith('PRIMARY') and not cleaned.startswith('FOREIGN'):
                                            # Remove brackets and split
                                            parts = cleaned.replace('[', '').replace(']', '').split()
                                            if len(parts) >= 2:
                                                col_name = parts[0]
                                                columns.append(col_name)
                                
                                if columns:
                                    return gr.Dropdown(choices=columns, value=columns[0]), "", f"✅ Found {len(columns)} columns"
                                else:
                                    return gr.Dropdown(choices=[], value=None), "", "❌ No columns found"
                                
                            except Exception as e:
                                logger.error(f"Column fetch error: {e}", exc_info=True)
                                return gr.Dropdown(choices=[], value=None), "", f"❌ Error: {str(e)}"
                        
                        def get_column_type(table_name, column_name):
                            """Get column type from schema."""
                            if not table_name or not column_name:
                                return ""
                            
                            try:
                                db = get_sql_database()
                                if not db:
                                    return "Unknown"
                                
                                schema_info = db.get_table_info()
                                
                                # Parse column type
                                in_table = False
                                for line in schema_info.split('\n'):
                                    if f'CREATE TABLE' in line and table_name in line:
                                        in_table = True
                                        continue
                                    
                                    if in_table:
                                        if line.strip().startswith(')'):
                                            break
                                        
                                        if column_name in line:
                                            # Extract type
                                            cleaned = line.strip().strip(',').strip()
                                            parts = cleaned.replace('[', '').replace(']', '').split()
                                            if len(parts) >= 2:
                                                return parts[1]
                                
                                return "Unknown"
                                
                            except Exception as e:
                                logger.error(f"Column type error: {e}", exc_info=True)
                                return "Error"
                        
                        def save_column_training(table, column, description, unit, examples):
                            """Save training data for a column."""
                            if not table or not column:
                                return "❌ Please select a table and column"
                            
                            if not description.strip():
                                return "❌ Please provide a description"
                            
                            try:
                                # Load current metadata
                                metadata = load_metadata()
                                
                                # Ensure table exists in metadata
                                if "tables" not in metadata:
                                    metadata["tables"] = {}
                                
                                if table not in metadata["tables"]:
                                    metadata["tables"][table] = {}
                                
                                # Save column training
                                column_data = {
                                    "description": description.strip(),
                                    "type": get_column_type(table, column),
                                    "unit": unit.strip() if unit.strip() else None,
                                    "unit_full": None,
                                    "examples": [ex.strip() for ex in examples.split(',') if ex.strip()] if examples else []
                                }
                                metadata["tables"][table][column] = column_data
                                
                                # Save metadata
                                save_metadata(metadata)
                                
                                # Track training event
                                session_tracker.track_training_event(
                                    event_type="column_metadata_updated",
                                    details={
                                        "table": table,
                                        "column": column,
                                        "description": description.strip(),
                                        "unit": unit.strip() if unit.strip() else None,
                                        "examples_count": len([ex.strip() for ex in examples.split(',') if ex.strip()] if examples else [])
                                    }
                                )
                                
                                return f"✅ Training saved for {table}.{column}"
                                
                            except Exception as e:
                                logger.error(f"Save training error: {e}", exc_info=True)
                                
                                # Track failed training attempt
                                session_tracker.track_error(
                                    error_type="column_training_save_failed",
                                    message=str(e),
                                    context={
                                        "table": table,
                                        "column": column
                                    }
                                )
                                
                                return f"❌ Error: {str(e)}"
                        
                        def display_current_training():
                            """Display current training data from metadata."""
                            try:
                                metadata = load_metadata()
                                
                                if "tables" not in metadata or not metadata["tables"]:
                                    return "No training data yet. Start by loading the schema and adding descriptions!"
                                
                                output = "### Trained Columns\n\n"
                                
                                for table_name, table_data in metadata["tables"].items():
                                    output += f"#### 📋 {table_name}\n\n"
                                    
                                    # Handle both old format (columns as dict) and new format (description + columns)
                                    columns = table_data if not isinstance(table_data.get('columns'), dict) else table_data.get('columns', {})
                                    
                                    for col_name, col_data in columns.items():
                                        # Skip non-column metadata like 'description'
                                        if col_name in ['description', 'business_terms', 'common_queries']:
                                            continue
                                        
                                        # Handle both string and dict formats
                                        if isinstance(col_data, str):
                                            output += f"**{col_name}**\n"
                                            output += f"- *Description:* {col_data}\n\n"
                                        elif isinstance(col_data, dict):
                                            col_type = col_data.get('type', 'Unknown')
                                            output += f"**{col_name}** ({col_type})\n"
                                            output += f"- *Description:* {col_data.get('description', 'N/A')}\n"
                                            
                                            if col_data.get('unit'):
                                                output += f"- *Unit:* {col_data.get('unit')}\n"
                                            
                                            if col_data.get('examples'):
                                                examples_str = ', '.join(str(ex) for ex in col_data['examples'][:3])
                                                output += f"- *Examples:* {examples_str}\n"
                                            
                                            output += "\n"
                                    
                                    output += "---\n\n"
                                
                                return output
                                
                            except Exception as e:
                                logger.error(f"Display training error: {e}", exc_info=True)
                                return f"❌ Error loading training data: {str(e)}"
                        
                        # Event handlers for column training
                        load_schema_btn.click(
                            load_schema_for_training,
                            outputs=[table_dropdown, column_dropdown, column_type_display, training_status]
                        )
                        
                        table_dropdown.change(
                            get_columns_for_table,
                            inputs=[table_dropdown],
                            outputs=[column_dropdown, column_type_display, training_status]
                        )
                        
                        column_dropdown.change(
                            get_column_type,
                            inputs=[table_dropdown, column_dropdown],
                            outputs=[column_type_display]
                        )
                        
                        save_training_btn.click(
                            save_column_training,
                            inputs=[table_dropdown, column_dropdown, description_input, unit_input, examples_input],
                            outputs=[training_status]
                        ).then(
                            display_current_training,
                            outputs=[training_display]
                        )
                        
                        clear_training_btn.click(
                            lambda: ("", "", ""),
                            outputs=[description_input, unit_input, examples_input]
                        )
                        
                        # Load training data on tab open
                        demo.load(
                            display_current_training,
                            outputs=[training_display]
                        )
                    
                    # Schema Analysis Tab
                    with gr.Tab("🔍 Auto-Analyze Schema"):
                        gr.Markdown("""### Automatic Schema Analysis
Let the AI analyze your database schema and generate training data automatically.""")
                        
                        analyze_btn = gr.Button("🚀 Analyze Database Schema", variant="primary", size="lg")
                        analysis_output = gr.Markdown("")
                        
                        def analyze_schema():
                            """Analyze database schema automatically."""
                            try:
                                db = get_sql_database()
                                if not db:
                                    return "❌ Database not available"
                                
                                schema = db.get_table_info()
                                
                                # Use LLM to analyze schema
                                global current_llm, current_provider
                                if current_llm is None:
                                    config = load_config()
                                    llm_config = config.get('llm', {})
                                    provider_name = llm_config.get('provider', 'openai')
                                    model = llm_config.get('model', 'gpt-4o-mini')
                                    current_provider = create_provider(provider_name)
                                    current_llm = current_provider.get_llm(model, 0.3, 2000)
                                
                                prompt = f"""Analyze this database schema and provide:
1. Overview of what this database is for
2. Key tables and their purposes
3. Important relationships between tables
4. Common query patterns that would be useful
5. Suggested system instructions for an AI assistant

Schema:
{schema}

Provide a comprehensive analysis:"""
                                
                                response = current_llm.invoke(prompt)
                                analysis = response.content if hasattr(response, 'content') else str(response)
                                
                                # Save as system instructions
                                save_system_instructions(f"Auto-generated analysis:\n\n{analysis}")
                                
                                return f"## ✅ Analysis Complete\n\n{analysis}\n\n---\n\n*Analysis saved to system instructions.*"
                                
                            except Exception as e:
                                logger.error(f"Schema analysis error: {e}", exc_info=True)
                                return f"❌ Error: {str(e)}"
                        
                        analyze_btn.click(
                            analyze_schema,
                            outputs=[analysis_output]
                        )
                    
                    # Example Queries Tab
                    with gr.Tab("📚 Auto-Generate Examples"):
                        gr.Markdown("""### Intelligent Query Generator
Automatically generate relevant example queries by analyzing your database schema.""")
                        
                        generate_btn = gr.Button("🤖 Generate Example Queries", variant="primary", size="lg")
                        examples_output = gr.Markdown("")
                        
                        def generate_example_queries():
                            """Auto-generate example queries based on schema analysis."""
                            try:
                                db = get_sql_database()
                                if not db:
                                    return "❌ Database not available"
                                
                                schema = db.get_table_info()
                                
                                # Use LLM to generate example queries
                                global current_llm, current_provider
                                if current_llm is None:
                                    config = load_config()
                                    llm_config = config.get('llm', {})
                                    provider_name = llm_config.get('provider', 'openai')
                                    model = llm_config.get('model', 'gpt-4o-mini')
                                    current_provider = create_provider(provider_name)
                                    current_llm = current_provider.get_llm(model, 0.3, 2000)
                                
                                prompt = f"""Analyze this database schema and generate 8-10 practical example questions that users would commonly ask.

Schema:
{schema}

For each question, provide:
1. A natural language question
2. The SQL Server query that answers it

Format each example as:
**Q: [Natural language question]**
```sql
[SQL Server query]
```

Focus on:
- Common business queries (totals, counts, summaries)
- Date-based analysis (monthly, yearly trends)
- Comparisons and rankings
- Aggregations by category
- Inventory/stock queries
- Supplier/vendor analysis

Generate the examples now:"""
                                
                                response = current_llm.invoke(prompt)
                                examples = response.content if hasattr(response, 'content') else str(response)
                                
                                # Save to file
                                examples_file = Path(__file__).parent.parent / "auto_generated_examples.md"
                                with open(examples_file, 'w') as f:
                                    f.write(examples)
                                
                                return f"## ✅ Examples Generated\n\n{examples}\n\n---\n\n*Examples saved to auto_generated_examples.md*"
                                
                            except Exception as e:
                                logger.error(f"Example generation error: {e}", exc_info=True)
                                return f"❌ Error: {str(e)}"
                        
                        generate_btn.click(
                            generate_example_queries,
                            outputs=[examples_output]
                        )
            
            # Developer Tools Tab (NEW)
            with gr.Tab("🔬 Developer Tools"):
                gr.Markdown("## Session Intelligence & Observability")
                gr.Markdown("Control what gets tracked and export session data for Copilot analysis.")
                
                with gr.Row():
                    with gr.Column(scale=1):
                        gr.Markdown("### 📊 Current Session")
                        
                        session_summary = gr.Markdown("Loading session data...")
                        refresh_summary_btn = gr.Button("🔄 Refresh Summary", size="sm")
                        
                        def get_current_session_summary():
                            """Get current session summary."""
                            try:
                                summary = session_tracker.get_session_summary()
                                
                                avg_time = summary.get('avg_response_time', 0)
                                avg_time_str = f"{avg_time:.0f}ms" if avg_time else 'N/A'
                                
                                output = f"""
**Session ID:** `{summary['session_id']}`  
**Duration:** {summary['duration_minutes']:.1f} minutes  
**Total Queries:** {summary['total_queries']}  
**Successful:** {summary['successful_queries']} ✅  
**Failed:** {summary['failed_queries']} ❌  
**Success Rate:** {summary['success_rate']:.1f}%  
**Avg Response Time:** {avg_time_str}  
**Training Events:** {summary['training_events']}  
**Errors:** {summary['errors']}  
"""
                                
                                recommendations = session_tracker._generate_recommendations()
                                if recommendations:
                                    output += "\n### 💡 Recommendations\n"
                                    for rec in recommendations:
                                        output += f"- {rec}\n"
                                
                                return output
                            except Exception as e:
                                return f"❌ Error: {str(e)}"
                        
                        refresh_summary_btn.click(get_current_session_summary, outputs=[session_summary])
                        
                        # Export button
                        gr.Markdown("---")
                        export_btn = gr.Button("📤 Export Session for Copilot", variant="primary", size="lg")
                        export_status = gr.Markdown("")
                        export_file_download = gr.File(label="Download Report", visible=False)
                        
                        def export_session_report():
                            """Export complete session for Copilot analysis."""
                            try:
                                report_path = session_tracker.export_for_copilot()
                                
                                if report_path:
                                    # Extract just the relative path for git
                                    relative_path = str(Path(report_path).relative_to(Path.cwd()))
                                    git_path = relative_path.replace("\\", "/")  # Windows to Unix path
                                    
                                    instructions = f"""✅ **Report Exported Successfully!**

File: `{report_path}`

### 📤 To Share with Copilot:

**Copy and run these commands:**

```bash
git add {git_path}
git commit -m "Add session report for analysis"
git push
```

Then tell me it's pushed and I'll analyze it!
"""
                                    return (
                                        instructions,
                                        report_path,
                                        gr.update(visible=True)
                                    )
                                else:
                                    return "❌ Export failed", None, gr.update(visible=False)
                            except Exception as e:
                                return f"❌ Error: {str(e)}", None, gr.update(visible=False)
                        
                        export_btn.click(export_session_report, outputs=[export_status, export_file_download, export_file_download])
                    
                    with gr.Column(scale=1):
                        gr.Markdown("### ⚙️ Observability Settings")
                        gr.Markdown("**Tier 1** (Always On): Essential metrics  \n**Tier 2** (Developer Mode): Detailed debugging")
                        
                        # Configuration controls
                        tier1_checkbox = gr.Checkbox(label="✅ Tier 1: Essential Metrics", value=True, interactive=False)
                        
                        gr.Markdown("---")
                        tier2_checkbox = gr.Checkbox(label="🔧 Tier 2: Developer Mode", value=False, info="Detailed debugging")
                        capture_llm_prompts = gr.Checkbox(label="📝 Capture Full LLM Prompts", value=False, info="⚠️ Very detailed")
                        capture_reasoning = gr.Checkbox(label="🧠 Capture Reasoning Chain", value=True, info="✅ Recommended")
                        capture_sample_data = gr.Checkbox(label="📊 Capture Sample Data", value=False, info="⚠️ Privacy concern")
                        
                        gr.Markdown("---")
                        save_config_btn = gr.Button("💾 Save Configuration", variant="secondary")
                        config_status = gr.Markdown("")
                        
                        def save_configuration(tier2, llm_prompts, reasoning, sample_data):
                            """Save observability configuration."""
                            try:
                                new_config = session_tracker.config.copy()
                                new_config.update({
                                    "tier2_enabled": tier2,
                                    "capture_llm_prompts": llm_prompts,
                                    "capture_reasoning_chain": reasoning,
                                    "capture_sample_data": sample_data
                                })
                                session_tracker.save_config(new_config)
                                
                                status = "✅ **Configuration Saved!**\n\n"
                                status += "🔧 Developer Mode ENABLED" if tier2 else "📊 Essential mode only"
                                return status
                            except Exception as e:
                                return f"❌ Error: {str(e)}"
                        
                        save_config_btn.click(
                            save_configuration,
                            inputs=[tier2_checkbox, capture_llm_prompts, capture_reasoning, capture_sample_data],
                            outputs=[config_status]
                        )
                        
                        # Guidance
                        gr.Markdown("---")
                        gr.Markdown("""
**Enable Developer Mode when:**
- ❌ Wrong results  
- 🐌 Slow performance  
- 🤔 Need to see AI reasoning  

**Export for Copilot when:**
- 💬 Asking for help  
- 🐛 Complex bugs  
""")
                
                # Load session summary on page load
                demo.load(
                    get_current_session_summary,
                    outputs=[session_summary]
                )

            # Diagnostics Tab
            with gr.Tab("🔍 Diagnostics"):
                gr.Markdown("## System Diagnostics")
                gr.Markdown("Collect system information, configuration, and logs for troubleshooting.")
                
                collect_btn = gr.Button("Collect Diagnostics", variant="primary")
                download_file = gr.File(label="Download Diagnostics File")
                
                collect_btn.click(
                    collect_and_download_diagnostics,
                    outputs=[download_file]
                )
        
        gr.Markdown("---")
        gr.Markdown("💡 **Tip:** Use the Diagnostics tab to collect logs if you encounter any issues.")
    
    return demo

if __name__ == "__main__":
    demo = build_ui()
    demo.launch()
