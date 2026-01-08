"""
Gradio UI for DBAI Application
Provides a multi-tab interface for chat, settings, training, data import, and diagnostics.
"""
import logging
import os
import io
from typing import List, Optional, Tuple
from datetime import datetime
import gradio as gr
import yaml
from pathlib import Path
from dotenv import load_dotenv, set_key

from src.providers import create_provider
from src.database import reload_engine, get_engine, run_query, get_sql_database, load_metadata, save_metadata
from src.llm import make_sql_chain, make_describe_chain, extract_sql_from_response, validate_sql
from src.telemetry import TelemetryLogger
from src.uploader import process_excel_files, check_table_exists, import_dataframe_to_db
from src.diagnostics import collect_diagnostics, collect_full_session_bundle
from src.clarity import analyze_query_clarity, needs_clarification
from src.learnings import save_learning, get_learning_stats
from src.quick_training import add_training_rule, get_training_stats, format_rules_display, update_rule, delete_rule, load_training_rules
from src.session_tracker import get_session_tracker, reset_session_tracker
from src.query_classifier import classify_query, needs_movement_clarification, get_clarification_for_classification
from src.query_templates import generate_sql_from_template
from src.feedback import save_feedback, get_feedback_statistics, format_feedback_for_display, get_recent_feedback, format_recent_feedback, get_rule_suggestions

# Version tracking - increment by 5 for each significant update
UI_BUILD_VERSION = 25
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
            try:
                # Memoize this clarification choice for the session
                session_tracker.remember_clarification(original_query, question)
            except Exception:
                pass
    
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
    try:
        classification = classify_query(question)
        # Basic safety: ensure expected keys exist
        if not isinstance(classification, dict):
            raise ValueError("Classification returned non-dict")
        classification.setdefault('type', 'unknown')
        classification.setdefault('confidence', 0)
        classification.setdefault('params', {})
    except Exception as e:
        logger.error(f"Classification error: {e}")
        classification = {'type': 'unknown', 'confidence': 0, 'params': {}}
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
            # If we've previously clarified this exact query in this session, reuse the choice
            try:
                remembered = session_tracker.get_clarification(question)
            except Exception:
                remembered = None
            if remembered:
                # Re-run classification with the remembered clarified intent
                question = remembered
                try:
                    classification = classify_query(question)
                    classification.setdefault('type', 'unknown')
                    classification.setdefault('confidence', 0)
                    classification.setdefault('params', {})
                except Exception as e:
                    logger.error(f"Re-classification error after memoized clarification: {e}")
                    classification = {'type': 'unknown', 'confidence': 0, 'params': {}}
            
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
            # If we have a remembered choice for this query, skip asking and apply it
            try:
                remembered = session_tracker.get_clarification(question)
            except Exception:
                remembered = None
            if remembered:
                # Apply remembered clarified intent
                question = remembered
                logger.info(f"Applied memoized clarification: '{remembered}'")
                # Continue without prompting for clarification
            else:
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
                # Track applied rules for per-rule impact analytics
                applied_rules = sql_response_obj.get('rules_applied', []) or []
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
        # Update per-rule usage stats if any rules were applied
        try:
            if success and applied_rules:
                from src.quick_training import bump_rule_usage
                bump_rule_usage(applied_rules)
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
    """Collect next-level diagnostics bundle and return zip path for download."""
    try:
        # Create full bundle with sensitive fields included per user request
        bundle_path = collect_full_session_bundle(include_sensitive=True)
        return bundle_path
    except Exception as e:
        logger.error(f"Diagnostics collection error: {e}", exc_info=True)
        # Fallback to basic text report
        try:
            return collect_diagnostics()
        except Exception:
            return None

