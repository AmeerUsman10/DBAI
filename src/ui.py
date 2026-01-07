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
from datetime import datetime
import gradio as gr
import yaml
from pathlib import Path
from dotenv import load_dotenv, set_key

from src.providers import create_provider
from src.database import reload_engine, test_connection, get_engine, run_query, get_sql_database, load_metadata, save_metadata
from src.llm import make_sql_chain, make_presentation_chain, make_describe_chain, extract_sql_from_response, validate_sql
from src.telemetry import TelemetryLogger
from src.uploader import process_excel_files, check_table_exists, import_dataframe_to_db
from src.trainer import save_training_example
from src.diagnostics import collect_diagnostics
from src.clarity import analyze_query_clarity, needs_clarification
from src.learnings import save_learning, get_learning_stats
from src.quick_training import add_training_rule, get_training_stats, format_rules_display, update_rule, delete_rule, load_training_rules
from src.session_tracker import get_session_tracker, reset_session_tracker
from src.query_classifier import classify_query, needs_movement_clarification, get_clarification_for_classification
from src.query_templates import generate_sql_from_template
from src.feedback import save_feedback, get_feedback_statistics, format_feedback_for_display, get_recent_feedback, format_recent_feedback, get_rule_suggestions
from src.dev_notes import load_notes, save_notes, add_quick_note, get_notes_preview
from src.query_optimizer import (
    cache_query_result, get_cached_result, cache_sql_generation, get_cached_sql,
    get_cache_stats, clear_expired_cache, clear_all_cache
)
from src.custom_personas import (
    load_custom_personas, save_custom_persona, delete_custom_persona,
    get_custom_persona, list_custom_personas, update_persona_stats,
    get_persona_effectiveness_ranking, generate_persona_prompt
)
from src.bookmarks import (
    load_bookmarks, save_bookmark, get_bookmark, update_bookmark_usage,
    delete_bookmark, get_bookmarks_by_folder, get_most_used_bookmarks, search_bookmarks
)

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
auto_chart_enabled = False  # Auto-chart visualization toggle

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


def get_all_personas() -> list:
    """Get all available personas (built-in + custom)."""
    try:
        # Start with built-in personas
        personas = [(p["name"], k) for k, p in PERSONAS.items()]
        
        # Add custom personas
        custom = list_custom_personas()
        for cp in custom:
            personas.append((f"🎭 {cp['name']}", cp['id']))
        
        return personas
    except Exception as e:
        logger.error(f"Error loading personas: {e}")
        return [(p["name"], k) for k, p in PERSONAS.items()]


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

def is_conversational_query(question: str, last_question: str = None) -> bool:
    """
    Detect if user is asking a conversational question vs a data query.
    
    Returns True if conversational (no SQL needed), False if data query.
    """
    question_lower = question.lower()
    
    # Strong conversational indicators
    conversational_patterns = [
        r'\b(the above|these results?|that data|this table|previous)\b',
        r'\b(why|how come|explain|what does (this|that|it) mean)\b',
        r'\b(different|same|changed|not matching)\b',
        r'\b(you (said|showed|returned|gave))\b',
        r'\b(earlier|before|last time)\b',
        r'^(why|how|what) (is|are|did|does)',
        r'\btell me (about|why|how)\b'
    ]
    
    import re
    for pattern in conversational_patterns:
        if re.search(pattern, question_lower):
            return True
    
    # If very short and no data keywords, likely conversational
    if len(question.split()) < 5:
        data_keywords = ['total', 'sum', 'count', 'show', 'list', 'get', 'find', 'top', 'supplier', 'yarn', 'greige']
        has_data_keyword = any(keyword in question_lower for keyword in data_keywords)
        if not has_data_keyword:
            return True
    
    return False


def format_result_as_table(rows, columns):
    """Format query result as markdown table."""
    if not rows or not columns:
        return "No results found."
    
    # Create markdown table
    table = "| " + " | ".join(columns) + " |\n"
    table += "| " + " | ".join(["---"] * len(columns)) + " |\n"
    
    for row in rows[:100]:  # Limit to 100 rows for display
        table += "| " + " | ".join(str(val) if val is not None else "" for val in row) + " |\n"
    
    if len(rows) > 100:
        table += f"\n*Showing first 100 of {len(rows)} results*"
    
    return table


def create_simple_chart(rows, columns):
    """
    Create a simple text-based chart for numeric data.
    Detects numeric columns and creates a basic bar chart visualization.
    """
    try:
        if not rows or len(rows) > 50:  # Only chart small datasets
            return None
        
        # Find numeric columns
        numeric_cols = []
        for i, col in enumerate(columns):
            try:
                # Check if column has numeric values
                sample_values = [row[i] for row in rows[:5] if row[i] is not None]
                if sample_values and all(isinstance(v, (int, float)) or str(v).replace('.','').replace('-','').isdigit() for v in sample_values):
                    numeric_cols.append(i)
            except:
                continue
        
        if not numeric_cols or len(numeric_cols) == 0:
            return None
        
        # Simple text-based bar chart
        label_col = 0  # First column as label
        value_col = numeric_cols[0]  # First numeric column as value
        
        chart = "\n### 📊 Quick Visualization\n\n"
        chart += f"**{columns[label_col]}** vs **{columns[value_col]}**\n\n"
        
        # Get data
        data_points = []
        for row in rows[:10]:  # Max 10 bars
            label = str(row[label_col])[:20] if row[label_col] else "Unknown"
            try:
                value = float(row[value_col]) if row[value_col] else 0
                data_points.append((label, value))
            except:
                continue
        
        if not data_points:
            return None
        
        # Find max value for scaling
        max_val = max(v for _, v in data_points)
        if max_val == 0:
            return None
        
        # Create horizontal bar chart
        chart += "```\n"
        for label, value in data_points:
            bar_length = int((value / max_val) * 40)  # Scale to 40 chars max
            bar = "█" * bar_length
            chart += f"{label:20} {bar} {value:,.0f}\n"
        chart += "```\n"
        
        chart += "\n*Auto-generated chart (first 10 rows)*\n"
        
        return chart
        
    except Exception as e:
        logger.debug(f"Chart generation skipped: {e}")
        return None


