"""
Gradio UI for DBAI Application
Provides a multi-tab interface for chat, settings, training, data import, and diagnostics.
"""
import logging
import os
from typing import List, Optional, Tuple
import gradio as gr
import yaml
from pathlib import Path
from dotenv import load_dotenv, set_key

from src.providers import create_provider
from src.database import reload_engine, test_connection, get_engine, run_query, get_sql_database
from src.llm import make_sql_chain, make_presentation_chain, make_describe_chain, extract_sql_from_response
from src.uploader import process_excel_files, check_table_exists, import_dataframe_to_db
from src.trainer import save_training_example
from src.diagnostics import collect_diagnostics

logger = logging.getLogger(__name__)
load_dotenv()

# Global state
current_provider = None
current_llm = None

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
def chat_query(question: str, history: List) -> Tuple[str, List]:
    """
    Process a natural language query and return SQL + results.
    
    Args:
        question: User's question
        history: Chat history
        
    Returns:
        Tuple of (response, updated_history)
    """
    global current_llm, current_provider
    
    if not question.strip():
        return "", history
    
    try:
        # Load config and initialize provider if needed
        config = load_config()
        llm_config = config.get('llm', {})
        
        provider_name = llm_config.get('provider', 'groq')
        model = llm_config.get('model', 'llama-3.1-8b-instant')
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
        
        # Generate SQL
        sql_chain = make_sql_chain(current_llm, db)
        sql_response = sql_chain({"question": question})
        
        # Extract SQL from response
        if isinstance(sql_response, dict):
            sql_query = sql_response.get('result', '')
        else:
            sql_query = str(sql_response)
        
        sql_query = extract_sql_from_response(sql_query)
        
        # Execute query
        success, result = run_query(sql_query)
        
        if success:
            # Format response (SQL hidden, only show results)
            response = ""
            
            if isinstance(result, dict):
                if 'columns' in result and 'rows' in result:
                    response += f"**Results:** ({len(result['rows'])} rows)\n\n"
                    
                    # Create simple table
                    if result['rows']:
                        # Header
                        response += "| " + " | ".join(result['columns']) + " |\n"
                        response += "|" + "|".join(["---" for _ in result['columns']]) + "|\n"
                        
                        # Rows (limit to 20)
                        for row in result['rows'][:20]:
                            response += "| " + " | ".join(str(v) for v in row) + " |\n"
                        
                        if len(result['rows']) > 20:
                            response += f"\n_... and {len(result['rows']) - 20} more rows_"
                else:
                    response += f"**Result:** {result.get('message', 'Success')}"
            else:
                response += f"**Result:** {result}"
        else:
            response = f"❌ **Error:** {result}"
        
        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": response})
        return "", history
        
    except Exception as e:
        logger.error(f"Chat query error: {e}", exc_info=True)
        response = f"❌ Error: {str(e)}"
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
    global current_provider, current_llm
    
    try:
        # Update config
        config = load_config()
        
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
        llm_config.get('provider', 'groq'),
        llm_config.get('model', 'llama-3.1-8b-instant'),
        llm_config.get('temperature', 0.1),
        llm_config.get('max_tokens', 2000),
        db_config.get('server', 'localhost'),
        db_config.get('database', 'master'),
        db_config.get('driver', 'ODBC Driver 17 for SQL Server'),
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
            # Chat Tab
            with gr.Tab("💬 Chat"):
                chatbot = gr.Chatbot(height=400, label="Conversation")
                
                with gr.Row():
                    question_input = gr.Textbox(
                        placeholder="Ask a question about your database...",
                        label="Your Question"
                    )
                
                with gr.Row():
                    send_stop_btn = gr.Button("▶ Send", variant="primary", scale=2)
                    clear_btn = gr.Button("Clear Chat", size="sm", variant="secondary", scale=1)
                
                # Query event tracking
                query_event = None
                
                def toggle_button_and_query(question, history, is_running):
                    """Handle send/stop toggle and query execution"""
                    if is_running:
                        # Stop was clicked
                        return history, question, False, gr.update(value="▶ Send", variant="primary")
                    else:
                        # Send was clicked
                        return chat_query(question, history)
                
                def update_button_during_query():
                    """Update button to Stop mode"""
                    return gr.update(value="⏹ Stop", variant="stop"), True
                
                def update_button_after_query(result):
                    """Update button back to Send mode"""
                    return result[0], result[1], False, gr.update(value="▶ Send", variant="primary")
                
                is_running = gr.State(False)
                
                # Handle button click
                send_stop_btn.click(
                    update_button_during_query,
                    outputs=[send_stop_btn, is_running]
                ).then(
                    chat_query,
                    inputs=[question_input, chatbot],
                    outputs=[question_input, chatbot]
                ).then(
                    lambda: (False, gr.update(value="▶ Send", variant="primary")),
                    outputs=[is_running, send_stop_btn]
                )
                
                question_input.submit(
                    update_button_during_query,
                    outputs=[send_stop_btn, is_running]
                ).then(
                    chat_query,
                    inputs=[question_input, chatbot],
                    outputs=[question_input, chatbot]
                ).then(
                    lambda: (False, gr.update(value="▶ Send", variant="primary")),
                    outputs=[is_running, send_stop_btn]
                )
                
                clear_btn.click(lambda: [], outputs=chatbot)
            
            # Settings Tab
            with gr.Tab("⚙️ Settings"):
                gr.Markdown("## LLM Provider Settings")
                
                with gr.Row():
                    provider_dropdown = gr.Dropdown(
                        choices=["groq", "openai"],
                        label="Provider",
                        value="groq"
                    )
                    model_dropdown = gr.Dropdown(
                        choices=[],
                        label="Model",
                        value="",
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
                        value="ODBC Driver 17 for SQL Server"
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
                    lambda: get_available_models("groq"),
                    outputs=[model_dropdown]
                )
            
            # Train Tab - AI Learning System
            with gr.Tab("🎓 Train"):
                gr.Markdown("## AI Database Training System")
                gr.Markdown("*Interactive session to teach the AI about your database structure, relationships, and business logic.*")
                
                # Training conversation interface
                training_chatbot = gr.Chatbot(
                    value=[{"role": "assistant", "content": "👋 Hi! I'm here to train the AI on your database. I'll ask you questions to understand your data structure, relationships, and business rules. Ready to begin?"}],
                    height=400,
                    label="Training Conversation"
                )
                
                with gr.Row():
                    training_input = gr.Textbox(
                        placeholder="Type your answer or question here...",
                        label="Your Response",
                        scale=5
                    )
                
                with gr.Row():
                    train_send_stop_btn = gr.Button("▶ Send", variant="primary", scale=2)
                    reset_training_btn = gr.Button("🔄 Reset Training", size="sm", variant="secondary", scale=1)
                
                with gr.Row():
                    view_knowledge_btn = gr.Button("📊 View Training Data", size="sm")
                    export_training_btn = gr.Button("💾 Export Knowledge", size="sm")
                
                knowledge_display = gr.Markdown(
                    label="AI Knowledge Base",
                    visible=False
                )
                
                export_file = gr.File(label="Download Training Data", visible=False)
                
                # Training state and functions
                training_state = gr.State({
                    "stage": 0,
                    "knowledge": {},
                    "conversation": []
                })
                
                def process_training_response(user_input, history, state):
                    """Process user's training response and generate next question."""
                    global current_llm, current_provider
                    
                    if not user_input.strip():
                        return history, "", state
                    
                    # Add user message to history
                    history.append({"role": "user", "content": user_input})
                    
                    # Initialize LLM if needed
                    if current_llm is None:
                        config = load_config()
                        llm_config = config.get('llm', {})
                        provider_name = llm_config.get('provider', 'openai')
                        model = llm_config.get('model', 'gpt-4o-mini')
                        current_provider = create_provider(provider_name)
                        current_llm = current_provider.get_llm(model, 0.3, 2000)
                    
                    # Get database schema for context
                    db = get_sql_database()
                    schema_info = ""
                    if db:
                        try:
                            schema_info = db.get_table_info()
                        except:
                            schema_info = "(Database schema unavailable)"
                    
                    # Build training prompt
                    conversation_context = "\n".join([f"{msg['role']}: {msg['content']}" for msg in history[:-1]])
                    
                    training_prompt = f"""You are an AI assistant helping to learn about a user's database. Your goal is to gather comprehensive information about:
1. Database purpose and domain
2. Table names and their purposes
3. Key relationships between tables
4. Important columns and their meanings
5. Business rules and constraints
6. Common queries and use cases

Database Schema:
{schema_info}

Conversation so far:
{conversation_context}

User's latest response: {user_input}

Based on this, either:
- Ask a thoughtful follow-up question to learn more
- If you have enough information about a topic, ask about the next important aspect
- After gathering comprehensive information, summarize your understanding

Respond naturally and conversationally. Ask ONE specific question at a time.

Response:"""
                    
                    try:
                        response = current_llm.invoke(training_prompt)
                        ai_response = response.content if hasattr(response, 'content') else str(response)
                        
                        # Add AI response to history
                        history.append({"role": "assistant", "content": ai_response})
                        
                        # Save to knowledge base
                        state["conversation"].append({"user": user_input, "ai": ai_response})
                        
                        # Update knowledge extraction
                        update_knowledge_base(state, user_input, ai_response)
                        
                        # Save to file
                        save_training_data(state)
                        
                        return history, "", state
                        
                    except Exception as e:
                        logger.error(f"Training error: {e}", exc_info=True)
                        error_msg = f"Error processing response: {str(e)}"
                        history.append({"role": "assistant", "content": error_msg})
                        return history, "", state
                
                def update_knowledge_base(state, user_input, ai_response):
                    """Extract and update structured knowledge from conversation."""
                    # Simple keyword-based extraction
                    lower_input = user_input.lower()
                    
                    if "table" in lower_input or "database" in lower_input:
                        if "tables" not in state["knowledge"]:
                            state["knowledge"]["tables"] = []
                        state["knowledge"]["tables"].append(user_input)
                    
                    if "relationship" in lower_input or "connect" in lower_input or "join" in lower_input:
                        if "relationships" not in state["knowledge"]:
                            state["knowledge"]["relationships"] = []
                        state["knowledge"]["relationships"].append(user_input)
                    
                    if "purpose" in lower_input or "used for" in lower_input:
                        if "purpose" not in state["knowledge"]:
                            state["knowledge"]["purpose"] = []
                        state["knowledge"]["purpose"].append(user_input)
                
                def save_training_data(state):
                    """Save training data to file."""
                    try:
                        from pathlib import Path
                        import json
                        
                        training_file = Path("training_data.json")
                        with open(training_file, "w") as f:
                            json.dump({
                                "conversation": state["conversation"],
                                "knowledge": state["knowledge"],
                                "timestamp": str(Path(training_file).stat().st_mtime if training_file.exists() else "new")
                            }, f, indent=2)
                    except Exception as e:
                        logger.error(f"Failed to save training data: {e}")
                
                def view_training_knowledge(state):
                    """Display structured knowledge learned by AI."""
                    knowledge = state.get("knowledge", {})
                    conversation = state.get("conversation", [])
                    
                    if not knowledge and not conversation:
                        return "No training data available yet. Start a conversation to train the AI!", gr.update(visible=True)
                    
                    display = "# 📚 AI Knowledge Base\n\n"
                    
                    if knowledge:
                        display += "## Structured Knowledge\n\n"
                        for category, items in knowledge.items():
                            display += f"### {category.title()}\n"
                            for item in items:
                                display += f"- {item}\n"
                            display += "\n"
                    
                    if conversation:
                        display += f"## Training Sessions\n\n"
                        display += f"Total exchanges: {len(conversation)}\n\n"
                        display += "### Recent Conversation\n\n"
                        for i, exchange in enumerate(conversation[-5:], 1):
                            display += f"**Q{i}:** {exchange['user']}\n\n"
                            display += f"**A{i}:** {exchange['ai']}\n\n"
                            display += "---\n\n"
                    
                    return display, gr.update(visible=True)
                
                def reset_training_session():
                    """Reset the training conversation."""
                    return [
                        {"role": "assistant", "content": "👋 Hi! I'm here to train the AI on your database. I'll ask you questions to understand your data structure, relationships, and business rules. Ready to begin?"}
                    ], {"stage": 0, "knowledge": {}, "conversation": []}, "", gr.update(visible=False)
                
                def export_knowledge(state):
                    """Export training data to downloadable file."""
                    try:
                        import tempfile
                        import json
                        from datetime import datetime
                        
                        data = {
                            "exported_at": datetime.now().isoformat(),
                            "conversation": state.get("conversation", []),
                            "knowledge": state.get("knowledge", {})
                        }
                        
                        temp_file = tempfile.NamedTemporaryFile(
                            mode='w',
                            suffix='.json',
                            prefix='training_data_',
                            delete=False
                        )
                        json.dump(data, temp_file, indent=2)
                        temp_file.close()
                        
                        return gr.update(value=temp_file.name, visible=True)
                    except Exception as e:
                        logger.error(f"Export failed: {e}")
                        return gr.update(visible=False)
                
                train_is_running = gr.State(False)
                
                # Event handlers with toggle button
                train_send_stop_btn.click(
                    lambda: (gr.update(value="⏹ Stop", variant="stop"), True),
                    outputs=[train_send_stop_btn, train_is_running]
                ).then(
                    process_training_response,
                    inputs=[training_input, training_chatbot, training_state],
                    outputs=[training_chatbot, training_input, training_state]
                ).then(
                    lambda: (False, gr.update(value="▶ Send", variant="primary")),
                    outputs=[train_is_running, train_send_stop_btn]
                )
                
                training_input.submit(
                    lambda: (gr.update(value="⏹ Stop", variant="stop"), True),
                    outputs=[train_send_stop_btn, train_is_running]
                ).then(
                    process_training_response,
                    inputs=[training_input, training_chatbot, training_state],
                    outputs=[training_chatbot, training_input, training_state]
                ).then(
                    lambda: (False, gr.update(value="▶ Send", variant="primary")),
                    outputs=[train_is_running, train_send_stop_btn]
                )
                
                view_knowledge_btn.click(
                    view_training_knowledge,
                    inputs=[training_state],
                    outputs=[knowledge_display, knowledge_display]
                )
                
                reset_training_btn.click(
                    reset_training_session,
                    outputs=[training_chatbot, training_state, training_input, knowledge_display]
                )
                
                export_training_btn.click(
                    export_knowledge,
                    inputs=[training_state],
                    outputs=[export_file]
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