# Build UI
def build_ui():
    """Build and return the Gradio interface."""
    
    with gr.Blocks(title="DBAI - Database AI Assistant") as demo:
        gr.Markdown(f"# 🤖 DBAI - Database AI Assistant  `Build {UI_BUILD_VERSION}`")
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
                
                # Graduated feedback flow
                feedback_category = gr.Radio(
                    choices=["❌ Wrong Data", "📊 Wrong Format", "❓ Needs Clarification", "💬 Other Issue"],
                    label="What was the issue?",
                    visible=False
                )
                feedback_comment = gr.Textbox(
                    placeholder="Please describe the issue (optional for most categories, required for 'Other Issue')",
                    label="Additional Details",
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
                    """Show category selection on thumbs down."""
                    if not msg_id or msg_id == "":
                        return "⚠️ Please send a query first.", gr.update(visible=False), gr.update(visible=False), gr.update(visible=False)
                    
                    return "What was the issue?", gr.update(visible=True), gr.update(visible=False), gr.update(visible=False)
                
                def handle_category_selection(category):
                    """Show comment field based on category selection."""
                    if not category:
                        return gr.update(visible=False), gr.update(visible=False)
                    
                    # For "Other Issue", require comment
                    if category == "💬 Other Issue":
                        return gr.update(visible=True, placeholder="Please describe the issue..."), gr.update(visible=True)
                    else:
                        # For predefined categories, comment is optional
                        return gr.update(visible=True, placeholder="Additional details (optional)..."), gr.update(visible=True)
                
                def submit_detailed_feedback(msg_id, category, feedback_text):
                    """Submit categorized feedback and create appropriate training rule."""
                    if not msg_id or msg_id == "":
                        return "⚠️ Please send a query first before providing feedback."
                    
                    if not category:
                        return "⚠️ Please select an issue category."
                    
                    # For "Other Issue", require description
                    if category == "💬 Other Issue" and not feedback_text.strip():
                        return "⚠️ Please describe the issue for 'Other Issue' category."
                    
                    try:
                        # Get query info
                        question = last_query_info.get("question", "")
                        sql = last_query_info.get("sql", "")
                        response = last_query_info.get("result", "")
                        session_id = session_tracker.session_id if session_tracker else None
                        
                        # Combine category and comment for feedback text
                        full_feedback = category
                        if feedback_text and feedback_text.strip():
                            full_feedback += f": {feedback_text}"
                        
                        # Save feedback
                        save_feedback(
                            message_id=msg_id,
                            feedback_type="thumbs_down",
                            question=question,
                            sql_query=sql,
                            response=response,
                            feedback_text=full_feedback,
                            session_id=session_id
                        )
                        
                        # Track in session
                        if session_tracker:
                            session_tracker.track_training_event(
                                event_type="negative_feedback",
                                details={"message_id": msg_id, "category": category, "feedback": feedback_text}
                            )
                        
                        # Create training rule based on category
                        rule = None
                        if category == "❌ Wrong Data":
                            if feedback_text.strip():
                                rule = f"When asked '{question}', ensure data accuracy: {feedback_text}"
                            else:
                                rule = f"Review data accuracy for queries like: '{question}'"
                        elif category == "📊 Wrong Format":
                            if feedback_text.strip():
                                rule = f"For '{question}', format results as: {feedback_text}"
                            else:
                                rule = f"Improve result formatting for: '{question}'"
                        elif category == "❓ Needs Clarification":
                            if feedback_text.strip():
                                rule = f"When query is ambiguous like '{question}', clarify: {feedback_text}"
                            else:
                                rule = f"Request clarification for ambiguous queries like: '{question}'"
                        elif category == "💬 Other Issue" and feedback_text.strip():
                            rule = f"CORRECTION for '{question}': {feedback_text}"
                        
                        if rule:
                            add_training_rule(rule)
                            return "✅ Feedback submitted and training rule created! This will help improve similar queries."
                        else:
                            return "✅ Feedback submitted. Thanks for helping us improve!"
                            
                    except Exception as e:
                        logger.error(f"Error saving detailed feedback: {e}")
                        return f"❌ Error saving feedback: {str(e)}"
                
                # Wire feedback buttons
                thumbs_up_btn.click(
                    handle_thumbs_up,
                    inputs=[current_message_id],
                    outputs=[feedback_status]
                )
                
                thumbs_down_btn.click(
                    handle_thumbs_down,
                    inputs=[current_message_id],
                    outputs=[feedback_status, feedback_category, feedback_comment, submit_feedback_btn]
                )
                
                feedback_category.change(
                    handle_category_selection,
                    inputs=[feedback_category],
                    outputs=[feedback_comment, submit_feedback_btn]
                )
                
                submit_feedback_btn.click(
                    submit_detailed_feedback,
                    inputs=[current_message_id, feedback_category, feedback_comment],
                    outputs=[feedback_status]
                ).then(
                    lambda: (gr.update(value=None, visible=False), gr.update(value="", visible=False), gr.update(visible=False)),
                    outputs=[feedback_category, feedback_comment, submit_feedback_btn]
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
            
            # Train Tab - Premium UX
            with gr.Tab("🎓 Train"):
                gr.Markdown("## 🚀 Training & Rules Management")
                gr.Markdown("Test rules, manage governance, and configure domain context—all in one place.")
                
                with gr.Tabs():
                    # Workflow 1: Quick Train (Test + Quick Setup combined)
                    with gr.Tab("⚡ Quick Train"):
                        gr.Markdown("""### Step 1: Enter Your Training Rule
**Plain English:** Tell the AI how to interpret specific queries or terms.

Examples:
- "When users say 'total arrival yarn', return LBS received (not PKR amount)"
- "Greige received = meters of greige fabric from suppliers"
- "Stock check always shows current inventory in both LBS and bags"
""")
                        
                        test_rule_input = gr.Textbox(
                            label="Training Rule",
                            placeholder='e.g., "When I ask for total arrival, multiply by 2 because we track in half-units"',
                            lines=2
                        )
                        
                        gr.Markdown("### Step 2: Test With a Sample Query")
                        test_sample_query = gr.Textbox(
                            label="Sample Query",
                            placeholder='e.g., "What was total arrival yarn last week?"',
                            lines=2
                        )
                        
                        with gr.Row():
                            test_rule_btn = gr.Button("🧪 Test Rule", variant="primary", size="lg")
                            clear_test_btn = gr.Button("🔄 Clear", variant="secondary")
                        
                        test_result_md = gr.Markdown("")
                        
                        gr.Markdown("### Step 3: Review & Save")
                        with gr.Row():
                            save_rule_btn = gr.Button("💾 Save Rule", variant="primary")
                            discard_btn = gr.Button("❌ Discard", variant="secondary")
                        save_msg = gr.Markdown("")
                        
                        # Hidden state to track test result
                        test_result_state = gr.State({})
                        
                        def test_training_rule(rule_text, sample_query):
                            """Test a training rule with a sample query."""
                            if not rule_text.strip() or not sample_query.strip():
                                return {"error": "❌ Enter both rule and sample query"}, "❌ Enter both rule and sample query"
                            
                            try:
                                # Get current SQL without rule (baseline)
                                logger.info(f"Testing rule: {rule_text[:100]}")
                                
                                # Call LLM to get SQL with and without the rule
                                global current_llm, current_provider
                                if current_llm is None:
                                    config = load_config()
                                    llm_config = config.get('llm', {})
                                    provider_name = llm_config.get('provider', 'openai')
                                    model = llm_config.get('model', 'gpt-4o-mini')
                                    current_provider = create_provider(provider_name)
                                    current_llm = current_provider.get_llm(model, 0.3, 2000)
                                
                                # Get database schema
                                db = get_sql_database()
                                schema = db.get_table_info() if db else "Schema unavailable"
                                
                                # Baseline SQL (without rule)
                                baseline_prompt = f"""Database schema:
{schema}

User query: {sample_query}

Generate SQL Server query for this request. Return ONLY the SQL."""
                                
                                baseline_response = current_llm.invoke(baseline_prompt)
                                baseline_sql = baseline_response.content if hasattr(baseline_response, 'content') else str(baseline_response)
                                baseline_sql = baseline_sql.strip().replace("```sql", "").replace("```", "").strip()
                                
                                # Enhanced SQL (with rule)
                                enhanced_prompt = f"""Database schema:
{schema}

Training rule: {rule_text}

User query: {sample_query}

Generate SQL Server query for this request, taking the training rule into account. Return ONLY the SQL."""
                                
                                enhanced_response = current_llm.invoke(enhanced_prompt)
                                enhanced_sql = enhanced_response.content if hasattr(enhanced_response, 'content') else str(enhanced_response)
                                enhanced_sql = enhanced_sql.strip().replace("```sql", "").replace("```", "").strip()
                                
                                # Display comparison
                                result_md = f"""
### ✅ Test Complete

#### Baseline SQL (without rule)
```sql
{baseline_sql[:500]}
```

#### Enhanced SQL (with rule)
```sql
{enhanced_sql[:500]}
```

**Rule applied:** Yes ✅

---
*Does the enhanced version look better? If yes, save the rule below.*
"""
                                
                                return {
                                    "rule": rule_text,
                                    "baseline_sql": baseline_sql,
                                    "enhanced_sql": enhanced_sql,
                                    "sample_query": sample_query
                                }, result_md
                            except Exception as e:
                                logger.error(f"Test error: {e}", exc_info=True)
                                return {"error": str(e)}, f"❌ Test failed: {e}"
                        
                        def save_tested_rule(state_data):
                            """Save the tested rule."""
                            if not state_data or "error" in state_data:
                                return "❌ No valid test result to save"
                            
                            try:
                                rule_text = state_data.get("rule", "")
                                ok, msg = add_training_rule(rule_text)
                                
                                if ok:
                                    logger.info(f"Rule saved: {rule_text[:100]}")
                                    session_tracker.track_training_event(
                                        event_type="test_and_learn_rule_saved",
                                        details={"rule": rule_text}
                                    )
                                    return f"✅ Rule saved! {msg}"
                                else:
                                    return f"❌ Save failed: {msg}"
                            except Exception as e:
                                return f"❌ Error: {e}"
                        
                        test_rule_btn.click(
                            test_training_rule,
                            inputs=[test_rule_input, test_sample_query],
                            outputs=[test_result_state, test_result_md]
                        )
                        
                        save_rule_btn.click(
                            save_tested_rule,
                            inputs=[test_result_state],
                            outputs=[save_msg]
                        )
                        
                        clear_test_btn.click(
                            lambda: ("", "", {}, "", ""),
                            outputs=[test_rule_input, test_sample_query, test_result_state, test_result_md, save_msg]
                        )
                        
                        discard_btn.click(
                            lambda: ("", "", {}, "", "Discarded. Enter a new rule."),
                            outputs=[test_rule_input, test_sample_query, test_result_state, test_result_md, save_msg]
                        )
                        
                        # Quick Setup Section (integrated into Quick Train)
                        gr.Markdown("---")
                        gr.Markdown("### 🎯 Quick Industry Setup")
                        gr.Markdown("Select your industry and common units for instant domain context generation.")
                        
                        with gr.Row():
                            with gr.Column():
                                gr.Markdown("**Industries**")
                                setup_textile = gr.Checkbox(label="🧵 Textile/Fabric")
                                setup_retail = gr.Checkbox(label="🛒 Retail/E-commerce")
                                setup_manufacturing = gr.Checkbox(label="🏭 Manufacturing")
                                setup_finance = gr.Checkbox(label="💰 Finance/Banking")
                                setup_logistics = gr.Checkbox(label="🚚 Logistics/Supply Chain")
                                setup_healthcare = gr.Checkbox(label="🏥 Healthcare")
                                setup_foodbev = gr.Checkbox(label="🍔 Food & Beverage")
                            
                            with gr.Column():
                                gr.Markdown("**Common Units**")
                                unit_lbs = gr.Checkbox(label="LBS (Pounds)")
                                unit_kg = gr.Checkbox(label="KG (Kilograms)")
                                unit_meters = gr.Checkbox(label="Meters/Yards")
                                unit_pkr = gr.Checkbox(label="PKR (Pakistani Rupee)")
                                unit_usd = gr.Checkbox(label="USD (US Dollar)")
                                unit_pieces = gr.Checkbox(label="Pieces/Units")
                        
                        quick_setup_btn = gr.Button("🚀 Generate Domain Instructions", variant="secondary", size="lg")
                        quick_setup_status = gr.Markdown("")
                        
                        def generate_quick_setup(textile, retail, manuf, finance, logistics, healthcare, foodbev,
                                                lbs, kg, meters, pkr, usd, pieces):
                            """Generate system instructions from checkboxes."""
                            industries = []
                            if textile: industries.append("textile/fabric manufacturing")
                            if retail: industries.append("retail/e-commerce")
                            if manuf: industries.append("general manufacturing")
                            if finance: industries.append("finance/banking")
                            if logistics: industries.append("logistics/supply chain")
                            if healthcare: industries.append("healthcare")
                            if foodbev: industries.append("food & beverage")
                            
                            units = []
                            if lbs: units.append("LBS (pounds)")
                            if kg: units.append("KG (kilograms)")
                            if meters: units.append("meters/yards for length")
                            if pkr: units.append("PKR (Pakistani Rupee)")
                            if usd: units.append("USD (US Dollar)")
                            if pieces: units.append("pieces/units for counts")
                            
                            if not industries:
                                return "⚠️ Select at least one industry."
                            
                            instructions = f"# Domain Context\n\n"
                            instructions += f"This database supports {', '.join(industries)}.\n\n"
                            
                            if units:
                                instructions += f"## Common Units\n"
                                for u in units:
                                    instructions += f"- {u}\n"
                                instructions += "\n"
                            
                            instructions += "## Guidelines\n"
                            instructions += "- Use domain-specific terminology\n"
                            instructions += "- Prefer relevant metrics and KPIs\n"
                            instructions += "- Consider industry-standard calculations\n"
                            
                            try:
                                save_system_instructions(instructions)
                                return f"✅ **Domain Instructions Generated**\n\n```\n{instructions}\n```\n\nSaved to system instructions."
                            except Exception as e:
                                return f"❌ Error: {e}"
                        
                        quick_setup_btn.click(
                            generate_quick_setup,
                            inputs=[setup_textile, setup_retail, setup_manufacturing, setup_finance, 
                                   setup_logistics, setup_healthcare, setup_foodbev,
                                   unit_lbs, unit_kg, unit_meters, unit_pkr, unit_usd, unit_pieces],
                            outputs=[quick_setup_status]
                        )
                    
                    # Workflow 2: Manage Rules (Impact + Governance + Suggestions + Analytics combined)
                    with gr.Tab("📋 Manage Rules"):
                        gr.Markdown("""### Which Rules Actually Help?
See which rules have the most impact on your queries. Ranked by real usage.
""")
                        impact_display = gr.Markdown("Loading impact analysis...")
                        
                        def show_rule_impact():
                            try:
                                from src.quick_training import load_training_rules
                                data = load_training_rules()
                                rules = data.get("rules", [])
                                
                                if not rules:
                                    return "No rules yet. Create rules in 'Test This Rule' tab."
                                
                                # Filter and rank by usage
                                approved = [r for r in rules if r.get("status","draft") == "approved"]
                                approved.sort(key=lambda r: int(r.get("usage_count", 0)), reverse=True)
                                
                                if not approved:
                                    return "No approved rules yet. Test and save rules in the 'Test This Rule' tab."
                                
                                output = "### 🏆 Rule Performance Ranking\n\n"
                                output += "| Rank | Rule | Usage | Priority |\n"
                                output += "|------|------|-------|----------|\n"
                                
                                for i, r in enumerate(approved, 1):
                                    instr = (r.get("instruction", "") or "").strip()
                                    usage = int(r.get("usage_count", 0))
                                    priority = r.get("priority", 5)
                                    prio_label = "🔴 HIGH" if priority <= 3 else ("🟡 MED" if priority <= 7 else "🟢 LOW")
                                    
                                    # Create a progress bar
                                    bar_width = max(1, usage // 5)  # Scale: 5 usages = 1 unit
                                    bar = "█" * min(bar_width, 20)
                                    
                                    output += f"| {i} | {instr[:60]}... | {usage}x {bar} | {prio_label} |\n"
                                
                                output += "\n---\n\n"
                                output += "### 💡 Insights\n\n"
                                top_rule = approved[0]
                                top_usage = int(top_rule.get("usage_count", 0))
                                
                                if top_usage > 0:
                                    output += f"🌟 **Top Performer:** This rule has helped {top_usage} queries\n\n"
                                
                                total_usage = sum(int(r.get("usage_count", 0)) for r in approved)
                                output += f"📈 **Total Impact:** {total_usage} successful queries using your rules\n\n"
                                
                                avg_usage = total_usage / len(approved) if approved else 0
                                output += f"📊 **Average per Rule:** {avg_usage:.1f} uses\n\n"
                                
                                return output
                            except Exception as e:
                                logger.error(f"Impact display error: {e}", exc_info=True)
                                return f"❌ Error: {e}"
                        
                        demo.load(show_rule_impact, outputs=[impact_display])
                        
                        # Rule Governance section (integrated)
                        gr.Markdown("---")
                        gr.Markdown("### 🛡️ Rule Governance")
                        gr.Markdown("Manage rule lifecycle: owner, priority, status, and conflict detection.")
                        
                        gov_rules_md = gr.Markdown()
                        gov_select = gr.Dropdown(label="Select Rule #", choices=[], allow_custom_value=True, interactive=True)
                        owner_in = gr.Textbox(label="Owner", placeholder="e.g., ameer")
                        priority_in = gr.Slider(label="Priority (1=high, 10=low)", minimum=1, maximum=10, step=1, value=5)
                        status_in = gr.Dropdown(label="Status", choices=["draft", "approved", "deprecated"], value="draft")
                        
                        with gr.Row():
                            approve_btn2 = gr.Button("✅ Approve", variant="primary")
                            update_btn = gr.Button("💾 Update")
                            delete_btn = gr.Button("🗑️ Delete", variant="stop")
                        gov_msg = gr.Markdown()
                        
                        def _load_governance_rules():
                            data = load_training_rules()
                            rules = data.get("rules", [])
                            if not rules:
                                return "No rules yet.", []
                            md = "<div style=\"display:flex;flex-direction:column;gap:12px;\">"
                            choices = []
                            for idx, r in enumerate(rules, 1):
                                instr = (r.get('instruction','') or '')
                                status = r.get('status','draft')
                                owner = r.get('owner','')
                                prio = r.get('priority',5)
                                usage = int(r.get('usage_count',0))
                                md += (
                                    f"<div style=\"padding:12px 14px;border:1px solid #e9ecef;border-radius:10px;box-shadow:0 2px 6px rgba(0,0,0,0.06);\">"
                                    f"<div style=\"font-weight:600;color:#333;\">#{idx} · {instr[:120]}</div>"
                                    f"<div style=\"margin-top:6px;color:#555;\">Status: {status} · Priority: {prio} · Owner: {owner} · Usage: {usage}</div>"
                                    f"</div>"
                                )
                                choices.append(str(idx))
                            md += "</div>"
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
                                return f"❌ Invalid selection: {e}", gr.update(choices=[], value=None)
                            ok, msg = update_rule(idx, status="approved")
                            md, choices = _load_governance_rules()
                            return (f"{'✅ Approved' if ok else '❌ ' + msg}", gr.update(choices=choices, value=rule_no if ok else None))
                        
                        def _update_rule(rule_no: str, owner: str, priority: int, status: str):
                            try:
                                idx = int(rule_no)
                            except Exception as e:
                                return f"❌ Invalid selection: {e}", gr.update(choices=[], value=None)
                            ok, msg = update_rule(idx, owner=owner, priority=priority, status=status)
                            md, choices = _load_governance_rules()
                            return (f"{'✅ Updated' if ok else '❌ ' + msg}", gr.update(choices=choices, value=rule_no if ok else None))
                        
                        def _delete_rule(rule_no: str):
                            try:
                                idx = int(rule_no)
                            except Exception as e:
                                return f"❌ Invalid selection: {e}", gr.update(choices=[], value=None)
                            ok, msg = delete_rule(idx)
                            md, choices = _load_governance_rules()
                            return (msg, gr.update(choices=choices, value=None))
                        
                        gov_select.change(_populate_fields, inputs=[gov_select], outputs=[owner_in, priority_in, status_in])
                        approve_btn2.click(_approve_rule, inputs=[gov_select], outputs=[gov_msg, gov_select])
                        update_btn.click(_update_rule, inputs=[gov_select, owner_in, priority_in, status_in], outputs=[gov_msg, gov_select])
                        delete_btn.click(_delete_rule, inputs=[gov_select], outputs=[gov_msg, gov_select])
                        demo.load(_load_governance_rules, outputs=[gov_rules_md, gov_select])
                    
                    # Workflow 3: Domain Setup (Schema Analysis + Examples + Custom Instructions combined)
                    with gr.Tab("🏢 Domain Setup"):
                        gr.Markdown("### Configure Database Context")
                        gr.Markdown("Tell the AI about your database structure, domain, and business rules.")
                        
                        with gr.Tabs():
                            with gr.Tab("✏️ Custom Instructions"):
                                gr.Markdown("**Advanced:** Write custom system instructions for power users.")
                                domain_instructions_input = gr.Textbox(
                                    label="System Instructions",
                                    placeholder="Enter domain-specific guidance, terminology, calculation rules...",
                                    lines=15,
                                    value=load_system_instructions()
                                )
                                save_instructions_btn = gr.Button("💾 Save Instructions", variant="primary")
                                instructions_status = gr.Markdown("")
                                
                                def _save_instructions(text):
                                    ok = save_system_instructions(text)
                                    return "✅ Instructions saved!" if ok else "❌ Save failed"
                                
                                save_instructions_btn.click(_save_instructions, inputs=[domain_instructions_input], outputs=[instructions_status])
                            
                            with gr.Tab("🤖 AI Schema Analysis"):
                                gr.Markdown("**Auto-generate** system instructions by analyzing your database schema.")
                                schema_analyze_btn = gr.Button("🔍 Analyze Database Schema", variant="primary", size="lg")
                                schema_result = gr.Markdown("")
                                
                                def analyze_schema_auto():
                                    try:
                                        engine = get_engine()
                                        if not engine:
                                            return "❌ Database not connected. Check Settings tab."
                                        
                                        # Get schema info
                                        db = get_sql_database()
                                        if not db:
                                            return "❌ Failed to get database schema"
                                        
                                        schema_info = db.get_table_info()
                                        instructions = f"# Database Schema Context\n\n{schema_info}\n\n## Guidelines\n- Use the tables and columns described above\n- Follow naming conventions observed in schema\n- Consider relationships between tables\n"
                                        save_system_instructions(instructions)
                                        
                                        return f"✅ **Schema Analyzed & Saved**\n\n```\n{instructions[:500]}...\n```\n\nFull instructions saved."
                                    except Exception as e:
                                        logger.error(f"Schema analysis error: {e}", exc_info=True)
                                        return f"❌ Error: {e}"
                                
                                schema_analyze_btn.click(analyze_schema_auto, outputs=[schema_result])
                            
                            with gr.Tab("📝 AI Example Queries"):
                                gr.Markdown("**Auto-generate** sample queries based on your schema.")
                                examples_btn = gr.Button("✨ Generate Examples", variant="primary", size="lg")
                                examples_result = gr.Markdown("")
                                
                                def generate_examples_auto():
                                    try:
                                        engine = get_engine()
                                        if not engine:
                                            return "❌ Database not connected."
                                        
                                        db = get_sql_database()
                                        if not db:
                                            return "❌ Failed to get database schema"
                                        
                                        schema_info = db.get_table_info()
                                        output = "# Auto-Generated Schema Reference\n\n"
                                        output += "Use this schema information to generate example queries:\n\n"
                                        output += f"```\n{schema_info}\n```\n\n"
                                        output += "**Suggested workflow:**\n"
                                        output += "1. Review the schema above\n"
                                        output += "2. Identify key tables and relationships\n"
                                        output += "3. Create example queries in the Chat tab\n"
                                        output += "4. Test and save successful patterns as training rules\n"
                                        
                                        # Save to file
                                        with open("auto_generated_examples.md", "w") as f:
                                            f.write(output)
                                        
                                        return f"✅ **Schema Reference Generated**\n\n{output[:600]}...\n\nSaved to `auto_generated_examples.md`"
                                    except Exception as e:
                                        logger.error(f"Example generation error: {e}", exc_info=True)
                                        return f"❌ Error: {e}"
                                
                                examples_btn.click(generate_examples_auto, outputs=[examples_result])
                    
                    # =========================================================================
                    # Phase 1: New Training Sub-Tabs
                    # =========================================================================
                    
                    # Import Report (CSV Upload & Analysis)
                    with gr.Tab("📥 Import Report"):
                        gr.Markdown("### Import Report from CSV")
                        gr.Markdown("Upload a CSV report file and let AI analyze it to create a reusable SQL template.")
                        
                        with gr.Row():
                            with gr.Column(scale=2):
                                import_csv_file = gr.File(
                                    label="Upload CSV Report",
                                    file_types=[".csv"],
                                    file_count="single"
                                )
                                import_report_name = gr.Textbox(
                                    label="Report Name",
                                    placeholder="e.g., Monthly Sales Summary"
                                )
                                import_report_desc = gr.Textbox(
                                    label="Description",
                                    placeholder="What does this report show?",
                                    lines=2
                                )
                            with gr.Column(scale=1):
                                gr.Markdown("**Instructions:**")
                                gr.Markdown("""
1. Upload a CSV file containing sample report data
2. AI will analyze columns and suggest SQL
3. Review and edit the suggested SQL
4. Save as a reusable template
""")
                        
                        analyze_csv_btn = gr.Button("🔍 Analyze CSV", variant="primary", size="lg")
                        
                        gr.Markdown("---")
                        gr.Markdown("### Analysis Results")
                        
                        csv_analysis_md = gr.Markdown("")
                        suggested_sql_box = gr.Textbox(
                            label="Suggested SQL Template",
                            placeholder="AI will generate SQL based on your CSV...",
                            lines=8,
                            interactive=True
                        )
                        sample_questions_box = gr.Textbox(
                            label="Sample Questions (one per line)",
                            placeholder="Questions that would trigger this report...",
                            lines=3
                        )
                        import_category = gr.Dropdown(
                            label="Category",
                            choices=["Sales", "Inventory", "Finance", "Reports", "General"],
                            value="Reports"
                        )
                        
                        with gr.Row():
                            save_as_template_btn = gr.Button("💾 Save as Template", variant="primary")
                            clear_import_btn = gr.Button("🔄 Clear", variant="secondary")
                        
                        import_status_md = gr.Markdown("")
                        
                        # Hidden state to store analysis result
                        csv_analysis_state = gr.State({})
                        
                        def _analyze_csv_report(file, report_name):
                            """Analyze uploaded CSV and suggest SQL."""
                            if file is None:
                                return "❌ Please upload a CSV file first", "", {}, ""
                            
                            try:
                                import pandas as pd
                                
                                # Read CSV
                                df = pd.read_csv(file.name)
                                
                                # Basic analysis
                                columns = list(df.columns)
                                row_count = len(df)
                                dtypes = df.dtypes.to_dict()
                                
                                # Sample data
                                sample_rows = df.head(5).to_dict('records')
                                
                                # Build analysis summary
                                analysis_md = f"""### 📊 CSV Analysis

**File:** {file.name.split('/')[-1]}  
**Rows:** {row_count}  
**Columns:** {len(columns)}

| Column | Type | Sample Values |
|--------|------|---------------|
"""
                                for col in columns[:15]:  # Limit to 15 columns
                                    dtype = str(dtypes.get(col, 'unknown'))
                                    samples = df[col].dropna().head(3).tolist()
                                    sample_str = ", ".join(str(s)[:20] for s in samples)
                                    analysis_md += f"| {col} | {dtype} | {sample_str} |\n"
                                
                                if len(columns) > 15:
                                    analysis_md += f"\n*...and {len(columns) - 15} more columns*\n"
                                
                                # Use LLM to suggest SQL
                                global current_llm, current_provider
                                if current_llm is None:
                                    config = load_config()
                                    llm_config = config.get('llm', {})
                                    provider_name = llm_config.get('provider', 'openai')
                                    model = llm_config.get('model', 'gpt-4o-mini')
                                    current_provider = create_provider(provider_name)
                                    current_llm = current_provider.get_llm(model, 0.3, 2000)
                                
                                # Get database schema for context
                                db = get_sql_database()
                                schema = db.get_table_info() if db else "Schema unavailable"
                                
                                prompt = f"""Analyze this CSV report and suggest a SQL query that would generate similar data.

CSV Columns: {columns}
Sample Data: {sample_rows[:3]}
Report Name: {report_name or 'Unnamed Report'}

Database Schema:
{schema[:3000]}

Generate a SQL Server query that would produce data similar to this CSV.
Consider:
1. Which tables likely contain this data
2. Any JOINs needed
3. Appropriate WHERE clauses
4. ORDER BY for sorting

Return ONLY the SQL query, no explanation."""

                                response = current_llm.invoke(prompt)
                                suggested_sql = response.content if hasattr(response, 'content') else str(response)
                                suggested_sql = suggested_sql.strip().replace("```sql", "").replace("```", "").strip()
                                
                                # Generate sample questions
                                questions_prompt = f"""Based on this report structure, suggest 3 natural language questions a user might ask to get this data:

Report: {report_name or 'Report'}
Columns: {columns[:10]}

Return just the questions, one per line."""

                                q_response = current_llm.invoke(questions_prompt)
                                sample_questions = q_response.content if hasattr(q_response, 'content') else ""
                                
                                state = {
                                    "columns": columns,
                                    "row_count": row_count,
                                    "suggested_sql": suggested_sql,
                                    "file_name": file.name
                                }
                                
                                return analysis_md, suggested_sql, state, sample_questions.strip()
                                
                            except Exception as e:
                                logger.error(f"CSV analysis error: {e}", exc_info=True)
                                return f"❌ Error analyzing CSV: {e}", "", {}, ""
                        
                        def _save_csv_as_template(name, desc, sql, questions, category, state):
                            """Save analyzed CSV as a report template."""
                            if not name:
                                return "❌ Please enter a report name"
                            if not sql:
                                return "❌ No SQL to save. Analyze a CSV first."
                            
                            try:
                                from src.report_templates import get_template_manager, ReportTemplate
                                manager = get_template_manager()
                                
                                question_list = [q.strip() for q in questions.split("\n") if q.strip()]
                                
                                template = ReportTemplate(
                                    name=name,
                                    description=desc,
                                    sql_template=sql,
                                    sample_questions=question_list,
                                    category=category,
                                    source="imported"
                                )
                                
                                success, msg = manager.add_template(template)
                                
                                if success:
                                    return f"✅ Template '{name}' saved successfully! Find it in the Report Library tab."
                                else:
                                    return f"❌ {msg}"
                            except Exception as e:
                                return f"❌ Error saving template: {e}"
                        
                        def _clear_import():
                            return None, "", "", "", "", "Reports", {}, ""
                        
                        analyze_csv_btn.click(
                            _analyze_csv_report,
                            inputs=[import_csv_file, import_report_name],
                            outputs=[csv_analysis_md, suggested_sql_box, csv_analysis_state, sample_questions_box]
                        )
                        
                        save_as_template_btn.click(
                            _save_csv_as_template,
                            inputs=[import_report_name, import_report_desc, suggested_sql_box, sample_questions_box, import_category, csv_analysis_state],
                            outputs=[import_status_md]
                        )
                        
                        clear_import_btn.click(
                            _clear_import,
                            outputs=[import_csv_file, import_report_name, import_report_desc, csv_analysis_md, suggested_sql_box, import_category, csv_analysis_state, import_status_md]
                        )
                    
                    # Report Library (Template Management)
                    with gr.Tab("📚 Report Library"):
                        gr.Markdown("### Pre-defined Report Templates")
                        gr.Markdown("Browse, create, and manage SQL templates for common queries.")
                        
                        template_list_md = gr.Markdown("Loading templates...")
                        
                        with gr.Row():
                            template_category_filter = gr.Dropdown(
                                label="Filter by Category",
                                choices=["All", "Sales", "Inventory", "Finance", "Reports", "General"],
                                value="All"
                            )
                            template_refresh_btn = gr.Button("🔄 Refresh", size="sm")
                        
                        gr.Markdown("---")
                        gr.Markdown("### Add New Template")
                        
                        with gr.Row():
                            with gr.Column():
                                new_template_name = gr.Textbox(label="Template Name", placeholder="e.g., Top Sales Report")
                                new_template_desc = gr.Textbox(label="Description", placeholder="What this template does...")
                                new_template_category = gr.Dropdown(
                                    label="Category",
                                    choices=["Sales", "Inventory", "Finance", "Reports", "General"],
                                    value="General"
                                )
                            with gr.Column():
                                new_template_sql = gr.Textbox(
                                    label="SQL Template",
                                    placeholder="SELECT TOP {top_n} * FROM Sales ORDER BY Amount DESC",
                                    lines=5
                                )
                                new_template_samples = gr.Textbox(
                                    label="Sample Questions (one per line)",
                                    placeholder="show top 10 sales\ntop sales by amount",
                                    lines=3
                                )
                        
                        add_template_btn = gr.Button("➕ Add Template", variant="primary")
                        template_action_msg = gr.Markdown("")
                        
                        def _load_template_list(category: str = "All"):
                            try:
                                from src.report_templates import get_template_manager
                                manager = get_template_manager()
                                
                                templates = manager.get_all_templates(
                                    category=category if category != "All" else None
                                )
                                
                                if not templates:
                                    return "No templates yet. Add one below!"
                                
                                output = "| Name | Category | Usage | Sample Question |\n"
                                output += "|------|----------|-------|----------------|\n"
                                
                                for t in templates[:20]:  # Limit display
                                    sample = t.sample_questions[0] if t.sample_questions else "-"
                                    output += f"| {t.name} | {t.category} | {t.use_count}x | {sample[:40]} |\n"
                                
                                stats = manager.get_statistics()
                                output += f"\n\n**Total:** {stats['total']} templates | **Total Uses:** {stats['total_uses']}"
                                
                                return output
                            except Exception as e:
                                logger.error(f"Template list error: {e}", exc_info=True)
                                return f"❌ Error loading templates: {e}"
                        
                        def _add_template(name, desc, category, sql, samples):
                            if not name or not sql:
                                return "❌ Name and SQL are required"
                            
                            try:
                                from src.report_templates import get_template_manager, ReportTemplate
                                manager = get_template_manager()
                                
                                sample_list = [s.strip() for s in samples.split("\n") if s.strip()] if samples else []
                                
                                template = ReportTemplate(
                                    name=name,
                                    description=desc,
                                    sql_template=sql,
                                    sample_questions=sample_list,
                                    category=category
                                )
                                
                                success, msg = manager.add_template(template)
                                return f"✅ {msg}" if success else f"❌ {msg}"
                            except Exception as e:
                                return f"❌ Error: {e}"
                        
                        template_category_filter.change(_load_template_list, inputs=[template_category_filter], outputs=[template_list_md])
                        template_refresh_btn.click(_load_template_list, inputs=[template_category_filter], outputs=[template_list_md])
                        add_template_btn.click(
                            _add_template,
                            inputs=[new_template_name, new_template_desc, new_template_category, new_template_sql, new_template_samples],
                            outputs=[template_action_msg]
                        )
                        demo.load(_load_template_list, outputs=[template_list_md])
                    
                    # Correction Queue (IT Approval Workflow)
                    with gr.Tab("🔧 Correction Queue"):
                        gr.Markdown("### SQL Correction Requests")
                        gr.Markdown("Review and approve user-submitted SQL corrections. Approved corrections become training rules.")
                        
                        correction_stats_md = gr.Markdown("")
                        correction_list_md = gr.Markdown("Loading corrections...")
                        
                        with gr.Row():
                            correction_status_filter = gr.Dropdown(
                                label="Filter by Status",
                                choices=["All", "Pending", "Approved", "Rejected"],
                                value="Pending"
                            )
                            correction_refresh_btn = gr.Button("🔄 Refresh", size="sm")
                        
                        gr.Markdown("---")
                        gr.Markdown("### Review Correction")
                        
                        correction_select = gr.Dropdown(label="Select Correction ID", choices=[], interactive=True)
                        
                        with gr.Row():
                            with gr.Column():
                                corr_original_q = gr.Textbox(label="Original Question", interactive=False)
                                corr_original_sql = gr.Textbox(label="Original SQL", lines=3, interactive=False)
                            with gr.Column():
                                corr_suggested_sql = gr.Textbox(label="Suggested SQL", lines=3, interactive=False)
                                corr_user_notes = gr.Textbox(label="User Notes", interactive=False)
                        
                        corr_reviewer_notes = gr.Textbox(label="Reviewer Notes", placeholder="Add notes for approval/rejection...")
                        corr_create_rule = gr.Checkbox(label="Create training rule from this correction", value=True)
                        
                        with gr.Row():
                            corr_approve_btn = gr.Button("✅ Approve", variant="primary")
                            corr_reject_btn = gr.Button("❌ Reject", variant="stop")
                        
                        correction_action_msg = gr.Markdown("")
                        
                        def _load_correction_stats():
                            try:
                                from src.correction_workflow import get_correction_workflow
                                workflow = get_correction_workflow()
                                stats = workflow.get_statistics()
                                
                                return (
                                    f"📊 **Stats:** {stats['pending']} pending | "
                                    f"{stats['approved']} approved | {stats['rejected']} rejected | "
                                    f"{stats['approval_rate']}% approval rate"
                                )
                            except Exception as e:
                                return f"❌ Error: {e}"
                        
                        def _load_corrections(status_filter: str = "Pending"):
                            try:
                                from src.correction_workflow import get_correction_workflow, CorrectionStatus
                                workflow = get_correction_workflow()
                                
                                status_map = {
                                    "Pending": CorrectionStatus.PENDING,
                                    "Approved": CorrectionStatus.APPROVED,
                                    "Rejected": CorrectionStatus.REJECTED,
                                    "All": None
                                }
                                
                                requests = workflow.get_all_requests(
                                    status_filter=status_map.get(status_filter)
                                )
                                
                                if not requests:
                                    return "No corrections found.", []
                                
                                output = "| ID | Question | Status | Date |\n"
                                output += "|------|----------|--------|------|\n"
                                
                                choices = []
                                for r in requests[:20]:
                                    q_short = r.original_question[:40] + "..." if len(r.original_question) > 40 else r.original_question
                                    date_short = r.created_at[:10] if r.created_at else "-"
                                    output += f"| {r.request_id} | {q_short} | {r.status.value} | {date_short} |\n"
                                    choices.append(r.request_id)
                                
                                return output, choices
                            except Exception as e:
                                logger.error(f"Correction list error: {e}", exc_info=True)
                                return f"❌ Error: {e}", []
                        
                        def _populate_correction(req_id: str):
                            if not req_id:
                                return "", "", "", ""
                            try:
                                from src.correction_workflow import get_correction_workflow
                                workflow = get_correction_workflow()
                                req = workflow.get_request(req_id)
                                
                                if not req:
                                    return "", "", "", ""
                                
                                return req.original_question, req.original_sql, req.suggested_sql, req.user_notes
                            except:
                                return "", "", "", ""
                        
                        def _approve_correction(req_id: str, notes: str, create_rule: bool):
                            if not req_id:
                                return "❌ Select a correction first"
                            try:
                                from src.correction_workflow import get_correction_workflow
                                workflow = get_correction_workflow()
                                success, msg = workflow.approve_request(req_id, notes, create_training_rule=create_rule)
                                return f"✅ {msg}" if success else f"❌ {msg}"
                            except Exception as e:
                                return f"❌ Error: {e}"
                        
                        def _reject_correction(req_id: str, notes: str):
                            if not req_id:
                                return "❌ Select a correction first"
                            try:
                                from src.correction_workflow import get_correction_workflow
                                workflow = get_correction_workflow()
                                success, msg = workflow.reject_request(req_id, notes)
                                return f"✅ {msg}" if success else f"❌ {msg}"
                            except Exception as e:
                                return f"❌ Error: {e}"
                        
                        correction_status_filter.change(
                            _load_corrections,
                            inputs=[correction_status_filter],
                            outputs=[correction_list_md, correction_select]
                        )
                        correction_refresh_btn.click(
                            _load_corrections,
                            inputs=[correction_status_filter],
                            outputs=[correction_list_md, correction_select]
                        )
                        correction_select.change(
                            _populate_correction,
                            inputs=[correction_select],
                            outputs=[corr_original_q, corr_original_sql, corr_suggested_sql, corr_user_notes]
                        )
                        corr_approve_btn.click(
                            _approve_correction,
                            inputs=[correction_select, corr_reviewer_notes, corr_create_rule],
                            outputs=[correction_action_msg]
                        )
                        corr_reject_btn.click(
                            _reject_correction,
                            inputs=[correction_select, corr_reviewer_notes],
                            outputs=[correction_action_msg]
                        )
                        demo.load(_load_correction_stats, outputs=[correction_stats_md])
                        demo.load(lambda: _load_corrections("Pending"), outputs=[correction_list_md, correction_select])
                    
                    # Domain Knowledge (Entity Management)
                    with gr.Tab("🧠 Domain Knowledge"):
                        gr.Markdown("### Learned Entities & Aliases")
                        gr.Markdown("Manage domain-specific terminology, aliases, and business entities.")
                        
                        domain_stats_md = gr.Markdown("")
                        entity_list_md = gr.Markdown("Loading entities...")
                        
                        with gr.Row():
                            entity_type_filter = gr.Dropdown(
                                label="Filter by Type",
                                choices=["All", "customer", "product", "location", "category", "other"],
                                value="All"
                            )
                            entity_refresh_btn = gr.Button("🔄 Refresh", size="sm")
                        
                        gr.Markdown("---")
                        gr.Markdown("### Add New Entity")
                        
                        with gr.Row():
                            with gr.Column():
                                new_entity_name = gr.Textbox(label="Canonical Name", placeholder="e.g., Acme Corp")
                                new_entity_type = gr.Dropdown(
                                    label="Entity Type",
                                    choices=["customer", "product", "location", "category", "other"],
                                    value="other"
                                )
                                new_entity_sql_value = gr.Textbox(label="SQL Value", placeholder="Value to use in queries")
                            with gr.Column():
                                new_entity_aliases = gr.Textbox(
                                    label="Aliases (one per line)",
                                    placeholder="ACME\nacme corporation\nacme inc",
                                    lines=3
                                )
                                new_entity_desc = gr.Textbox(label="Description", placeholder="Optional description...")
                        
                        add_entity_btn = gr.Button("➕ Add Entity", variant="primary")
                        entity_action_msg = gr.Markdown("")
                        
                        def _load_domain_stats():
                            try:
                                from src.domain_knowledge import get_domain_manager
                                manager = get_domain_manager()
                                stats = manager.get_statistics()
                                
                                type_counts = " | ".join([f"{k}: {v}" for k, v in stats.get('by_type', {}).items()])
                                
                                return (
                                    f"📊 **{stats['total_entities']} entities** | "
                                    f"{stats['total_aliases']} aliases | "
                                    f"{stats['total_matches']} matches\n\n"
                                    f"**By Type:** {type_counts or 'None'}"
                                )
                            except Exception as e:
                                return f"❌ Error: {e}"
                        
                        def _load_entities(type_filter: str = "All"):
                            try:
                                from src.domain_knowledge import get_domain_manager
                                manager = get_domain_manager()
                                
                                entities = manager.get_all_entities(
                                    entity_type=type_filter if type_filter != "All" else None
                                )
                                
                                if not entities:
                                    return "No entities yet. Add one below!"
                                
                                output = "| Name | Type | Aliases | Matches |\n"
                                output += "|------|------|---------|--------|\n"
                                
                                for e in entities[:20]:
                                    aliases_str = ", ".join(e.aliases[:3]) + ("..." if len(e.aliases) > 3 else "")
                                    output += f"| {e.canonical_name} | {e.entity_type} | {aliases_str} | {e.match_count}x |\n"
                                
                                return output
                            except Exception as e:
                                logger.error(f"Entity list error: {e}", exc_info=True)
                                return f"❌ Error: {e}"
                        
                        def _add_entity(name, etype, sql_val, aliases, desc):
                            if not name:
                                return "❌ Name is required"
                            
                            try:
                                from src.domain_knowledge import get_domain_manager, DomainEntity
                                manager = get_domain_manager()
                                
                                alias_list = [a.strip() for a in aliases.split("\n") if a.strip()] if aliases else []
                                
                                entity = DomainEntity(
                                    canonical_name=name,
                                    entity_type=etype,
                                    sql_value=sql_val or name,
                                    aliases=alias_list,
                                    description=desc
                                )
                                
                                success, msg = manager.add_entity(entity)
                                return f"✅ {msg}" if success else f"❌ {msg}"
                            except Exception as e:
                                return f"❌ Error: {e}"
                        
                        entity_type_filter.change(_load_entities, inputs=[entity_type_filter], outputs=[entity_list_md])
                        entity_refresh_btn.click(_load_entities, inputs=[entity_type_filter], outputs=[entity_list_md])
                        add_entity_btn.click(
                            _add_entity,
                            inputs=[new_entity_name, new_entity_type, new_entity_sql_value, new_entity_aliases, new_entity_desc],
                            outputs=[entity_action_msg]
                        )
                        demo.load(_load_domain_stats, outputs=[domain_stats_md])
                        demo.load(_load_entities, outputs=[entity_list_md])
            
            # Developer Tab (merged from Developer Tools + Developer Settings)
            with gr.Tab("🛠️ Developer"):
                gr.Markdown("## Developer Tools & Configuration")
                gr.Markdown("Session monitoring, diagnostics, and observability settings.")
                
                # Sub-tab 1: Session & Cache
                with gr.Tab("📊 Session & Cache"):
                    with gr.Row():
                        with gr.Column(scale=1):
                            gr.Markdown("### Session Summary")
                            
                            session_summary = gr.Markdown("Loading session data...")
                            
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
                            
                            # Cache Statistics Section
                            gr.Markdown("---")
                            gr.Markdown("### Cache Performance")
                            cache_stats_display = gr.Markdown("Loading cache stats...")
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
                            
                            clear_cache_btn.click(clear_cache_action, outputs=[cache_action_status])
                            
                            # Feedback Analytics Section
                            gr.Markdown("---")
                            gr.Markdown("### Feedback Analytics")
                            
                            feedback_stats_display = gr.Markdown("No feedback data yet.")
                            recent_feedback_display = gr.Markdown("")
                            
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
                            
                            # Auto-load all session data on page load
                            demo.load(get_current_session_summary, outputs=[session_summary])
                            demo.load(show_cache_stats, outputs=[cache_stats_display])
                            demo.load(show_feedback_analytics, outputs=[feedback_stats_display, recent_feedback_display])
                
                with gr.Tab("📦 Diagnostics & Export"):
                    gr.Markdown("### Export Options")
                    gr.Markdown("Choose the right export for your needs: Quick session report or comprehensive diagnostic bundle.")
                    
                    with gr.Row():
                        with gr.Column(scale=1):
                            gr.Markdown("#### 📤 Session Report")
                            gr.Markdown("Export current session for Copilot analysis (queries, errors, recommendations).")
                            export_session_btn = gr.Button("📤 Export Session", variant="secondary", size="lg")
                            export_status = gr.Markdown("")
                            export_file_download = gr.File(label="Download Session Report", visible=False)
                    
                            def export_session_report():
                                """Export session report for quick Copilot sharing."""
                                try:
                                    report_path = session_tracker.export_for_copilot()
                                    if report_path:
                                        return (
                                            f"✅ **Session Report Exported**\n\nFile: `{report_path}`\n\nDownload below and share with Copilot for analysis.",
                                            report_path,
                                            gr.update(visible=True)
                                        )
                                    else:
                                        return "❌ Export failed", None, gr.update(visible=False)
                                except Exception as e:
                                    return f"❌ Error: {str(e)}", None, gr.update(visible=False)
                            
                            export_session_btn.click(export_session_report, outputs=[export_status, export_file_download, export_file_download])
                        
                        with gr.Column(scale=1):
                            gr.Markdown("#### 🔍 Full Diagnostic Bundle")
                            gr.Markdown("Complete package: session + config + logs + training data + environment snapshot.")
                            diagnostics_btn = gr.Button("🔍 Collect Full Diagnostics", variant="primary", size="lg")
                            diagnostics_status = gr.Markdown("")
                            diagnostics_download = gr.File(label="Download Diagnostics Bundle", visible=False)
                            
                            def collect_full_diagnostics():
                                """Collect comprehensive diagnostic bundle."""
                                try:
                                    bundle_path = collect_full_session_bundle(include_sensitive=True)
                                    if bundle_path:
                                        return (
                                            f"✅ **Diagnostic Bundle Created**\n\nBundle: `{bundle_path}`\n\nIncludes: session data, logs, config, training rules, DB snapshot, environment info.",
                                            bundle_path,
                                            gr.update(visible=True)
                                        )
                                    else:
                                        # Fallback to basic diagnostics
                                        basic_path = collect_diagnostics()
                                        return (
                                            f"⚠️ **Basic Diagnostics Collected**\n\nFile: `{basic_path}`\n\n(Full bundle unavailable, using text report)",
                                            basic_path,
                                            gr.update(visible=True)
                                        )
                                except Exception as e:
                                    return f"❌ Error: {str(e)}", None, gr.update(visible=False)
                            
                            diagnostics_btn.click(collect_full_diagnostics, outputs=[diagnostics_status, diagnostics_download, diagnostics_download])
                    
                    gr.Markdown("---")
                    gr.Markdown("### 💡 Usage Guide")
                    gr.Markdown("""
**When to use Session Report:**
- Quick bug reports to Copilot
- Sharing recent query issues
- Performance questions

**When to use Full Diagnostics:**
- Connection/configuration problems
- Training/learning issues  
- System-wide debugging
- Comprehensive troubleshooting
""")

                # Sub-tab 3: Observability Config
                with gr.Tab("⚙️ Observability Config"):
                    gr.Markdown("### Configure Monitoring & Telemetry")
                    
                    with gr.Row():
                        with gr.Column(scale=1):
                            gr.Markdown("#### Observability Tiers")
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
**💡 Enable Developer Mode when:**
- ❌ Wrong results or unexpected behavior
- 🐌 Slow performance issues
- 🤔 Need to see AI reasoning and prompts
- 🐛 Debugging complex problems
""")
                        
                        with gr.Column(scale=1):
                            gr.Markdown("#### Quick Actions")
                            gr.Markdown("Common developer workflows and shortcuts.")
                            
                            clear_session_btn = gr.Button("🔄 Reset Current Session", size="sm")
                            session_reset_status = gr.Markdown("")
                            
                            def reset_current_session():
                                try:
                                    reset_session_tracker()
                                    return "✅ Session reset successfully! New session ID assigned."
                                except Exception as e:
                                    return f"❌ Error: {str(e)}"
                            
                            clear_session_btn.click(reset_current_session, outputs=[session_reset_status])


    
    return demo

if __name__ == "__main__":
    demo = build_ui()
    demo.launch(theme=gr.themes.Default())