def chat_query(question: str, history: List, persona: str = "default") -> Tuple[str, List, str, str]:
    """
    Process a natural language query with clarity checking and learning.
    
    Args:
        question: User's question
        history: Chat history
        persona: Selected persona
        
    Returns:
        Tuple of (empty_string, updated_history, message_id, response_text)
    """
    global current_llm, current_provider, session_tokens, pending_clarification, session_tracker, last_query_info, last_query_result_data
    
    if not question.strip():
        return "", history, "", ""
    
    # Generate unique message ID for feedback tracking
    import uuid
    message_id = str(uuid.uuid4())[:8]
    
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
    
    # Resolve persona overlay for prompt shaping
    persona_overlay = ""
    try:
        if persona in PERSONAS:
            persona_overlay = PERSONAS[persona]["prompt"]
        else:
            cp = get_custom_persona(persona)
            if cp:
                persona_overlay = generate_persona_prompt(cp)
    except Exception:
        persona_overlay = ""

    # CLASSIFY FIRST to detect breakdown/template potential (always needed)
    classification = classify_query(question)
    logger.info(f"Query classified as: {classification['type']} (confidence: {classification['confidence']}%)")
    
    # Analyze query clarity (skip if already clarified above)
    if not pending_clarification.get("original_query"):
        
        # Check if this is a conversational query (not a data request)
        is_conversation = is_conversational_query(question, last_query_info.get("question"))

        if is_conversation:
            # Handle as conversation - use LLM directly without SQL
            try:
                conversation_prompt = f"""The user is asking a conversational question about previous results or context.

User's question: "{question}"

Previous query: "{last_query_info.get('question', 'None')}"
Previous result (first 500 chars): "{str(last_query_info.get('result', ''))[:500]}"

Respond conversationally and naturally. If they're comparing results or asking for clarification, explain based on the context shown above. Do NOT generate SQL. Just have a helpful conversation.

Your response:"""
                
                conversation_response = current_llm.invoke(conversation_prompt)
                response_text = conversation_response.content if hasattr(conversation_response, 'content') else str(conversation_response)
                
                # Extract tokens
                conv_tokens = extract_token_usage(conversation_response)
                session_tokens['prompt'] += conv_tokens['prompt_tokens']
                session_tokens['completion'] += conv_tokens['completion_tokens']
                session_tokens['total'] += conv_tokens['total_tokens']
                
                response = f"{response_text}\n\n<sub>💬 Conversational response · 🔹 Tokens: {conv_tokens['total_tokens']} · Session: {session_tokens['total']:,}</sub>"
                
                # Track conversation
                total_time_ms = int((time.time() - start_time) * 1000)
                session_tracker.track_query(
                    user_question=question,
                    clarity_analysis=None,
                    llm_interaction={"provider": provider_name, "model": model, "type": "conversation", "tokens": conv_tokens},
                    execution=None,
                    response={"type": "conversation", "text": response},
                    performance={"total_time_ms": total_time_ms, "tokens": conv_tokens},
                    error=None
                )
                
                history.append({"role": "user", "content": question})
                history.append({"role": "assistant", "content": response})
                return "", history, message_id, response
                
            except Exception as e:
                logger.error(f"Conversation handling error: {e}")
                # Fall through to normal query handling if conversation fails
        
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
                
                return "", history, message_id, response
    
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
        
        # CHECK CACHE FIRST - Skip for faster responses and token savings
        cached_result = get_cached_result(question, fuzzy_match=True)
        if cached_result:
            sql_query, result, cache_metadata = cached_result
            logger.info(f"⚡ CACHE HIT! Skipping SQL generation and execution")
            
            # Format cached result
            if result and 'rows' in result and 'columns' in result:
                response = f"### Query Result (from cache)\n\n"
                response += format_result_as_table(result['rows'], result['columns'])
                response += f"\n\n<sub>⚡ Loaded from cache · 0 tokens used · Saved {cache_metadata.get('tokens_saved', 50)} tokens</sub>"
            else:
                response = str(result)
                response += "\n\n<sub>⚡ Loaded from cache · 0 tokens used</sub>"
            
            # Track cache hit
            session_tracker.track_query(
                user_question=question,
                clarity_analysis=None,
                llm_interaction={"provider": "cache", "type": "cache_hit", "tokens": {"total_tokens": 0}},
                execution={"method": "cache", "success": True},
                response={"type": "cached", "text": response},
                performance={"total_time_ms": int((time.time() - start_time) * 1000), "tokens": {"total_tokens": 0}},
                error=None
            )

            # Append cache stats footer
            try:
                stats = get_cache_stats() or {}
                rc = stats.get("result_cache", {})
                sc = stats.get("sql_cache", {})
                size_mb = stats.get("cache_size_mb", 0)
                response += (
                    f"\n\n<sub>🗄️ Cache: results={rc.get('total_entries',0)}, hits={rc.get('total_hits',0)} · "
                    f"sql={sc.get('total_entries',0)}, reuses={sc.get('total_reuses',0)} · size={size_mb:.2f}MB</sub>"
                )
            except Exception:
                pass

            # Audit event for cache hit
            try:
                TelemetryLogger.log_audit_event({
                    "session_id": session_tracker.session_id,
                    "message_id": message_id,
                    "question": question,
                    "provider": "cache",
                    "model": "n/a",
                    "generation_method": "cache",
                    "tokens_total": 0,
                    "sql_query": sql_query,
                    "success": True,
                    "execution_time_ms": int((time.time() - start_time) * 1000),
                    "cache_hit": True,
                    "safety_blocked": False
                })
            except Exception:
                pass
            
            history.append({"role": "user", "content": question})
            history.append({"role": "assistant", "content": response})
            return "", history, message_id, response
        
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
            
            return "", history, message_id, response
        
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
            sql_response_obj = sql_chain({"question": question, "persona_overlay": persona_overlay, "message_id": message_id})
            
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

        # SAFETY CHECK: Validate SQL before execution
        is_valid, safety_msg = validate_sql(sql_query)
        if not is_valid:
            # Prepare blocked response with guidance
            response = (
                f"❌ Query blocked by safety guardrails: {safety_msg}\n\n"
                "Only single-statement SELECT queries are allowed. "
                "Please rephrase your request or use a safer query." 
            )

            # Track attempted execution (blocked)
            execution_data = {
                "sql_query": sql_query,
                "success": False,
                "blocked_by_safety": True,
                "reason": safety_msg,
                "execution_time_ms": 0
            }

            # Add generation method indicator
            method_icon = "⚡" if generation_method == "template" else "🤖"
            method_text = "Template" if generation_method == "template" else "LLM"
            response += f"\n\n<sub>{method_icon} Generated via {method_text} · 🚫 Safety blocked</sub>"

            # Track lifecycle and return
            total_time_ms = int((time.time() - start_time) * 1000)
            session_tracker.track_query(
                user_question=question,
                clarity_analysis=clarity_data,
                llm_interaction={
                    "provider": provider_name if generation_method == "llm" else "template",
                    "model": model if generation_method == "llm" else "rule-based",
                    "temperature": temperature,
                    "sql_generated": sql_query,
                    "tokens": response_tokens,
                    "generation_method": generation_method
                },
                execution=execution_data,
                response={"type": "error", "text": response, "length_chars": len(response)},
                performance={
                    "total_time_ms": total_time_ms,
                    "query_time_ms": 0,
                    "tokens": response_tokens
                },
                error={"type": "SafetyBlocked", "message": safety_msg}
            )

            history.append({"role": "user", "content": question})
            history.append({"role": "assistant", "content": response})
            return "", history, message_id, response
        
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
                        
                        # Create professional HTML table with styling
                        response += '<div style="overflow-x: auto; max-height: 600px;">'
                        response += '<table style="width: 100%; border-collapse: collapse; font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, sans-serif; font-size: 14px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">'
                        
                        # Header with gradient background
                        response += '<thead style="position: sticky; top: 0; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white;">'
                        response += '<tr>'
                        for col in result['columns']:
                            response += f'<th style="padding: 14px 16px; text-align: left; font-weight: 600; border-bottom: 3px solid #5568d3; text-transform: uppercase; font-size: 12px; letter-spacing: 0.5px;">{col}</th>'
                        response += '</tr>'
                        response += '</thead>'
                        
                        # Body with alternating rows
                        response += '<tbody>'
                        for idx, row in enumerate(display_rows[:100]):  # Show up to 100 rows
                            bg_color = "#f8f9fa" if idx % 2 == 0 else "#ffffff"
                            response += f'<tr style="background-color: {bg_color}; transition: background-color 0.2s;">'
                            for val in row:
                                # Format numbers with commas
                                if isinstance(val, (int, float)):
                                    formatted_val = f"{val:,.2f}" if isinstance(val, float) else f"{val:,}"
                                else:
                                    formatted_val = str(val) if val is not None else ""
                                response += f'<td style="padding: 12px 16px; border-bottom: 1px solid #e9ecef; color: #212529;">{formatted_val}</td>'
                            response += '</tr>'
                        response += '</tbody>'
                        response += '</table>'
                        response += '</div>\n'
                        
                        # Add auto-chart if enabled and data is suitable
                        global auto_chart_enabled
                        if auto_chart_enabled and len(result['rows']) <= 50:
                            chart = create_simple_chart(result['rows'], result['columns'])
                            if chart:
                                response += f"\n{chart}\n"
                        
                        if len(result['rows']) > 100:
                            response += f"\n\n*Showing first 100 of {len(result['rows']):,} rows*"
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
        
        # Append cache stats footer for non-cache path
        try:
            stats = get_cache_stats() or {}
            rc = stats.get("result_cache", {})
            sc = stats.get("sql_cache", {})
            size_mb = stats.get("cache_size_mb", 0)
            response += (
                f"\n\n<sub>🗄️ Cache: results={rc.get('total_entries',0)}, hits={rc.get('total_hits',0)} · "
                f"sql={sc.get('total_entries',0)}, reuses={sc.get('total_reuses',0)} · size={size_mb:.2f}MB</sub>"
            )
        except Exception:
            pass

        # LOG: Final response sent to user
        logger.info(f"RESPONSE SENT: {len(response)} chars | Success: {success} | Tokens: {response_tokens.get('total_tokens', 0)}")
        logger.debug(f"RESPONSE PREVIEW: {response[:200]}")
        
        # CACHE SUCCESSFUL QUERIES for future reuse
        if success and result:
            try:
                cache_query_result(
                    question=question,
                    sql=sql_query,
                    result=result,
                    metadata={
                        "generation_method": generation_method,
                        "tokens_used": response_tokens.get('total_tokens', 0),
                        "tokens_saved": response_tokens.get('total_tokens', 50),  # Estimated savings on reuse
                        "execution_time_ms": execution_data.get("execution_time_ms", 0) if execution_data else 0
                    }
                )
                logger.info(f"💾 Cached query result for future reuse")
            except Exception as e:
                logger.warning(f"Failed to cache result: {e}")
        
        # Save last query info for live training mode corrections
        last_query_info = {
            "message_id": message_id,
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

        # Update persona stats if custom persona in use
        try:
            if persona not in PERSONAS:
                tokens_total = response_tokens.get("total_tokens", 0)
                update_persona_stats(persona_id=persona, success=bool(success), tokens=tokens_total)
        except Exception:
            pass
        
        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": response})

        # Audit event for normal execution
        try:
            TelemetryLogger.log_audit_event({
                "session_id": session_tracker.session_id,
                "message_id": message_id,
                "question": question,
                "provider": provider_name if generation_method == "llm" else "template",
                "model": model if generation_method == "llm" else "rule-based",
                "generation_method": generation_method,
                "tokens_total": response_tokens.get("total_tokens", 0),
                "sql_query": sql_query,
                "success": bool(success),
                "execution_time_ms": execution_data.get("execution_time_ms", 0) if execution_data else 0,
                "cache_hit": False,
                "safety_blocked": False
            })
        except Exception:
            pass
        return "", history, message_id, response
        
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
        return "", history, message_id, response

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
    
    with gr.Blocks(title="DBAI - Database AI Assistant") as demo:
        gr.Markdown("# 🤖 DBAI - Database AI Assistant")
        gr.Markdown("Ask questions about your database in natural language!")
        
        with gr.Tabs():
            # Chat Tab - Premium Design
            with gr.Tab("💬 Chat"):
                # Premium controls bar
                with gr.Row():
                    with gr.Column(scale=2):
                        persona_selector = gr.Dropdown(
                            choices=get_all_personas(),
                            value="default",
                            label="🎭 AI Persona",
                            info="Select response style",
                            container=True
                        )
                    with gr.Column(scale=2):
                        auto_chart_checkbox = gr.Checkbox(
                            label="📊 Auto-visualize numeric data",
                            value=False,
                            container=True
                        )
                    with gr.Column(scale=1):
                        export_csv_btn = gr.DownloadButton(
                            "📥 Export",
                            variant="secondary",
                            size="lg"
                        )
                
                # Main chat area
                chatbot = gr.Chatbot(
                    height=500,
                    label="",
                    show_label=False,
                    avatar_images=(None, "🤖")
                )
                
                # Input area with send button
                with gr.Row():
                    question_input = gr.Textbox(
                        placeholder="Ask anything about your database... (e.g., 'Show top 10 suppliers by revenue')",
                        label="",
                        show_label=False,
                        scale=5,
                        container=False,
                        lines=1
                    )
                    send_stop_btn = gr.Button("Send ▶", variant="primary", scale=1, size="lg")
                
                # Secondary controls
                with gr.Row():
                    clear_btn = gr.Button("🗑️ Clear Chat", size="sm", variant="secondary", scale=1)
                
                # Feedback controls
                gr.Markdown("### Rate the last response")
                with gr.Row():
                    thumbs_up_btn = gr.Button("👍 Helpful", size="sm", variant="secondary", scale=1)
                    thumbs_down_btn = gr.Button("👎 Not helpful", size="sm", variant="secondary", scale=1)
                    copy_response_btn = gr.Button("📋 Copy Response", size="sm", variant="secondary", scale=1)
                
                feedback_comment = gr.Textbox(
                    placeholder="What could be improved? (optional)",
                    label="Additional Feedback",
                    lines=2,
                    visible=False
                )
                submit_feedback_btn = gr.Button("Submit Feedback", visible=False, variant="primary", size="sm")
                feedback_status = gr.Markdown("")
                
                # Query event tracking and state
                is_running = gr.State(False)
                current_message_id = gr.State("")
                last_response_text = gr.State("")
                
                # Handle button click
                send_stop_btn.click(
                    lambda: (gr.update(value="⏹ Stop", variant="stop"), True),
                    outputs=[send_stop_btn, is_running]
                ).then(
                    chat_query,
                    inputs=[question_input, chatbot, persona_selector],
                    outputs=[question_input, chatbot, current_message_id, last_response_text]
                ).then(
                    lambda: (False, gr.update(value="Send ▶", variant="primary")),
                    outputs=[is_running, send_stop_btn]
                )
                
                question_input.submit(
                    lambda: (gr.update(value="⏹ Stop", variant="stop"), True),
                    outputs=[send_stop_btn, is_running]
                ).then(
                    chat_query,
                    inputs=[question_input, chatbot, persona_selector],
                    outputs=[question_input, chatbot, current_message_id, last_response_text]
                ).then(
                    lambda: (False, gr.update(value="Send ▶", variant="primary")),
                    outputs=[is_running, send_stop_btn]
                )
                
                clear_btn.click(lambda: [], outputs=chatbot)
                
                # Export CSV button
                export_csv_btn.click(
                    fn=export_to_csv,
                    outputs=export_csv_btn
                )
                
                # Auto-chart Toggle
                def toggle_auto_chart(enabled):
                    """Toggle auto-chart generation."""
                    global auto_chart_enabled
                    auto_chart_enabled = enabled
                    return None
                
                auto_chart_checkbox.change(
                    toggle_auto_chart,
                    inputs=[auto_chart_checkbox],
                    outputs=[]
                )
                
                # Feedback event handlers
                def handle_thumbs_up(msg_id):
                    """Handle thumbs up feedback."""
                    if not msg_id or msg_id == "":
                        return "⚠️ Please send a query first before providing feedback."
                    
                    try:
                        # Get query info from last_query_info
                        question = last_query_info.get("question", "")
                        sql = last_query_info.get("sql", "")
                        response = last_query_info.get("result", "")
                        session_id = session_tracker.session_id if session_tracker else None
                        
                        # Save feedback
                        save_feedback(
                            message_id=msg_id,
                            feedback_type="thumbs_up",
                            question=question,
                            sql_query=sql,
                            response=response,
                            session_id=session_id
                        )
                        
                        # Track in session
                        if session_tracker:
                            session_tracker.track_training_event(
                                event_type="positive_feedback",
                                details={"message_id": msg_id}
                            )
                        
                        return "✅ Thanks for your feedback! This helps improve future responses."
                    except Exception as e:
                        logger.error(f"Error saving thumbs up: {e}")
                        return f"❌ Error saving feedback: {str(e)}"
                
                def handle_thumbs_down(msg_id):
                    """Show feedback comment field on thumbs down."""
                    if not msg_id or msg_id == "":
                        return "⚠️ Please send a query first.", gr.update(visible=False), gr.update(visible=False)
                    
                    return "👎 Please tell us what was wrong so we can improve:", gr.update(visible=True), gr.update(visible=True)
                
                def submit_detailed_feedback(msg_id, feedback_text):
                    """Submit detailed negative feedback."""
                    if not msg_id or msg_id == "":
                        return "⚠️ Please send a query first before providing feedback."
                    
                    try:
                        # Get query info
                        question = last_query_info.get("question", "")
                        sql = last_query_info.get("sql", "")
                        response = last_query_info.get("result", "")
                        session_id = session_tracker.session_id if session_tracker else None
                        
                        # Save feedback
                        save_feedback(
                            message_id=msg_id,
                            feedback_type="thumbs_down",
                            question=question,
                            sql_query=sql,
                            response=response,
                            feedback_text=feedback_text,
                            session_id=session_id
                        )
                        
                        # Track in session
                        if session_tracker:
                            session_tracker.track_training_event(
                                event_type="negative_feedback",
                                details={"message_id": msg_id, "feedback": feedback_text}
                            )
                        
                        # If feedback provided, create training rule
                        if feedback_text and feedback_text.strip():
                            rule = f"CORRECTION for '{question}': {feedback_text}"
                            add_training_rule(rule)
                            return "✅ Feedback submitted and training rule created! This will help improve similar queries."
                        else:
                            return "✅ Feedback submitted. Thanks for helping us improve!"
                            
                    except Exception as e:
                        logger.error(f"Error saving detailed feedback: {e}")
                        return f"❌ Error saving feedback: {str(e)}"
                
                def copy_to_clipboard(response_text):
                    """Copy response to clipboard (placeholder - actual implementation would need JS)."""
                    if not response_text:
                        return "⚠️ No response to copy."
                    return "📋 Response copied! (use Ctrl+C to copy from the chat)"
                
                # Wire feedback buttons
                thumbs_up_btn.click(
                    handle_thumbs_up,
                    inputs=[current_message_id],
                    outputs=[feedback_status]
                )
                
                thumbs_down_btn.click(
                    handle_thumbs_down,
                    inputs=[current_message_id],
                    outputs=[feedback_status, feedback_comment, submit_feedback_btn]
                )
                
                submit_feedback_btn.click(
                    submit_detailed_feedback,
                    inputs=[current_message_id, feedback_comment],
                    outputs=[feedback_status]
                ).then(
                    lambda: (gr.update(value="", visible=False), gr.update(visible=False)),
                    outputs=[feedback_comment, submit_feedback_btn]
                )
                
                copy_response_btn.click(
                    copy_to_clipboard,
                    inputs=[last_response_text],
                    outputs=[feedback_status]
                )
            
            # Settings Tab
            with gr.Tab("⚙️ Settings"):
                gr.Markdown("## LLM Provider Settings")
                
                with gr.Row():
                    provider_dropdown = gr.Dropdown(
                        choices=["openai", "groq"],
                        label="Provider",
                        value="openai",
                        info="Select your LLM provider"
                    )
                    model_dropdown = gr.Dropdown(
                        choices=get_available_models("openai"),
                        label="Model",
                        value="gpt-4o-mini",
                        allow_custom_value=True,
                        info="Choose the AI model to use"
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
                gr.Markdown("Configure your SQL Server connection. Supports both local and remote databases.")
                
                with gr.Tabs():
                    with gr.Tab("🏠 Local Database"):
                        gr.Markdown("### Local SQL Server Express Connection")
                        with gr.Row():
                            local_server = gr.Textbox(
                                label="Server",
                                value="localhost",
                                info="Usually 'localhost' or '(localdb)\\MSSQLLocalDB'"
                            )
                            local_db_name = gr.Textbox(
                                label="Database",
                                value="master",
                                info="Database name"
                            )
                        
                        with gr.Row():
                            local_driver = gr.Dropdown(
                                choices=[
                                    "ODBC Driver 18 for SQL Server",
                                    "ODBC Driver 17 for SQL Server",
                                    "SQL Server Native Client 11.0",
                                    "SQL Server"
                                ],
                                label="Driver",
                                value="ODBC Driver 18 for SQL Server",
                                info="Select your installed SQL Server driver"
                            )
                        
                        local_use_windows_auth = gr.Checkbox(
                            label="Use Windows Authentication (Trusted Connection)",
                            value=True,
                            info="Recommended for local SQL Server Express"
                        )
                        
                        with gr.Row(visible=False) as local_creds_row:
                            local_username = gr.Textbox(label="Username")
                            local_password = gr.Textbox(label="Password", type="password")
                        
                        local_use_windows_auth.change(
                            lambda x: gr.update(visible=not x),
                            inputs=[local_use_windows_auth],
                            outputs=[local_creds_row]
                        )
                        
                        test_local_btn = gr.Button("🔌 Test Local Connection", variant="secondary")
                        save_local_btn = gr.Button("💾 Save Local Settings", variant="primary")
                    
                    with gr.Tab("🌐 Remote Database"):
                        gr.Markdown("### Remote SQL Server Connection")
                        with gr.Row():
                            remote_server = gr.Textbox(
                                label="Server Address",
                                placeholder="192.168.1.100 or myserver.database.windows.net",
                                info="IP address or hostname"
                            )
                            remote_port = gr.Textbox(
                                label="Port",
                                value="1433",
                                info="Default SQL Server port"
                            )
                        
                        with gr.Row():
                            remote_db_name = gr.Textbox(
                                label="Database",
                                placeholder="YourDatabase"
                            )
                            remote_driver = gr.Dropdown(
                                choices=[
                                    "ODBC Driver 18 for SQL Server",
                                    "ODBC Driver 17 for SQL Server",
                                    "SQL Server Native Client 11.0"
                                ],
                                label="Driver",
                                value="ODBC Driver 18 for SQL Server"
                            )
                        
                        with gr.Row():
                            remote_username = gr.Textbox(label="Username", placeholder="sa or db_user")
                            remote_password = gr.Textbox(label="Password", type="password")
                        
                        remote_encrypt = gr.Checkbox(
                            label="Encrypt connection (TLS/SSL)",
                            value=True,
                            info="Required for Azure SQL Database"
                        )
                        
                        remote_trust_cert = gr.Checkbox(
                            label="Trust Server Certificate",
                            value=False,
                            info="Enable if using self-signed certificates"
                        )
                        
                        test_remote_btn = gr.Button("🔌 Test Remote Connection", variant="secondary")
                        save_remote_btn = gr.Button("💾 Save Remote Settings", variant="primary")
                
                connection_status = gr.Markdown("")
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
                
                # Local database connection handlers
                def test_local_connection(server, db_name, driver, use_windows_auth, username, password):
                    try:
                        import pyodbc
                        if use_windows_auth:
                            conn_str = f"DRIVER={{{driver}}};SERVER={server};DATABASE={db_name};Trusted_Connection=yes;TrustServerCertificate=yes;"
                        else:
                            conn_str = f"DRIVER={{{driver}}};SERVER={server};DATABASE={db_name};UID={username};PWD={password};TrustServerCertificate=yes;"
                        
                        conn = pyodbc.connect(conn_str, timeout=5)
                        conn.close()
                        return "✅ Local database connection successful!"
                    except Exception as e:
                        return f"❌ Connection failed: {str(e)}"
                
                def save_local_settings(provider, model, temp, max_tokens, server, db_name, driver, use_windows_auth, username, password):
                    return save_settings(provider, model, temp, max_tokens, server, db_name, driver, 
                                       "" if use_windows_auth else username, 
                                       "" if use_windows_auth else password)
                
                test_local_btn.click(
                    test_local_connection,
                    inputs=[local_server, local_db_name, local_driver, local_use_windows_auth, local_username, local_password],
                    outputs=[connection_status]
                )
                
                save_local_btn.click(
                    save_local_settings,
                    inputs=[provider_dropdown, model_dropdown, temperature_slider, max_tokens_slider,
                           local_server, local_db_name, local_driver, local_use_windows_auth, local_username, local_password],
                    outputs=[settings_output]
                )
                
                # Remote database connection handlers
                def test_remote_connection(server, port, db_name, driver, username, password, encrypt, trust_cert):
                    try:
                        import pyodbc
                        server_with_port = f"{server},{port}" if port else server
                        encrypt_str = "yes" if encrypt else "no"
                        trust_str = "yes" if trust_cert else "no"
                        
                        conn_str = f"DRIVER={{{driver}}};SERVER={server_with_port};DATABASE={db_name};UID={username};PWD={password};Encrypt={encrypt_str};TrustServerCertificate={trust_str};"
                        
                        conn = pyodbc.connect(conn_str, timeout=10)
                        conn.close()
                        return "✅ Remote database connection successful!"
                    except Exception as e:
                        return f"❌ Connection failed: {str(e)}"
                
                def save_remote_settings(provider, model, temp, max_tokens, server, port, db_name, driver, username, password, encrypt, trust_cert):
                    server_with_port = f"{server},{port}" if port else server
                    return save_settings(provider, model, temp, max_tokens, server_with_port, db_name, driver, username, password)
                
                test_remote_btn.click(
                    test_remote_connection,
                    inputs=[remote_server, remote_port, remote_db_name, remote_driver, remote_username, remote_password, remote_encrypt, remote_trust_cert],
                    outputs=[connection_status]
                )
                
                save_remote_btn.click(
                    save_remote_settings,
                    inputs=[provider_dropdown, model_dropdown, temperature_slider, max_tokens_slider,
                           remote_server, remote_port, remote_db_name, remote_driver, remote_username, remote_password, remote_encrypt, remote_trust_cert],
                    outputs=[settings_output]
                )
                
                # Load current settings on page load
                demo.load(
                    load_settings,
                    outputs=[
                        provider_dropdown, model_dropdown, temperature_slider, max_tokens_slider,
                        local_server, local_db_name, local_driver, local_username, local_password
                    ]
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
                    
                    # Training Analytics Sub-tab
                    with gr.Tab("📈 Training Analytics"):
                        gr.Markdown("## 🎓 Learning Performance Dashboard")
                        gr.Markdown("Analyze the effectiveness of your training rules and query learnings.")
                        
                        analytics_display = gr.Markdown("Loading analytics...")
                        refresh_analytics_btn = gr.Button("🔄 Refresh Analytics", variant="primary")
                        consolidate_btn = gr.Button("🧹 Run Consolidation", variant="secondary")
                        
                        gr.Markdown("---")
                        gr.Markdown("### 💰 Token Cost Savings")
                        cost_savings = gr.Markdown()
                        
                        gr.Markdown("### 🏆 Top Performing Rules")
                        rule_ranking = gr.Markdown()
                        
                        def show_training_analytics():
                            """Display comprehensive training analytics."""
                            try:
                                from src.learnings import get_learning_stats, load_learnings
                                from src.quick_training import get_training_stats
                                import json
                                from pathlib import Path
                                
                                learning_stats = get_learning_stats()
                                training_stats = get_training_stats()

                                # Load audit events for safety/cache metrics (if available)
                                audit_path = Path(__file__).parent.parent / "logs" / "audit_events.json"
                                blocked_count = 0
                                cache_count = 0
                                total_events = 0
                                if audit_path.exists():
                                    try:
                                        with open(audit_path, 'r', encoding='utf-8') as f:
                                            events = json.load(f)
                                        total_events = len(events)
                                        for ev in events:
                                            if ev.get("safety_blocked"):
                                                blocked_count += 1
                                            if ev.get("cache_hit"):
                                                cache_count += 1
                                    except Exception:
                                        pass
                                
                                # Build analytics dashboard
                                output = "## 📊 Learning System Performance\n\n"
                                output += f"**Total Query Patterns Learned:** {learning_stats['total']}\n\n"
                                output += f"**Successful Patterns:** {learning_stats['successful']}\n\n"
                                output += f"**Total Queries Processed:** {learning_stats['total_queries']}\n\n"
                                output += "\n### 🔒 Safety & Cache\n"
                                output += f"**Safety Blocks:** {blocked_count} | **Cache Hits:** {cache_count} | **Audited Events:** {total_events}\n\n"
                                
                                if learning_stats['most_used']:
                                    mu = learning_stats['most_used']
                                    output += f"\n### 🔥 Most Popular Pattern\n"
                                    output += f"**Query:** {mu['original_query']}\n\n"
                                    output += f"**Clarified As:** {mu['clarified_query']}\n\n"
                                    output += f"**Usage Count:** {mu.get('usage_count', 0)} times\n\n"
                                
                                output += "\n---\n\n"
                                output += "## 🎯 Quick Training Rules\n\n"
                                output += f"**Total Rules:** {training_stats['total']}\n\n"
                                output += f"**Last Updated:** {training_stats['last_updated'] or 'Never'}\n\n"
                                
                                # Cost savings calculation
                                # Estimate: each learned pattern saves ~50 tokens on average
                                tokens_saved = learning_stats['successful'] * 50
                                cost_per_1k_tokens = 0.002  # $0.002 per 1K tokens (gpt-4o-mini)
                                estimated_savings = (tokens_saved / 1000) * cost_per_1k_tokens
                                
                                savings_output = f"### 💵 Estimated Token Savings\n\n"
                                savings_output += f"**Tokens Saved by Learnings:** ~{tokens_saved:,} tokens\n\n"
                                savings_output += f"**Estimated Cost Savings:** ${estimated_savings:.4f}\n\n"
                                savings_output += f"*Based on {learning_stats['successful']} successful patterns averaging 50 tokens each*\n"
                                
                                # Rule ranking (simplified - just show count)
                                ranking_output = f"### 📋 Training Rules Impact\n\n"
                                ranking_output += f"Your {training_stats['total']} training rules are actively guiding the AI.\n\n"
                                ranking_output += f"*Detailed per-rule analytics coming in next update*\n"
                                
                                return output, savings_output, ranking_output
                                
                            except Exception as e:
                                logger.error(f"Analytics error: {e}", exc_info=True)
                                return f"❌ Error: {str(e)}", "", ""
                        
                        refresh_analytics_btn.click(
                            show_training_analytics,
                            outputs=[analytics_display, cost_savings, rule_ranking]
                        )
                        
                        def _run_consolidation():
                            try:
                                from src.consolidation import consolidate_training
                                ok, msg = consolidate_training()
                                return msg if ok else f"❌ {msg}"
                            except Exception as e:
                                return f"❌ Error: {e}"

                        consolidate_btn.click(_run_consolidation, outputs=[analytics_display])
                        
                        # Load on tab open
                        demo.load(show_training_analytics, outputs=[analytics_display, cost_savings, rule_ranking])
                    
                    # Rule Suggestions Sub-tab (from feedback)
                    with gr.Tab("🧩 Rule Suggestions"):
                        gr.Markdown("## Suggested Training Rules")
                        gr.Markdown("Generated automatically from negative feedback with comments. Approve to add as Quick Training rules.")

                        suggestions_output = gr.Markdown(visible=True)
                        suggestions_select = gr.Dropdown(label="Select a suggestion to approve", choices=[], interactive=True)
                        approve_btn = gr.Button("✅ Approve & Add Rule", variant="primary")
                        refresh_suggestions_btn = gr.Button("🔄 Refresh Suggestions")

                        def _load_rule_suggestions():
                            items = get_rule_suggestions(limit=50)
                            if not items:
                                return "No rule suggestions available yet.", []
                            # Build display markdown and dropdown choices
                            md = "### Recent Suggestions\n\n"
                            choices = []
                            for idx, s in enumerate(items):
                                ts = s.get("timestamp", "")[:19]
                                q = (s.get("question", "") or "").strip()
                                rule = (s.get("suggested_rule", "") or "").strip()
                                md += f"**{idx+1}.** ({ts})\n- Query: _{q[:100]}_\n- Rule: {rule}\n\n"
                                # Use index as value for selection
                                choices.append(f"{idx+1}: {q[:50]}...")
                            return md, choices

                        def _approve_selected(selection: str):
                            items = get_rule_suggestions(limit=50)
                            if not items:
                                return "❌ No suggestions to approve", gr.Dropdown(choices=[])
                            try:
                                # Parse index from selection "N: ..."
                                idx = int(selection.split(":", 1)[0]) - 1
                                s = items[idx]
                                from src.quick_training import add_training_rule
                                ok, msg = add_training_rule(s.get("suggested_rule", ""), status="approved")
                                status = "✅ Rule added" if ok else f"❌ {msg}"
                                md, choices = _load_rule_suggestions()
                                return f"{status}\n\n{msg if not ok else s.get('suggested_rule','')}", gr.Dropdown(choices=choices, value=None)
                            except Exception as e:
                                return f"❌ Error: {e}", gr.Dropdown(choices=[])

                        # Wire buttons
                        refresh_suggestions_btn.click(_load_rule_suggestions, outputs=[suggestions_output, suggestions_select])
                        approve_btn.click(_approve_selected, inputs=[suggestions_select], outputs=[suggestions_output, suggestions_select])

                        # Load suggestions on tab open
                        demo.load(_load_rule_suggestions, outputs=[suggestions_output, suggestions_select])

                    # Rule Governance Sub-tab
                    with gr.Tab("🛡️ Rule Governance"):
                        gr.Markdown("## Govern Training Rules")
                        gr.Markdown("Set owner, priority, and status. Only approved rules are injected into prompts.")

                        gov_rules_md = gr.Markdown()
                        gov_select = gr.Dropdown(label="Select Rule #", choices=[], interactive=True)
                        owner_in = gr.Textbox(label="Owner", placeholder="e.g., ameer")
                        priority_in = gr.Slider(label="Priority (1=high, 10=low)", minimum=1, maximum=10, step=1, value=5)
                        status_in = gr.Dropdown(label="Status", choices=["draft", "approved", "deprecated"], value="draft")
                        with gr.Row():
                            approve_btn2 = gr.Button("✅ Approve", variant="primary")
                            update_btn = gr.Button("💾 Update")
                            delete_btn = gr.Button("🗑️ Delete", variant="stop")
                            refresh_gov_btn = gr.Button("🔄 Refresh")
                        gov_msg = gr.Markdown()

                        def _load_governance_rules():
                            data = load_training_rules()
                            rules = data.get("rules", [])
                            if not rules:
                                return "No rules yet.", []
                            md = f"### Rules ({len(rules)})\n\n"
                            choices = []
                            for idx, r in enumerate(rules, 1):
                                md += (
                                    f"**#{idx}** - {r.get('instruction','')[:80]}\n"
                                    f"- Status: {r.get('status','draft')} · Priority: {r.get('priority',5)} · Owner: {r.get('owner','')}\n\n"
                                )
                                choices.append(str(idx))
                            return md, choices

                        def _populate_fields(rule_no: str):
                            try:
                                idx = int(rule_no)
                            except:
                                return owner_in, priority_in, status_in
                            data = load_training_rules()
                            rules = data.get("rules", [])
                            if idx < 1 or idx > len(rules):
                                return owner_in, priority_in, status_in
                            r = rules[idx - 1]
                            return (
                                gr.Textbox(value=r.get("owner","")),
                                gr.Slider(value=int(r.get("priority",5))),
                                gr.Dropdown(value=r.get("status","draft"))
                            )

                        def _approve_rule(rule_no: str):
                            try:
                                idx = int(rule_no)
                            except Exception as e:
                                return f"❌ Invalid selection: {e}", gr.Dropdown(choices=[])
                            ok, msg = update_rule(idx, status="approved")
                            md, choices = _load_governance_rules()
                            return (f"{'✅ Approved' if ok else '❌ ' + msg}", gr.Dropdown(choices=choices, value=rule_no if ok else None))

                        def _update_rule(rule_no: str, owner: str, priority: int, status: str):
                            try:
                                idx = int(rule_no)
                            except Exception as e:
                                return f"❌ Invalid selection: {e}", gr.Dropdown(choices=[])
                            ok, msg = update_rule(idx, owner=owner, priority=priority, status=status)
                            md, choices = _load_governance_rules()
                            return (f"{'✅ Updated' if ok else '❌ ' + msg}", gr.Dropdown(choices=choices, value=rule_no if ok else None))

                        def _delete_rule(rule_no: str):
                            try:
                                idx = int(rule_no)
                            except Exception as e:
                                return f"❌ Invalid selection: {e}", gr.Dropdown(choices=[])
                            ok, msg = delete_rule(idx)
                            md, choices = _load_governance_rules()
                            return (msg, gr.Dropdown(choices=choices, value=None))

                        # Wiring
                        refresh_gov_btn.click(_load_governance_rules, outputs=[gov_rules_md, gov_select])
                        gov_select.change(_populate_fields, inputs=[gov_select], outputs=[owner_in, priority_in, status_in])
                        approve_btn2.click(_approve_rule, inputs=[gov_select], outputs=[gov_msg, gov_select])
                        update_btn.click(_update_rule, inputs=[gov_select, owner_in, priority_in, status_in], outputs=[gov_msg, gov_select])
                        delete_btn.click(_delete_rule, inputs=[gov_select], outputs=[gov_msg, gov_select])

                        # Initial load
                        demo.load(_load_governance_rules, outputs=[gov_rules_md, gov_select])

                    # Custom Personas Sub-tab
                    with gr.Tab("🎭 Custom Personas"):
                        gr.Markdown("## Create Custom AI Personas")
                        gr.Markdown("Design specialized AI assistants with unique characteristics and domain expertise.")
                        
                        with gr.Row():
                            with gr.Column(scale=1):
                                gr.Markdown("### ➕ Create New Persona")
                                
                                persona_id_input = gr.Textbox(label="Persona ID", placeholder="e.g., logistics_expert", info="Unique identifier (no spaces)")
                                persona_name_input = gr.Textbox(label="Display Name", placeholder="e.g., Logistics Expert")
                                persona_desc_input = gr.Textbox(label="Description", placeholder="What makes this persona unique?", lines=2)
                                
                                persona_tone = gr.Dropdown(
                                    choices=["friendly", "professional", "technical"],
                                    value="professional",
                                    label="Communication Tone"
                                )
                                
                                persona_complexity = gr.Dropdown(
                                    choices=["simple", "balanced", "detailed"],
                                    value="balanced",
                                    label="Response Complexity"
                                )
                                
                                persona_domain = gr.Dropdown(
                                    choices=["general", "finance", "logistics", "retail", "manufacturing"],
                                    value="general",
                                    label="Domain Expertise"
                                )
                                
                                persona_instructions = gr.Textbox(
                                    label="Custom Instructions",
                                    placeholder="Additional guidance for this persona...",
                                    lines=4
                                )
                                
                                save_persona_btn = gr.Button("💾 Save Persona", variant="primary")
                                persona_status = gr.Markdown("")
                            
                            with gr.Column(scale=1):
                                gr.Markdown("### 📊 Persona Performance")
                                
                                persona_list_display = gr.Markdown("Loading personas...")
                                refresh_personas_btn = gr.Button("🔄 Refresh List", size="sm")
                                
                                gr.Markdown("---")
                                gr.Markdown("### 🏆 Effectiveness Ranking")
                                persona_ranking = gr.Markdown()
                        
                        def save_new_persona(pid, name, desc, tone, complexity, domain, instructions):
                            """Save a custom persona."""
                            try:
                                if not pid or not name:
                                    return "❌ Persona ID and Name are required"
                                
                                # Validate ID (no spaces)
                                if ' ' in pid:
                                    return "❌ Persona ID cannot contain spaces"
                                
                                success = save_custom_persona(
                                    persona_id=pid,
                                    name=name,
                                    description=desc,
                                    tone=tone,
                                    complexity=complexity,
                                    domain_expertise=domain,
                                    custom_instructions=instructions
                                )
                                
                                if success:
                                    return f"✅ Persona '{name}' saved successfully!\n\nYou can now select it from the persona dropdown in the Chat tab."
                                else:
                                    return "❌ Failed to save persona"
                                    
                            except Exception as e:
                                logger.error(f"Persona save error: {e}")
                                return f"❌ Error: {str(e)}"
                        
                        def list_personas_display():
                            """Display all custom personas."""
                            try:
                                personas = list_custom_personas()
                                
                                if not personas:
                                    return "No custom personas created yet.\n\nCreate your first persona using the form on the left!"
                                
                                output = f"### 📋 Custom Personas ({len(personas)})\n\n"
                                
                                for p in personas:
                                    stats = p.get('stats', {})
                                    total_queries = stats.get('total_queries', 0)
                                    success_rate = 0
                                    if total_queries > 0:
                                        success_rate = (stats.get('successful_queries', 0) / total_queries) * 100
                                    
                                    output += f"#### {p['name']}\n"
                                    output += f"**ID:** `{p['id']}`\n\n"
                                    output += f"**Tone:** {p['tone']} | **Complexity:** {p['complexity']} | **Domain:** {p['domain_expertise']}\n\n"
                                    output += f"**Usage:** {total_queries} queries | **Success Rate:** {success_rate:.1f}%\n\n"
                                    output += f"---\n\n"
                                
                                return output
                                
                            except Exception as e:
                                logger.error(f"Persona list error: {e}")
                                return f"❌ Error: {str(e)}"
                        
                        def show_persona_ranking():
                            """Show personas ranked by effectiveness."""
                            try:
                                ranking = get_persona_effectiveness_ranking()
                                
                                if not ranking:
                                    return "No usage data yet for custom personas."
                                
                                output = "### 🏆 Top Performing Personas\n\n"
                                
                                for i, p in enumerate(ranking[:5], 1):
                                    output += f"**{i}. {p['name']}**\n"
                                    output += f"   Success Rate: {p['success_rate']:.1f}% | "
                                    output += f"Queries: {p['total_queries']} | "
                                    output += f"Avg Tokens: {p['avg_tokens']:.0f}\n\n"
                                
                                return output
                                
                            except Exception as e:
                                logger.error(f"Ranking error: {e}")
                                return f"❌ Error: {str(e)}"
                        
                        save_persona_btn.click(
                            save_new_persona,
                            inputs=[persona_id_input, persona_name_input, persona_desc_input,
                                   persona_tone, persona_complexity, persona_domain, persona_instructions],
                            outputs=[persona_status]
                        ).then(
                            # Refresh the persona dropdown in Chat tab
                            lambda: gr.update(choices=get_all_personas()),
                            outputs=[persona_selector]
                        )
                        
                        refresh_personas_btn.click(
                            list_personas_display,
                            outputs=[persona_list_display]
                        )
                        
                        # Load on page open
                        demo.load(list_personas_display, outputs=[persona_list_display])
                        demo.load(show_persona_ranking, outputs=[persona_ranking])
            
            # Developer Tools Tab (UPDATED)
            with gr.Tab("🔬 Developer Tools"):
                gr.Markdown("## Developer Insights")
                gr.Markdown("Session summaries, cache stats, feedback analytics, and export.")
                
                with gr.Row():
                    with gr.Column(scale=1):
                        gr.Markdown("### Session Summary")
                        
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
                        
                        # Cache Statistics Section
                        gr.Markdown("---")
                        gr.Markdown("### Cache Performance")
                        cache_stats_display = gr.Markdown("Loading cache stats...")
                        refresh_cache_btn = gr.Button("🔄 Refresh Cache Stats", size="sm")
                        clear_cache_btn = gr.Button("🗑️ Clear All Cache", size="sm", variant="stop")
                        cache_action_status = gr.Markdown("")
                        
                        def show_cache_stats():
                            """Display cache performance statistics."""
                            try:
                                stats = get_cache_stats()
                                
                                result_cache = stats.get('result_cache', {})
                                sql_cache = stats.get('sql_cache', {})
                                cache_size = stats.get('cache_size_mb', 0)
                                
                                output = "#### 💾 Result Cache\n"
                                output += f"**Cached Queries:** {result_cache.get('total_entries', 0)}\n\n"
                                output += f"**Cache Hits:** {result_cache.get('total_hits', 0)}\n\n"
                                
                                if result_cache.get('most_popular'):
                                    output += f"**Most Popular:** {result_cache['most_popular'][:50]}... ({result_cache.get('most_popular_hits', 0)} hits)\n\n"
                                
                                output += "\n#### 🔤 SQL Cache\n"
                                output += f"**Cached SQL Queries:** {sql_cache.get('total_entries', 0)}\n\n"
                                output += f"**Reuse Count:** {sql_cache.get('total_reuses', 0)}\n\n"
                                
                                if sql_cache.get('most_reused'):
                                    output += f"**Most Reused:** {sql_cache['most_reused'][:50]}... ({sql_cache.get('most_reused_count', 0)} reuses)\n\n"
                                
                                output += f"\n**Total Cache Size:** {cache_size:.2f} MB\n"
                                
                                # Calculate token savings estimate
                                total_hits = result_cache.get('total_hits', 0) + sql_cache.get('total_reuses', 0)
                                tokens_saved = total_hits * 50  # Estimate 50 tokens saved per hit
                                cost_saved = (tokens_saved / 1000) * 0.002  # $0.002 per 1K tokens
                                
                                output += f"\n#### 💰 Savings\n"
                                output += f"**Est. Tokens Saved:** ~{tokens_saved:,}\n\n"
                                output += f"**Est. Cost Saved:** ${cost_saved:.4f}\n"
                                
                                return output
                            except Exception as e:
                                logger.error(f"Cache stats error: {e}")
                                return f"❌ Error: {str(e)}"
                        
                        def clear_cache_action():
                            """Clear all cached data."""
                            try:
                                success = clear_all_cache()
                                if success:
                                    return "✅ Cache cleared successfully!"
                                return "❌ Failed to clear cache"
                            except Exception as e:
                                return f"❌ Error: {str(e)}"
                        
                        refresh_cache_btn.click(show_cache_stats, outputs=[cache_stats_display])
                        clear_cache_btn.click(clear_cache_action, outputs=[cache_action_status])
                        
                        # Feedback Analytics Section
                        gr.Markdown("---")
                        gr.Markdown("### Feedback Analytics")
                        
                        feedback_stats_display = gr.Markdown("No feedback data yet.")
                        recent_feedback_display = gr.Markdown("")
                        refresh_feedback_btn = gr.Button("🔄 Refresh Feedback Stats", size="sm")
                        
                        def show_feedback_analytics():
                            """Display feedback analytics."""
                            try:
                                stats = get_feedback_statistics()
                                recent = get_recent_feedback(limit=5)
                                
                                stats_md = format_feedback_for_display(stats)
                                recent_md = format_recent_feedback(recent)
                                
                                return stats_md, recent_md
                            except Exception as e:
                                logger.error(f"Feedback analytics error: {e}")
                                return f"❌ Error: {str(e)}", ""
                        
                        refresh_feedback_btn.click(
                            show_feedback_analytics,
                            outputs=[feedback_stats_display, recent_feedback_display]
                        )
                        
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
                        gr.Markdown("### Controls")
                        gr.Markdown("Observability and diagnostics moved to 🛠️ Developer Settings.")
                
                # Load session summary on page load
                demo.load(
                    get_current_session_summary,
                    outputs=[session_summary]
                )

            # Developer Settings Tab (NEW)
            with gr.Tab("🛠️ Developer Settings"):
                gr.Markdown("## Observability & Diagnostics")
                gr.Markdown("Configure developer mode features and collect diagnostics for troubleshooting.")

                with gr.Row():
                    with gr.Column(scale=1):
                        gr.Markdown("### Observability Settings")
                        gr.Markdown("**Tier 1** (Always On): Essential metrics  \n**Tier 2** (Developer Mode): Detailed debugging")

                        # Configuration controls
                        tier1_checkbox = gr.Checkbox(label="✅ Tier 1: Essential Metrics", value=True, interactive=False)

                        gr.Markdown("---")
                        tier2_checkbox = gr.Checkbox(label="🔧 Tier 2: Developer Mode", value=False, info="Enable detailed debugging")

                        # Sub-features (dependent on Tier 2)
                        gr.Markdown("**⚙️ Tier 2 Features** (only work when Developer Mode is ON):")
                        capture_llm_prompts = gr.Checkbox(label="📝 Capture Full LLM Prompts", value=False, info="⚠️ Very detailed", interactive=False)
                        capture_sample_data = gr.Checkbox(label="📊 Capture Sample Data", value=False, info="⚠️ Privacy concern", interactive=False)

                        gr.Markdown("---")
                        save_config_btn = gr.Button("💾 Save Configuration", variant="secondary")
                        config_status = gr.Markdown("")

                        def toggle_tier2_features(tier2_enabled):
                            """Enable/disable sub-features based on Tier 2 state."""
                            return (
                                gr.update(interactive=tier2_enabled),  # capture_llm_prompts
                                gr.update(interactive=tier2_enabled),  # capture_sample_data
                            )

                        def save_configuration(tier2, llm_prompts, sample_data):
                            """Save observability configuration."""
                            try:
                                new_config = session_tracker.config.copy()
                                new_config.update({
                                    "tier2_enabled": tier2,
                                    "capture_llm_prompts": llm_prompts if tier2 else False,
                                    "capture_sample_data": sample_data if tier2 else False,
                                })
                                session_tracker.save_config(new_config)

                                status = "✅ **Configuration Saved!**\n\n"
                                status += "🔧 Developer Mode ENABLED" if tier2 else "📊 Essential mode only"
                                if tier2:
                                    status += f"\n- LLM Prompts: {'ON' if llm_prompts else 'OFF'}"
                                    status += f"\n- Sample Data: {'ON' if sample_data else 'OFF'}"
                                return status
                            except Exception as e:
                                return f"❌ Error: {str(e)}"

                        # Wire up Tier 2 toggle to enable/disable sub-features
                        tier2_checkbox.change(
                            toggle_tier2_features,
                            inputs=[tier2_checkbox],
                            outputs=[capture_llm_prompts, capture_sample_data]
                        )

                        save_config_btn.click(
                            save_configuration,
                            inputs=[tier2_checkbox, capture_llm_prompts, capture_sample_data],
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

                    with gr.Column(scale=1):
                        gr.Markdown("### Diagnostics")
                        gr.Markdown("Collect system information, configuration, and logs for troubleshooting.")
                        dev_collect_btn = gr.Button("🔍 Collect Diagnostics", variant="primary")
                        dev_download_file = gr.File(label="Download Diagnostics File")
                        dev_collect_btn.click(
                            collect_and_download_diagnostics,
                            outputs=[dev_download_file]
                        )

            
        
        gr.Markdown("---")
        gr.Markdown("💡 **Tip:** Diagnostics are available under 🛠️ Developer Settings.")
    
    return demo

if __name__ == "__main__":
    demo = build_ui()
    demo.launch(theme=gr.themes.Default())
