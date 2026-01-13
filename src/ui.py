"""
Gradio UI for DBAI Application
Provides a multi-tab interface for chat, settings, training, data import, and diagnostics.
"""
import logging
import os
import io
import uuid
from typing import List, Optional, Tuple
from datetime import datetime
import gradio as gr
import yaml
from pathlib import Path
from dotenv import load_dotenv, set_key
import copy

from src.providers import create_provider
from src.database import reload_engine, get_engine, run_query, get_sql_database, load_metadata, save_metadata
from src.llm import make_sql_chain, make_describe_chain, extract_sql_from_response, validate_sql
from src.query_validator import validate_query_and_results, ResultsQualityChecker
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
from src.training_module import (
    get_training_manager, TrainingExample, CATEGORY_OPTIONS, COMPLEXITY_LEVELS
)

# Version tracking - increment by 5 for each significant update
UI_BUILD_VERSION = 26
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
        # Do not persist plaintext secrets in config for demo: mask DB password and keep it in process env
        cfg_copy = dict(config)
        db_cfg = cfg_copy.get('database', {})
        passwd = db_cfg.get('password') if isinstance(db_cfg, dict) else None
        if passwd:
            try:
                # Keep password only in process env for the demo session
                os.environ['DBAI_DB_PASSWORD'] = str(passwd)
            except Exception:
                pass
            # Mask the value written to config file
            if isinstance(db_cfg, dict):
                cfg_copy['database'] = dict(db_cfg)
                cfg_copy['database']['password'] = '***REDACTED***'

        with open(config_path, 'w') as f:
            yaml.dump(cfg_copy, f, default_flow_style=False)
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
    if pending_clarification["question"]:
        # Extract number from input like "1", "1.", "1)", "(1)", etc.
        import re
        match = re.match(r'^\s*[\(\[]?\s*(\d+)\s*[\.\)\]\s]*\s*$', question.strip())
        if match:
            choice_num = int(match.group(1))
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
            return "", history, message_id, response
        
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
        
        # QUALITY CHECK: Validate results integrity if query succeeded
        if success and isinstance(result, dict) and 'rows' in result:
            try:
                results_rows = result.get('rows', [])
                validation_report = validate_query_and_results(sql_query, results_rows, question)
                
                # Log validation findings
                if validation_report["issues"]:
                    logger.warning(f"Result validation issues: {validation_report['issues']}")
                if validation_report["warnings"]:
                    logger.info(f"Result validation warnings: {validation_report['warnings']}")
                
                # If critical issues found, flag the result
                if validation_report["issues"]:
                    success = False
                    result = {
                        "error": f"⚠️ Data quality concerns detected:\n\n" + "\n".join(validation_report["issues"]) + 
                                "\n\nPlease review the query or contact support."
                    }
                    execution_data["success"] = False
                    execution_data["validation_issues"] = validation_report["issues"]
                elif validation_report["warnings"]:
                    # Log warnings but don't fail - show them to user in response
                    execution_data["validation_warnings"] = validation_report["warnings"]
            except Exception as e:
                logger.error(f"Validation check failed: {e}")
                # Don't fail the query if validation fails, just log it
        
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
            
            # Add validation warnings if any
            if execution_data.get("validation_warnings"):
                warnings_text = "\n".join([f"⚠️ {w}" for w in execution_data["validation_warnings"]])
                response += f"**Data Quality Notices:**\n{warnings_text}\n\n"
            
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


def session_chat_query(question: str, history: List, persona: str, session_state: dict):
    """Wrapper to provide per-session isolation for globals during chat handling.

    The wrapper copies relevant session-scoped variables into module globals,
    calls the main `chat_query`, and then writes the updated globals back
    into the session_state object for persistence.
    """
    global pending_clarification, session_tokens, last_query_info, last_query_result_data, training_mode_enabled, auto_chart_enabled

    # Initialize session container
    s = session_state or {}

    # Load session values into globals (use shallow copy to avoid aliasing)
    try:
        pending_clarification = copy.deepcopy(s.get("pending_clarification", pending_clarification))
        session_tokens = copy.deepcopy(s.get("session_tokens", session_tokens))
        last_query_info = copy.deepcopy(s.get("last_query_info", last_query_info))
        last_query_result_data = s.get("last_query_result_data", last_query_result_data)
        training_mode_enabled = s.get("training_mode_enabled", training_mode_enabled)
        auto_chart_enabled = s.get("auto_chart_enabled", auto_chart_enabled)
    except Exception:
        # If anything goes wrong, proceed with existing globals
        pass

    # Call the primary chat handler
    input_val, updated_history, message_id, response_text = chat_query(question, history, persona)

    # Persist back into session_state
    try:
        new_state = {
            "pending_clarification": copy.deepcopy(pending_clarification),
            "session_tokens": copy.deepcopy(session_tokens),
            "last_query_info": copy.deepcopy(last_query_info),
            "last_query_result_data": last_query_result_data,
            "training_mode_enabled": training_mode_enabled,
            "auto_chart_enabled": auto_chart_enabled
        }
    except Exception:
        new_state = session_state or {}

    return input_val, updated_history, message_id, response_text, new_state

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
                    teach_me_btn = gr.Button("📚 Teach Me", size="sm", variant="secondary", scale=1, visible=False)
                
                # Teach Me dialog (for schema mapping corrections)
                teach_me_dialog = gr.Markdown("", visible=False)
                with gr.Row(visible=False) as teach_me_row:
                    teach_me_term = gr.Textbox(
                        label="What did you mean?",
                        placeholder='e.g., "customers" or "customer name"',
                        scale=2
                    )
                    teach_me_table = gr.Dropdown(
                        label="Table",
                        choices=[],
                        scale=1
                    )
                    teach_me_column = gr.Dropdown(
                        label="Column",
                        choices=[],
                        scale=1
                    )
                    teach_me_save_btn = gr.Button("💾 Save Mapping", variant="primary", scale=1)
                teach_me_status = gr.Markdown("")
                
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
                session_state = gr.State({})
                
                # Handle button click
                send_stop_btn.click(
                    lambda: (gr.update(value="⏹ Stop", variant="stop"), True),
                    outputs=[send_stop_btn, is_running]
                ).then(
                    session_chat_query,
                    inputs=[question_input, chatbot, persona_selector, session_state],
                    outputs=[question_input, chatbot, current_message_id, last_response_text, session_state]
                ).then(
                    lambda: (False, gr.update(value="Send ▶", variant="primary")),
                    outputs=[is_running, send_stop_btn]
                )
                
                question_input.submit(
                    lambda: (gr.update(value="⏹ Stop", variant="stop"), True),
                    outputs=[send_stop_btn, is_running]
                ).then(
                    session_chat_query,
                    inputs=[question_input, chatbot, persona_selector, session_state],
                    outputs=[question_input, chatbot, current_message_id, last_response_text, session_state]
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
                
                # Teach Me functionality
                def show_teach_me_dialog(msg_id):
                    """Show teach me dialog when user clicks Teach Me button."""
                    if not msg_id or msg_id == "":
                        return (
                            gr.update(visible=False),
                            gr.update(visible=False),
                            gr.update(visible=False),
                            gr.update(visible=False),
                            gr.update(choices=[]),
                            gr.update(choices=[])
                        )
                    
                    try:
                        from src.database import get_engine
                        from src.schema_discovery import discover_tables, discover_columns
                        
                        engine = get_engine()
                        if engine:
                            tables = discover_tables(engine)
                            return (
                                gr.update(visible=True, value="**What should I call this?**\n\nEnter the term you used and select the correct table/column."),
                                gr.update(visible=True),
                                gr.update(visible=True),
                                gr.update(visible=True),
                                gr.update(choices=tables),
                                gr.update(choices=[])
                            )
                    except:
                        pass
                    
                    return (
                        gr.update(visible=True, value="⚠️ Database connection required. Please configure in Settings first."),
                        gr.update(visible=True),
                        gr.update(visible=False),
                        gr.update(visible=False),
                        gr.update(choices=[]),
                        gr.update(choices=[])
                    )
                
                def update_teach_me_columns(table_name):
                    """Update column dropdown when table is selected."""
                    try:
                        from src.database import get_engine
                        from src.schema_discovery import discover_columns
                        
                        engine = get_engine()
                        if engine and table_name:
                            columns = discover_columns(engine, table_name)
                            column_names = [col["name"] for col in columns]
                            return gr.update(choices=column_names)
                        return gr.update(choices=[])
                    except:
                        return gr.update(choices=[])
                
                def save_teach_me_mapping(term, table, column):
                    """Save the mapping from teach me dialog."""
                    if not term.strip():
                        return "❌ Please enter what you meant.", gr.update(visible=False), gr.update(visible=False), gr.update(visible=False), gr.update(visible=False)
                    
                    try:
                        from src.schema_mapper import save_table_mapping, save_column_mapping
                        
                        if table and column:
                            # Column mapping
                            if save_column_mapping(term.strip(), table, column):
                                return (
                                    f"✅ Saved: When you say '{term}', I'll use table '{table}', column '{column}'",
                                    gr.update(visible=False),
                                    gr.update(visible=False),
                                    gr.update(visible=False),
                                    gr.update(visible=False)
                                )
                            else:
                                return "❌ Failed to save mapping.", gr.update(), gr.update(), gr.update(), gr.update()
                        elif table:
                            # Table mapping only
                            if save_table_mapping(term.strip(), table):
                                return (
                                    f"✅ Saved: When you say '{term}', I'll use table '{table}'",
                                    gr.update(visible=False),
                                    gr.update(visible=False),
                                    gr.update(visible=False),
                                    gr.update(visible=False)
                                )
                            else:
                                return "❌ Failed to save mapping.", gr.update(), gr.update(), gr.update(), gr.update()
                        else:
                            return "❌ Please select at least a table.", gr.update(), gr.update(), gr.update(), gr.update()
                    except Exception as e:
                        logger.error(f"Error saving teach me mapping: {e}", exc_info=True)
                        return f"❌ Error: {str(e)}", gr.update(), gr.update(), gr.update(), gr.update()
                
                teach_me_btn.click(
                    show_teach_me_dialog,
                    inputs=[current_message_id],
                    outputs=[teach_me_dialog, teach_me_row, teach_me_term, teach_me_save_btn, teach_me_table, teach_me_column]
                )
                
                teach_me_table.change(
                    update_teach_me_columns,
                    inputs=[teach_me_table],
                    outputs=[teach_me_column]
                )
                
                teach_me_save_btn.click(
                    save_teach_me_mapping,
                    inputs=[teach_me_term, teach_me_table, teach_me_column],
                    outputs=[teach_me_status, teach_me_dialog, teach_me_row, teach_me_term, teach_me_save_btn]
                )
                
                # Show Teach Me button when there's a response (can be enhanced to show only on wrong results)
                def update_teach_me_visibility(msg_id):
                    """Show Teach Me button when there's a message."""
                    if msg_id and msg_id != "":
                        return gr.update(visible=True)
                    return gr.update(visible=False)
                
                # Update Teach Me button visibility when message ID changes
                current_message_id.change(
                    update_teach_me_visibility,
                    inputs=[current_message_id],
                    outputs=[teach_me_btn]
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
            
            # Schema Mapping Tab
            with gr.Tab("🗺️ Schema Mapping"):
                gr.Markdown("## Schema Mapping")
                gr.Markdown("Map natural language terms to your actual database table and column names.")
                
                # Auto-discovered schema display
                gr.Markdown("### Discovered Schema")
                schema_refresh_btn = gr.Button("🔄 Refresh Schema", variant="secondary", size="sm")
                schema_display = gr.Markdown("Click 'Refresh Schema' to discover your database structure.")
                
                def refresh_schema_display():
                    """Refresh and display discovered schema."""
                    try:
                        from src.database import get_engine
                        from src.schema_discovery import get_schema_summary, get_table_info_string
                        
                        engine = get_engine()
                        if not engine:
                            return "❌ No database connection. Please configure database in Settings tab first."
                        
                        schema = get_schema_summary(engine)
                        schema_text = get_table_info_string(engine)
                        
                        if not schema.get("tables"):
                            return "⚠️ No tables found in database. Make sure your database connection is configured correctly."
                        
                        summary = f"### Found {len(schema['tables'])} tables:\n\n"
                        for table in schema["tables"]:
                            summary += f"- **{table['name']}** ({len(table['columns'])} columns)\n"
                        
                        summary += f"\n---\n\n**Full Schema Details:**\n\n```\n{schema_text}\n```"
                        
                        return summary
                    except Exception as e:
                        logger.error(f"Error refreshing schema: {e}", exc_info=True)
                        return f"❌ Error: {str(e)}"
                
                schema_refresh_btn.click(refresh_schema_display, outputs=[schema_display])
                
                gr.Markdown("---")
                
                # Table alias mapping
                gr.Markdown("### Table Mappings")
                gr.Markdown("When I say... → Use table...")
                
                with gr.Row():
                    table_alias_input = gr.Textbox(
                        label="When I say...",
                        placeholder='e.g., "customers"',
                        scale=2
                    )
                    table_dropdown = gr.Dropdown(
                        label="Use table...",
                        choices=[],
                        scale=2
                    )
                    add_table_mapping_btn = gr.Button("➕ Add", variant="primary", scale=1)
                
                table_mappings_display = gr.Markdown("No table mappings yet.")
                table_mappings_list = gr.State([])
                
                def load_table_mappings():
                    """Load and display current table mappings."""
                    try:
                        from src.schema_mapper import load_mappings
                        from src.database import get_engine
                        from src.schema_discovery import discover_tables
                        
                        mappings = load_mappings()
                        table_aliases = mappings.get("table_aliases", {})
                        
                        # Get available tables for dropdown
                        engine = get_engine()
                        available_tables = discover_tables(engine) if engine else []
                        
                        if not table_aliases:
                            return "No table mappings yet.", [], available_tables
                        
                        display = "### Current Table Mappings:\n\n"
                        mapping_list = []
                        for alias, actual in table_aliases.items():
                            display += f"- **\"{alias}\"** → `{actual}`\n"
                            mapping_list.append({"alias": alias, "actual": actual})
                        
                        return display, mapping_list, available_tables
                    except Exception as e:
                        logger.error(f"Error loading table mappings: {e}", exc_info=True)
                        return f"❌ Error: {str(e)}", [], []
                
                def add_table_mapping(alias, actual_table):
                    """Add a new table mapping."""
                    if not alias.strip() or not actual_table:
                        return "❌ Please enter both alias and select a table.", gr.update(), gr.update()
                    
                    try:
                        from src.schema_mapper import save_table_mapping, load_table_mappings
                        
                        if save_table_mapping(alias.strip(), actual_table):
                            display, mapping_list, tables = load_table_mappings()
                            return f"✅ Added: \"{alias}\" → `{actual_table}`", display, gr.update(choices=tables)
                        else:
                            return "❌ Failed to save mapping.", gr.update(), gr.update()
                    except Exception as e:
                        return f"❌ Error: {str(e)}", gr.update(), gr.update()
                
                add_table_mapping_btn.click(
                    add_table_mapping,
                    inputs=[table_alias_input, table_dropdown],
                    outputs=[table_mappings_display, table_mappings_display, table_dropdown]
                )
                
                # Update table dropdown when schema is refreshed
                def update_table_dropdown():
                    try:
                        from src.database import get_engine
                        from src.schema_discovery import discover_tables
                        
                        engine = get_engine()
                        if engine:
                            tables = discover_tables(engine)
                            return gr.update(choices=tables)
                        return gr.update(choices=[])
                    except:
                        return gr.update(choices=[])
                
                schema_refresh_btn.click(update_table_dropdown, outputs=[table_dropdown])
                demo.load(load_table_mappings, outputs=[table_mappings_display, table_mappings_list, table_dropdown])
                
                gr.Markdown("---")
                
                # Column alias mapping
                gr.Markdown("### Column Mappings")
                gr.Markdown("When I say... → Use table... → column...")
                
                with gr.Row():
                    column_alias_input = gr.Textbox(
                        label="When I say...",
                        placeholder='e.g., "customer name"',
                        scale=2
                    )
                    column_table_dropdown = gr.Dropdown(
                        label="Table...",
                        choices=[],
                        scale=1
                    )
                    column_dropdown = gr.Dropdown(
                        label="Column...",
                        choices=[],
                        scale=1
                    )
                    add_column_mapping_btn = gr.Button("➕ Add", variant="primary", scale=1)
                
                column_mappings_display = gr.Markdown("No column mappings yet.")
                
                def update_column_dropdown(table_name):
                    """Update column dropdown based on selected table."""
                    try:
                        from src.database import get_engine
                        from src.schema_discovery import discover_columns
                        
                        engine = get_engine()
                        if engine and table_name:
                            columns = discover_columns(engine, table_name)
                            column_names = [col["name"] for col in columns]
                            return gr.update(choices=column_names)
                        return gr.update(choices=[])
                    except:
                        return gr.update(choices=[])
                
                def load_column_mappings():
                    """Load and display current column mappings."""
                    try:
                        from src.schema_mapper import load_mappings
                        
                        mappings = load_mappings()
                        column_aliases = mappings.get("column_aliases", {})
                        
                        if not column_aliases:
                            return "No column mappings yet."
                        
                        display = "### Current Column Mappings:\n\n"
                        for alias, info in column_aliases.items():
                            display += f"- **\"{alias}\"** → `{info['table']}.{info['column']}`\n"
                        
                        return display
                    except Exception as e:
                        return f"❌ Error: {str(e)}"
                
                def add_column_mapping(alias, table_name, column_name):
                    """Add a new column mapping."""
                    if not alias.strip() or not table_name or not column_name:
                        return "❌ Please enter alias and select both table and column.", gr.update()
                    
                    try:
                        from src.schema_mapper import save_column_mapping
                        
                        if save_column_mapping(alias.strip(), table_name, column_name):
                            display = load_column_mappings()
                            return f"✅ Added: \"{alias}\" → `{table_name}.{column_name}`", display
                        else:
                            return "❌ Failed to save mapping.", gr.update()
                    except Exception as e:
                        return f"❌ Error: {str(e)}", gr.update()
                
                column_table_dropdown.change(update_column_dropdown, inputs=[column_table_dropdown], outputs=[column_dropdown])
                add_column_mapping_btn.click(
                    add_column_mapping,
                    inputs=[column_alias_input, column_table_dropdown, column_dropdown],
                    outputs=[column_mappings_display, column_mappings_display]
                )
                schema_refresh_btn.click(update_table_dropdown, outputs=[column_table_dropdown])
                demo.load(load_column_mappings, outputs=[column_mappings_display])
                demo.load(update_table_dropdown, outputs=[column_table_dropdown])
            
            # Train Tab - Simplified (Examples Only)
            with gr.Tab("🎓 Train"):
                gr.Markdown("## Example Queries")
                gr.Markdown("Manage example queries that help the AI understand how to query your database.")
                
                # Example Queries Management
                with gr.Tabs():
                    with gr.Tab("📝 Example Queries"):
                        gr.Markdown("""### Step 1: Enter Your Training Rule
**Plain English:** Tell the AI how to interpret specific queries or terms.

Examples:
- "When users say 'total arrival yarn', return LBS received (not PKR amount)"
- "Greige received = meters of greige fabric from suppliers"
- "Stock check always shows current inventory in both LBS and bags"
""")
                        
                        # List of examples
                        examples_list_md = gr.Markdown("Loading examples...")
                        
                        # Add new example
                        gr.Markdown("### Add New Example")
                        with gr.Row():
                            example_user_query = gr.Textbox(
                                label="User Query (Natural Language)",
                                placeholder='e.g., "top 10 customers by sales"',
                                scale=2
                            )
                            example_db_type = gr.Dropdown(
                                label="Database Type",
                                choices=["mysql", "mssql", "oracle"],
                                value="mysql",
                                scale=1
                            )
                        
                        example_sql_query = gr.Textbox(
                            label="SQL Query",
                            placeholder="SELECT TOP 10 cust_nm, SUM(tot_amt) FROM...",
                            lines=4
                        )
                        example_explanation = gr.Textbox(
                            label="Explanation (Optional)",
                            placeholder="Gets top customers ranked by total sales",
                            lines=2
                        )
                        
                        with gr.Row():
                            add_example_btn = gr.Button("➕ Add Example", variant="primary")
                            refresh_examples_btn = gr.Button("🔄 Refresh", variant="secondary")
                        
                        example_action_msg = gr.Markdown("")
                        
                        # Test example
                        gr.Markdown("---")
                        gr.Markdown("### Test Example")
                        test_example_query = gr.Textbox(
                            label="Test Query",
                            placeholder="Enter a query to test against examples...",
                            lines=2
                        )
                        test_example_btn = gr.Button("🧪 Test", variant="secondary")
                        test_example_result = gr.Markdown("")
                        
                        # Functions for example queries
                        def load_examples_list():
                            """Load and display all example queries."""
                            try:
                                from src.example_queries import load_examples, get_example_stats
                                
                                data = load_examples()
                                examples = data.get("examples", [])
                                stats = get_example_stats()
                                
                                if not examples:
                                    return "No examples yet. Add one below!"
                                
                                output = f"### Example Queries ({stats['total_examples']} total, {stats['total_usage']} uses)\n\n"
                                output += "| # | User Query | SQL Preview | DB | Uses | Success |\n"
                                output += "|---|------------|-------------|----|----|---------|\n"
                                
                                for i, ex in enumerate(examples[:20], 1):  # Limit to 20
                                    user_q = ex.get("user_query", "")[:50]
                                    sql_preview = ex.get("sql_query", "")[:40].replace("\n", " ")
                                    db_type = ex.get("database_type", "mysql")
                                    uses = ex.get("usage_count", 0)
                                    success = f"{ex.get('success_rate', 1.0)*100:.0f}%"
                                    output += f"| {i} | {user_q}... | {sql_preview}... | {db_type} | {uses}x | {success} |\n"
                                
                                if len(examples) > 20:
                                    output += f"\n*...and {len(examples) - 20} more examples*\n"
                                
                                return output
                            except Exception as e:
                                logger.error(f"Error loading examples: {e}", exc_info=True)
                                return f"❌ Error: {str(e)}"
                        
                        def add_example_query(user_query, sql_query, db_type, explanation):
                            """Add a new example query."""
                            if not user_query.strip() or not sql_query.strip():
                                return "❌ Please enter both user query and SQL query", load_examples_list()
                            
                            try:
                                from src.example_queries import add_example
                                
                                example_id = add_example(
                                    user_query=user_query.strip(),
                                    sql_query=sql_query.strip(),
                                    database_type=db_type,
                                    explanation=explanation.strip() if explanation else "",
                                    source="manual"
                                )
                                
                                if example_id:
                                    return f"✅ Example added! (ID: {example_id})", load_examples_list()
                                else:
                                    return "❌ Failed to add example", load_examples_list()
                            except Exception as e:
                                logger.error(f"Error adding example: {e}", exc_info=True)
                                return f"❌ Error: {str(e)}", load_examples_list()
                        
                        def test_example_against_examples(test_query):
                            """Test a query against stored examples."""
                            if not test_query.strip():
                                return "❌ Please enter a test query"
                            
                            try:
                                from src.example_queries import get_relevant_examples, format_examples_for_prompt
                                
                                relevant = get_relevant_examples(test_query, limit=3)
                                
                                if not relevant:
                                    return "No relevant examples found for this query."
                                
                                output = f"### Found {len(relevant)} relevant examples:\n\n"
                                for i, ex in enumerate(relevant, 1):
                                    output += f"**Example {i}:**\n"
                                    output += f"- User said: \"{ex['user_query']}\"\n"
                                    output += f"- SQL: `{ex['sql_query'][:100]}...`\n"
                                    if ex.get("explanation"):
                                        output += f"- Note: {ex['explanation']}\n"
                                    output += "\n"
                                
                                return output
                            except Exception as e:
                                logger.error(f"Error testing example: {e}", exc_info=True)
                                return f"❌ Error: {str(e)}"
                        
                        # Wire up the functions
                        add_example_btn.click(
                            add_example_query,
                            inputs=[example_user_query, example_sql_query, example_db_type, example_explanation],
                            outputs=[example_action_msg, examples_list_md]
                        )
                        refresh_examples_btn.click(load_examples_list, outputs=[examples_list_md])
                        test_example_btn.click(test_example_against_examples, inputs=[test_example_query], outputs=[test_example_result])
                        demo.load(load_examples_list, outputs=[examples_list_md])
                        
                        # Clear form after adding
                        def clear_example_form():
                            return "", "", "mysql", "", ""
                        
                        add_example_btn.click(
                            clear_example_form,
                            outputs=[example_user_query, example_sql_query, example_db_type, example_explanation]
                        )
                    
                    # Old code removed - keeping only Examples tab
                    # All other sub-tabs (Quick Train, Manage Rules, Import Report, etc.) removed per plan
            
            # Upload Report Tab - Excel + SQL Upload with AI Clarification
            with gr.Tab("📊 Upload Report"):
                gr.Markdown("## Upload Report")
                gr.Markdown("Upload an Excel file and SQL query. AI will analyze and ask clarifying questions about unknown or ambiguous aspects.")
                
                with gr.Row():
                    with gr.Column(scale=2):
                        upload_excel_file = gr.File(
                            label="Excel File",
                            file_types=[".xlsx", ".xls"],
                            file_count="single"
                        )
                        upload_sql_query = gr.Textbox(
                            label="SQL Query",
                            placeholder="SELECT * FROM orders WHERE status = 1",
                            lines=5
                        )
                        upload_db_type = gr.Dropdown(
                            label="SQL Dialect",
                            choices=["mysql", "mssql", "oracle"],
                            value="mysql"
                        )
                        upload_description = gr.Textbox(
                            label="Report Description",
                            placeholder="Explain what this report shows and what the data represents...",
                            lines=3
                        )
                        upload_submit_btn = gr.Button("📤 Submit & Process", variant="primary", size="lg")
                    
                    with gr.Column(scale=1):
                        gr.Markdown("**Instructions:**")
                        gr.Markdown("""
1. Upload an Excel file (.xlsx or .xls)
2. Paste the SQL query (MySQL, MSSQL, or Oracle)
3. Describe what the report shows
4. AI will analyze and ask clarifying questions
5. Answer questions to create mappings and examples
""")
                
                upload_status = gr.Markdown("")
                upload_analysis_display = gr.Markdown("")
                upload_questions_display = gr.Markdown("")
                
                # Clarification answers section
                clarification_answers_section = gr.Markdown("", visible=False)
                clarification_answers = gr.State({})  # Store answers: {question_index: answer}
                
                # State to store processing results
                upload_processing_state = gr.State({})
                
                def process_upload_report(excel_file, sql_query, db_type, description):
                    """Process uploaded Excel + SQL with AI analysis."""
                    if not excel_file or not sql_query.strip() or not description.strip():
                        return "❌ Please provide Excel file, SQL query, and description.", "", "", {}
                    
                    try:
                        from src.report_processor import process_upload
                        global current_llm, current_provider
                        
                        if current_llm is None:
                            config = load_config()
                            llm_config = config.get('llm', {})
                            provider_name = llm_config.get('provider', 'openai')
                            model = llm_config.get('model', 'gpt-4o-mini')
                            current_provider = create_provider(provider_name)
                            current_llm = current_provider.get_llm(model, 0.3, 2000)
                        
                        result = process_upload(
                            excel_path=excel_file.name,
                            sql_query=sql_query,
                            description=description,
                            db_type=db_type,
                            llm=current_llm
                        )
                        
                        if not result.get("success"):
                            return f"❌ Processing failed: {result.get('error', 'Unknown error')}", "", "", {}, gr.update(visible=False)
                        
                        # Store original inputs in result for later use
                        result["sql_query"] = sql_query
                        result["description"] = description
                        result["db_type"] = db_type
                        
                        # Format analysis display
                        excel_structure = result.get("excel_structure", {})
                        sql_info = result.get("sql_info", {})
                        ai_analysis = result.get("ai_analysis", {})
                        questions = result.get("clarification_questions", [])
                        
                        analysis_text = f"""### 📊 Analysis Results

**Excel Structure:**
- Columns: {', '.join(excel_structure.get('columns', [])[:10])}
- Sample rows: {excel_structure.get('row_count_preview', 0)}

**SQL Analysis:**
- Tables used: {', '.join(sql_info.get('tables', []))}
- Columns referenced: {', '.join(sql_info.get('columns', [])[:10])}
- Has aggregations: {sql_info.get('has_aggregations', False)}
"""
                        
                        questions_text = ""
                        answers_ui = ""
                        if questions:
                            questions_text = "### ❓ Questions I Need Answered:\n\n"
                            answers_ui = "### Answer the Questions:\n\n"
                            for i, q in enumerate(questions, 1):
                                q_type = q.get("type", "unknown")
                                question_text = q.get("question", "")
                                context = q.get("context", "")
                                questions_text += f"{i}. **{q_type.replace('_', ' ').title()}:** {question_text}\n"
                                if context:
                                    questions_text += f"   Context: {context}\n"
                                questions_text += "\n"
                                
                                # Create answer input for each question
                                answers_ui += f"**Question {i}:** {question_text}\n"
                                answers_ui += f"Your answer: [Input field for question {i}]\n\n"
                        else:
                            questions_text = "✅ No ambiguities found. The report is clear!"
                            answers_ui = ""
                        
                        return (
                            "✅ Processing complete! Review the analysis and questions below.",
                            analysis_text,
                            questions_text,
                            result,
                            gr.update(visible=bool(questions), value=answers_ui) if questions else gr.update(visible=False)
                        )
                    
                    except Exception as e:
                        logger.error(f"Error processing upload: {e}", exc_info=True)
                        return f"❌ Error: {str(e)}", "", "", {}
                
                upload_submit_btn.click(
                    process_upload_report,
                    inputs=[upload_excel_file, upload_sql_query, upload_db_type, upload_description],
                    outputs=[upload_status, upload_analysis_display, upload_questions_display, upload_processing_state, clarification_answers_section]
                )
                
                # Answer inputs (dynamically created based on questions)
                answer_inputs_container = gr.Column(visible=False)
                
                def create_answer_inputs(processing_state):
                    """Create answer input fields for each question."""
                    if not processing_state or not processing_state.get("clarification_questions"):
                        return gr.update(visible=False), []
                    
                    questions = processing_state.get("clarification_questions", [])
                    inputs = []
                    
                    with gr.Row():
                        for i, q in enumerate(questions):
                            q_type = q.get("type", "unknown")
                            question_text = q.get("question", "")
                            
                            answer_input = gr.Textbox(
                                label=f"Q{i+1}: {question_text[:50]}...",
                                placeholder="Your answer...",
                                key=f"answer_{i}"
                            )
                            inputs.append(answer_input)
                    
                    return gr.update(visible=True), inputs
                
                # Save answers and create mappings/examples
                save_answers_btn = gr.Button("💾 Save Answers & Create Mappings", variant="primary", visible=False)
                save_answers_status = gr.Markdown("")
                
                def save_clarification_answers(processing_state, *answers):
                    """Save user answers and create mappings/examples."""
                    if not processing_state or not processing_state.get("clarification_questions"):
                        return "❌ No questions to answer.", gr.update(visible=False)
                    
                    try:
                        from src.report_processor import create_mappings_from_answers
                        from src.schema_mapper import save_mappings
                        from src.example_queries import add_example
                        
                        questions = processing_state.get("clarification_questions", [])
                        answers_dict = {str(i): ans.strip() for i, ans in enumerate(answers) if ans and ans.strip()}
                        
                        if not answers_dict:
                            return "❌ Please provide at least one answer.", gr.update()
                        
                        # Create mappings from answers
                        mappings = create_mappings_from_answers(questions, answers_dict)
                        
                        # Save mappings
                        from src.schema_mapper import load_mappings
                        current_mappings = load_mappings()
                        current_mappings["table_aliases"].update(mappings.get("table_aliases", {}))
                        current_mappings["column_aliases"].update(mappings.get("column_aliases", {}))
                        save_mappings(current_mappings)
                        
                        # Create example query
                        sql_query = processing_state.get("sql_query", "")
                        description = processing_state.get("description", "")
                        db_type = processing_state.get("db_type", "mysql")
                        
                        if sql_query and description:
                            add_example(
                                user_query=description,
                                sql_query=sql_query,
                                database_type=db_type,
                                explanation=f"Uploaded report: {description}",
                                source="uploaded_report"
                            )
                        
                        table_count = len(mappings.get("table_aliases", {}))
                        column_count = len(mappings.get("column_aliases", {}))
                        
                        return (
                            f"✅ Saved! Created {table_count} table mapping(s) and {column_count} column mapping(s). "
                            f"Also created an example query. The system will now understand these terms!",
                            gr.update(visible=False)
                        )
                    except Exception as e:
                        logger.error(f"Error saving clarification answers: {e}", exc_info=True)
                        return f"❌ Error: {str(e)}", gr.update()
                
                # Note: The answer inputs would need to be dynamically created based on questions
                # For now, we'll use a simpler approach with a text area for all answers
                all_answers_input = gr.Textbox(
                    label="Answers (one per line, in order)",
                    placeholder="Answer 1\nAnswer 2\nAnswer 3",
                    lines=5,
                    visible=False
                )
                
                def save_answers_simple(processing_state, all_answers):
                    """Save answers from text area (simpler approach)."""
                    if not processing_state or not processing_state.get("clarification_questions"):
                        return "❌ No questions to answer.", gr.update(visible=False)
                    
                    try:
                        from src.report_processor import create_mappings_from_answers
                        from src.schema_mapper import save_mappings, load_mappings
                        from src.example_queries import add_example
                        
                        questions = processing_state.get("clarification_questions", [])
                        answers_list = [a.strip() for a in all_answers.split("\n") if a.strip()]
                        answers_dict = {str(i): ans for i, ans in enumerate(answers_list) if i < len(questions)}
                        
                        if not answers_dict:
                            return "❌ Please provide answers (one per line).", gr.update()
                        
                        # Create mappings
                        mappings = create_mappings_from_answers(questions, answers_dict)
                        
                        # Save mappings
                        current_mappings = load_mappings()
                        current_mappings["table_aliases"].update(mappings.get("table_aliases", {}))
                        current_mappings["column_aliases"].update(mappings.get("column_aliases", {}))
                        save_mappings(current_mappings)
                        
                        # Create example query
                        sql_query = processing_state.get("sql_query", "")
                        description = processing_state.get("description", "")
                        db_type = processing_state.get("db_type", "mysql")
                        
                        # Try to get SQL from the original upload
                        if not sql_query and processing_state.get("sql_info"):
                            # SQL was in the processing result
                            pass
                        
                        table_count = len(mappings.get("table_aliases", {}))
                        column_count = len(mappings.get("column_aliases", {}))
                        
                        return (
                            f"✅ Saved! Created {table_count} table mapping(s) and {column_count} column mapping(s). "
                            f"The system will now understand these terms!",
                            gr.update(visible=False)
                        )
                    except Exception as e:
                        logger.error(f"Error saving answers: {e}", exc_info=True)
                        return f"❌ Error: {str(e)}", gr.update()
                
                # Show answer input when questions are displayed
                def show_answer_input(has_questions):
                    if has_questions:
                        return gr.update(visible=True), gr.update(visible=True)
                    return gr.update(visible=False), gr.update(visible=False)
                
                upload_questions_display.change(
                    lambda q: show_answer_input(bool(q) and "Questions I Need" in q),
                    inputs=[upload_questions_display],
                    outputs=[all_answers_input, save_answers_btn]
                )
                
                save_answers_btn.click(
                    save_answers_simple,
                    inputs=[upload_processing_state, all_answers_input],
                    outputs=[save_answers_status, all_answers_input]
                )
            
            with gr.Tab("🎯 Data Training Module"):
                gr.Markdown("""
## Knowledge Capture System
Map business questions to MSSQL/Oracle SQL with complete reasoning and metadata.
This is not model training—it's a living knowledge base that captures how users talk about data.
""")
                
                with gr.Tabs():
                    # Example Editor
                    with gr.Tab("✏️ Example Editor"):
                        with gr.Row():
                            with gr.Column(scale=2):
                                tm_question = gr.Textbox(
                                    label="Business Question",
                                    placeholder="Show me the top 5 products by revenue last month",
                                    lines=2
                                )
                                tm_schema = gr.Textbox(
                                    label="Schema Context (Tables & Columns)",
                                    placeholder="Products (product_id, product_name, price)\nSales (sale_id, product_id, quantity, sale_date, revenue)",
                                    lines=4
                                )
                                tm_assumptions = gr.Textbox(
                                    label="Assumptions & Ambiguity Resolution",
                                    placeholder="'Revenue' means gross revenue (not net). 'Last month' means previous calendar month. 'Top 5' ordered by total revenue descending.",
                                    lines=3
                                )
                                
                                with gr.Row():
                                    tm_categories = gr.Dropdown(
                                        label="Categories (select multiple)",
                                        choices=CATEGORY_OPTIONS,
                                        multiselect=True,
                                        value=[]
                                    )
                                    tm_complexity = gr.Dropdown(
                                        label="Complexity",
                                        choices=COMPLEXITY_LEVELS,
                                        value="intermediate"
                                    )
                                
                                with gr.Row():
                                    tm_processing = gr.Radio(
                                        label="Processing Type",
                                        choices=["sql_only", "sql_plus_postprocessing"],
                                        value="sql_only"
                                    )
                                    tm_priority = gr.Slider(
                                        label="Priority (1-5)",
                                        minimum=1,
                                        maximum=5,
                                        value=3,
                                        step=1
                                    )
                            
                            with gr.Column(scale=1):
                                tm_example_id = gr.Textbox(label="Example ID (auto-generated)", interactive=False)
                                tm_version = gr.Textbox(label="Version", value="1", interactive=False)
                                tm_validated = gr.Checkbox(label="Validated", value=False)
                                
                                gr.Markdown("### Actions")
                                tm_save_btn = gr.Button("💾 Save Example", variant="primary", size="lg")
                                tm_new_btn = gr.Button("📄 New Example", size="sm")
                                tm_delete_btn = gr.Button("🗑️ Delete", size="sm", variant="stop")
                        
                        # Dual Engine Outputs
                        gr.Markdown("### SQL Outputs (Side-by-Side)")
                        with gr.Row():
                            with gr.Column():
                                gr.Markdown("#### MSSQL")
                                tm_mssql_query = gr.Code(
                                    label="MSSQL Query",
                                    language="sql",
                                    lines=8
                                )
                                tm_mssql_explanation = gr.Textbox(
                                    label="Explanation",
                                    placeholder="Why this query works for MSSQL...",
                                    lines=3
                                )
                            
                            with gr.Column():
                                gr.Markdown("#### Oracle")
                                tm_oracle_query = gr.Code(
                                    label="Oracle Query",
                                    language="sql",
                                    lines=8
                                )
                                tm_oracle_explanation = gr.Textbox(
                                    label="Explanation",
                                    placeholder="Why this query works for Oracle...",
                                    lines=3
                                )
                        
                        tm_save_status = gr.Markdown()
                        
                        # Save example logic
                        def save_training_example(question, schema, assumptions, categories, complexity,
                                                 processing, priority, mssql_q, mssql_exp, oracle_q, oracle_exp,
                                                 example_id, validated):
                            if not question or not schema:
                                return "❌ Question and Schema are required!"
                            
                            if not mssql_q and not oracle_q:
                                return "❌ At least one SQL query (MSSQL or Oracle) is required!"
                            
                            manager = get_training_manager()
                            
                            if not example_id:
                                example_id = str(uuid.uuid4())[:8]
                            
                            example = TrainingExample(
                                id=example_id,
                                question=question,
                                schema_context=schema,
                                mssql_query=mssql_q or "",
                                mssql_explanation=mssql_exp or "",
                                oracle_query=oracle_q or "",
                                oracle_explanation=oracle_exp or "",
                                categories=categories or [],
                                complexity=complexity,
                                assumptions=assumptions or "",
                                processing_type=processing,
                                created_at=datetime.now().isoformat(),
                                updated_at=datetime.now().isoformat(),
                                version=1,
                                priority=int(priority),
                                validated=validated
                            )
                            
                            saved_id = manager.add_example(example)
                            return f"✅ **Saved!** Example ID: `{saved_id}` (Version {example.version})"
                        
                        def clear_example_form():
                            return ["", "", "", [], "intermediate", "sql_only", 3, "", "", "", "", "", "", 1, False, ""]
                        
                        def delete_training_example(example_id):
                            if not example_id:
                                return "❌ No example selected to delete!"
                            
                            manager = get_training_manager()
                            if manager.delete_example(example_id):
                                return f"✅ Deleted example `{example_id}`"
                            return f"❌ Example `{example_id}` not found!"
                        
                        tm_save_btn.click(
                            save_training_example,
                            inputs=[tm_question, tm_schema, tm_assumptions, tm_categories, tm_complexity,
                                   tm_processing, tm_priority, tm_mssql_query, tm_mssql_explanation,
                                   tm_oracle_query, tm_oracle_explanation, tm_example_id, tm_validated],
                            outputs=[tm_save_status]
                        )
                        
                        tm_new_btn.click(
                            clear_example_form,
                            outputs=[tm_question, tm_schema, tm_assumptions, tm_categories, tm_complexity,
                                    tm_processing, tm_priority, tm_mssql_query, tm_mssql_explanation,
                                    tm_oracle_query, tm_oracle_explanation, tm_example_id, tm_version,
                                    tm_validated, tm_save_status]
                        )
                        
                        tm_delete_btn.click(
                            delete_training_example,
                            inputs=[tm_example_id],
                            outputs=[tm_save_status]
                        )
                    
                    # Query Ingestion & Review
                    with gr.Tab("📥 Query Review"):
                        gr.Markdown("""
### Review Queries from User Interactions
Queries captured from the Chat tab appear here for review. Fix the SQL and save as canonical examples.
""")
                        
                        tm_review_refresh_btn = gr.Button("🔄 Load Pending Reviews", variant="primary")
                        tm_review_list = gr.Dropdown(label="Pending Reviews", choices=[], interactive=True)
                        
                        with gr.Row():
                            with gr.Column():
                                tm_review_question = gr.Textbox(label="Original Question", interactive=False)
                                tm_review_schema = gr.Textbox(label="Schema Used", interactive=False, lines=3)
                                tm_review_ai_response = gr.Code(label="AI Generated SQL", language="sql", interactive=False)
                                tm_review_feedback = gr.Textbox(label="User Feedback", interactive=False)
                                tm_review_correction = gr.Textbox(label="User Correction", interactive=False, lines=2)
                            
                            with gr.Column():
                                gr.Markdown("### Convert to Training Example")
                                tm_review_to_example_btn = gr.Button("✅ Convert to Example", variant="primary")
                                tm_review_skip_btn = gr.Button("⏭️ Mark Reviewed (Skip)", variant="secondary")
                        
                        tm_review_status = gr.Markdown()
                        
                        def load_pending_reviews():
                            manager = get_training_manager()
                            pending = manager.get_ingested_for_review()
                            
                            if not pending:
                                return gr.Dropdown(choices=[], value=None), "No pending reviews."
                            
                            choices = [f"{q.id}: {q.question[:50]}..." for q in pending]
                            return gr.Dropdown(choices=choices, value=choices[0] if choices else None), f"Found {len(pending)} pending reviews."
                        
                        def show_review_details(selected):
                            if not selected:
                                return "", "", "", "", ""
                            
                            query_id = selected.split(":")[0]
                            manager = get_training_manager()
                            query = manager.ingested.get(query_id)
                            
                            if not query:
                                return "", "", "", "", ""
                            
                            ai_sql = query.ai_response.get("result", "") if isinstance(query.ai_response, dict) else str(query.ai_response)
                            
                            return (
                                query.question,
                                query.schema_used,
                                ai_sql,
                                query.user_feedback,
                                query.user_correction or ""
                            )
                        
                        def mark_reviewed_skip(selected):
                            if not selected:
                                return "❌ No query selected!"
                            
                            query_id = selected.split(":")[0]
                            manager = get_training_manager()
                            manager.mark_reviewed(query_id)
                            return f"✅ Marked `{query_id}` as reviewed."
                        
                        tm_review_refresh_btn.click(
                            load_pending_reviews,
                            outputs=[tm_review_list, tm_review_status]
                        )
                        
                        tm_review_list.change(
                            show_review_details,
                            inputs=[tm_review_list],
                            outputs=[tm_review_question, tm_review_schema, tm_review_ai_response,
                                    tm_review_feedback, tm_review_correction]
                        )
                        
                        tm_review_skip_btn.click(
                            mark_reviewed_skip,
                            inputs=[tm_review_list],
                            outputs=[tm_review_status]
                        )
                    
                    # Coverage & Stats
                    with gr.Tab("📊 Coverage"):
                        gr.Markdown("### Training Data Coverage Analysis")
                        
                        tm_coverage_refresh_btn = gr.Button("🔄 Refresh Stats", variant="primary")
                        tm_coverage_display = gr.Markdown()
                        
                        def show_coverage_stats():
                            manager = get_training_manager()
                            stats = manager.get_coverage_stats()
                            
                            output = f"""
## Coverage Statistics

**Total Examples:** {stats['total_examples']}  
**Validated:** {stats['validated']}  
**Pending Review:** {stats['needs_review']}

### By Category
"""
                            for cat, count in sorted(stats['by_category'].items(), key=lambda x: x[1], reverse=True):
                                output += f"- **{cat}**: {count}\n"
                            
                            output += "\n### By Complexity\n"
                            for complexity, count in sorted(stats['by_complexity'].items()):
                                output += f"- **{complexity}**: {count}\n"
                            
                            output += "\n### By Engine Coverage\n"
                            output += f"- **Both MSSQL & Oracle**: {stats['by_engine']['both']}\n"
                            output += f"- **MSSQL only**: {stats['by_engine']['mssql']}\n"
                            output += f"- **Oracle only**: {stats['by_engine']['oracle']}\n"
                            
                            output += "\n### By Priority\n"
                            for priority in sorted(stats['by_priority'].keys(), reverse=True):
                                output += f"- **Priority {priority}**: {stats['by_priority'][priority]}\n"
                            
                            # Coverage gaps
                            output += "\n### 🚨 Coverage Gaps\n"
                            missing_categories = [cat for cat in CATEGORY_OPTIONS if cat not in stats['by_category']]
                            if missing_categories:
                                output += "**Missing categories:**\n"
                                for cat in missing_categories:
                                    output += f"- {cat}\n"
                            else:
                                output += "✅ All categories have at least one example!\n"
                            
                            return output
                        
                        tm_coverage_refresh_btn.click(
                            show_coverage_stats,
                            outputs=[tm_coverage_display]
                        )
                    
                    # Regression Testing
                    with gr.Tab("🧪 Regression Tests"):
                        gr.Markdown("""
### Validate AI Against Canonical Examples
Run test questions and compare AI output against your saved training examples.
""")
                        
                        tm_test_questions = gr.Textbox(
                            label="Test Questions (one per line)",
                            placeholder="Show me top 5 products by revenue\nWhat are the monthly sales totals?",
                            lines=6
                        )
                        tm_run_tests_btn = gr.Button("▶️ Run Regression Tests", variant="primary", size="lg")
                        tm_test_results = gr.Markdown()
                        
                        def run_regression_tests(questions_text):
                            if not questions_text.strip():
                                return "❌ Please enter test questions!"
                            
                            questions = [q.strip() for q in questions_text.split('\n') if q.strip()]
                            manager = get_training_manager()
                            results = manager.run_regression_test(questions)
                            
                            output = f"""
## Regression Test Results

**Total Tests:** {results['total_tests']}  
**Passed:** {results['passed']} ✅  
**Failed:** {results['failed']} ❌

### Details
"""
                            for detail in results['details']:
                                status = "✅ PASS" if detail.get('passed') else "❌ FAIL"
                                output += f"\n#### {status}: {detail['question']} ({detail['engine']})\n"
                                
                                if 'error' in detail:
                                    output += f"**Error:** {detail['error']}\n"
                                elif not detail.get('passed'):
                                    output += f"**Expected:**\n```sql\n{detail.get('expected', '')}\n```\n"
                                    output += f"**Generated:**\n```sql\n{detail.get('generated', '')}\n```\n"
                            
                            return output
                        
                        tm_run_tests_btn.click(
                            run_regression_tests,
                            inputs=[tm_test_questions],
                            outputs=[tm_test_results]
                        )
                    
                    # Browse & Search
                    with gr.Tab("🔍 Browse Examples"):
                        gr.Markdown("### Search and Browse Training Examples")
                        
                        with gr.Row():
                            tm_search_query = gr.Textbox(label="Search", placeholder="Enter keywords...")
                            tm_search_btn = gr.Button("🔍 Search", variant="primary")
                        
                        with gr.Row():
                            tm_filter_category = gr.Dropdown(label="Filter by Category", choices=["All"] + CATEGORY_OPTIONS, value="All")
                            tm_filter_complexity = gr.Dropdown(label="Filter by Complexity", choices=["All"] + COMPLEXITY_LEVELS, value="All")
                        
                        tm_examples_list = gr.Dropdown(label="Examples", choices=[], interactive=True)
                        tm_load_example_btn = gr.Button("📂 Load Selected Example")
                        
                        tm_browse_status = gr.Markdown()
                        
                        def search_and_filter(query, category, complexity):
                            manager = get_training_manager()
                            
                            if query.strip():
                                examples = manager.search_examples(query)
                            else:
                                cat_filter = None if category == "All" else category
                                comp_filter = None if complexity == "All" else complexity
                                examples = manager.list_examples(category=cat_filter, complexity=comp_filter)
                            
                            if not examples:
                                return gr.Dropdown(choices=[], value=None), f"No examples found."
                            
                            choices = [f"{e.id}: {e.question[:60]}..." for e in examples]
                            return gr.Dropdown(choices=choices, value=choices[0] if choices else None), f"Found {len(examples)} examples."
                        
                        def load_selected_example(selected):
                            if not selected:
                                return [""] * 14 + ["Loaded example"]
                            
                            example_id = selected.split(":")[0]
                            manager = get_training_manager()
                            example = manager.get_example(example_id)
                            
                            if not example:
                                return [""] * 14 + ["Example not found"]
                            
                            # Return values for all fields
                            return [
                                example.question,
                                example.schema_context,
                                example.assumptions,
                                example.categories,
                                example.complexity,
                                example.processing_type,
                                example.priority,
                                example.mssql_query,
                                example.mssql_explanation,
                                example.oracle_query,
                                example.oracle_explanation,
                                example.id,
                                str(example.version),
                                example.validated,
                                f"Loaded example `{example.id}` (v{example.version})"
                            ]
                        
                        tm_search_btn.click(
                            search_and_filter,
                            inputs=[tm_search_query, tm_filter_category, tm_filter_complexity],
                            outputs=[tm_examples_list, tm_browse_status]
                        )
                        
                        tm_filter_category.change(
                            search_and_filter,
                            inputs=[tm_search_query, tm_filter_category, tm_filter_complexity],
                            outputs=[tm_examples_list, tm_browse_status]
                        )
                        
                        tm_filter_complexity.change(
                            search_and_filter,
                            inputs=[tm_search_query, tm_filter_category, tm_filter_complexity],
                            outputs=[tm_examples_list, tm_browse_status]
                        )
                        
                        tm_load_example_btn.click(
                            load_selected_example,
                            inputs=[tm_examples_list],
                            outputs=[tm_question, tm_schema, tm_assumptions, tm_categories, tm_complexity,
                                    tm_processing, tm_priority, tm_mssql_query, tm_mssql_explanation,
                                    tm_oracle_query, tm_oracle_explanation, tm_example_id, tm_version,
                                    tm_validated, tm_save_status]
                        )
            
                    # Developer Tab Functions
                    def export_session_report():
                        """Export session report for quick Copilot sharing."""
                        try:
                            tracker = get_session_tracker()
                            report_path = tracker.export_for_copilot()
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
                    
                    def collect_full_diagnostics():
                        """Collect comprehensive diagnostic bundle."""
                        try:
                            from src.diagnostics import collect_full_session_bundle
                            bundle_path = collect_full_session_bundle(include_sensitive=True)
                            if bundle_path:
                                return (
                                    f"✅ **Diagnostic Bundle Created**\n\nBundle: `{bundle_path}`\n\nIncludes: session data, logs, config, training rules, DB snapshot, environment info.",
                                    bundle_path,
                                    gr.update(visible=True)
                                )
                            else:
                                # Fallback to basic diagnostics
                                from src.diagnostics import collect_diagnostics
                                basic_path = collect_diagnostics()
                                return (
                                    f"⚠️ **Basic Diagnostics Collected**\n\nFile: `{basic_path}`\n\n(Full bundle unavailable, using text report)",
                                    basic_path,
                                    gr.update(visible=True)
                                )
                        except Exception as e:
                            return f"❌ Error: {str(e)}", None, gr.update(visible=False)
            
            # Developer Tab (Simplified)
            with gr.Tab("🛠️ Developer"):
                gr.Markdown("## Developer Tools")
                gr.Markdown("Quick diagnostics and system monitoring.")

                # Main Diagnostics Section
                with gr.Accordion("🎯 Auto-Diagnostics", open=True):
                    gr.Markdown("""
**One-click diagnostics for AI-assisted debugging**

Automatically captures errors, analyzes patterns, and generates recommendations.
""")
                    with gr.Row():
                        diag_btn = gr.Button("🚀 Run Diagnostics", variant="primary", size="lg")
                        fresh_btn = gr.Button("🔄 Fresh Session", size="sm")

                    diag_output = gr.Markdown()

                    diag_btn.click(run_auto_diagnostics_ui, outputs=diag_output)
                    fresh_btn.click(clear_session, outputs=diag_output)

                # Quick Status Section
                with gr.Accordion("📊 System Status", open=False):
                    status_display = gr.Markdown()
                    refresh_btn = gr.Button("🔄 Refresh", size="sm")

                    refresh_btn.click(_env_status, outputs=status_display)
                    demo.load(_env_status, outputs=status_display)

                # Export Section
                with gr.Accordion("📦 Export Data", open=False):
                    gr.Markdown("Export session data for analysis or debugging.")

                    with gr.Row():
                        session_export_btn = gr.Button("📤 Session Report", variant="secondary")
                        full_export_btn = gr.Button("🔍 Full Diagnostics", variant="primary")

                    export_status = gr.Markdown()
                    export_file = gr.File(visible=False)

                    session_export_btn.click(export_session_report, outputs=[export_status, export_file, export_file])
                    full_export_btn.click(collect_full_diagnostics, outputs=[export_status, export_file, export_file])

    
    return demo

if __name__ == "__main__":
    demo = build_ui()
    demo.launch(theme=gr.themes.Default())
