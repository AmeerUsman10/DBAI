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
                'provider': 'groq',
                'model': 'llama-3.1-8b-instant',
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
                        label="Your Question",
                        scale=4
                    )
                    submit_btn = gr.Button("Submit", variant="primary", scale=1)
                
                with gr.Row():
                    clear_btn = gr.Button("Clear Chat")
                    stop_btn = gr.Button("⏹️ Stop", variant="stop")
                
                # Store the current query event for cancellation
                query_event = submit_btn.click(
                    chat_query,
                    inputs=[question_input, chatbot],
                    outputs=[question_input, chatbot]
                )
                
                question_event = question_input.submit(
                    chat_query,
                    inputs=[question_input, chatbot],
                    outputs=[question_input, chatbot]
                )
                
                # Stop button cancels the ongoing query
                stop_btn.click(None, cancels=[query_event, question_event])
                
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
            
            # Train Tab - Interactive Q&A
            with gr.Tab("🎓 Train"):
                gr.Markdown("## Interactive Database Training")
                gr.Markdown("Teach the AI about your database by answering its questions.")
                
                with gr.Row():
                    with gr.Column(scale=1):
                        start_training_btn = gr.Button("Start Training Session", variant="primary", size="lg")
                        stop_training_btn = gr.Button("Stop Training", variant="stop")
                        
                    with gr.Column(scale=2):
                        training_progress = gr.Textbox(
                            label="Progress",
                            value="Click 'Start Training Session' to begin",
                            interactive=False,
                            lines=2
                        )
                
                ai_question = gr.Textbox(
                    label="AI Question",
                    placeholder="AI will ask questions about your database here...",
                    interactive=False,
                    lines=3
                )
                
                user_answer = gr.Textbox(
                    label="Your Answer",
                    placeholder="Type your answer here...",
                    lines=4
                )
                
                submit_answer_btn = gr.Button("Submit Answer", variant="primary")
                
                training_history = gr.Textbox(
                    label="Training History",
                    lines=10,
                    interactive=False
                )
                
                # Training functions
                def start_training():
                    questions = [
                        "What is the main purpose of your database? What kind of data does it store?",
                        "What are the most important tables in your database? List their names.",
                        "Describe the relationships between your main tables. Which tables are connected and how?",
                        "What are the common queries or questions users ask about this data?",
                        "Are there any special business rules or constraints I should know about?"
                    ]
                    return questions[0], "Training started! Answer the questions below.", ""
                
                training_state = gr.State({"question_index": 0, "history": []})
                
                def submit_training_answer(answer, state):
                    if not answer.strip():
                        return gr.update(), gr.update(), gr.update()
                    
                    questions = [
                        "What is the main purpose of your database? What kind of data does it store?",
                        "What are the most important tables in your database? List their names.",
                        "Describe the relationships between your main tables. Which tables are connected and how?",
                        "What are the common queries or questions users ask about this data?",
                        "Are there any special business rules or constraints I should know about?"
                    ]
                    
                    current_idx = state.get("question_index", 0)
                    history = state.get("history", [])
                    
                    # Save current Q&A
                    history.append(f"Q{current_idx + 1}: {questions[current_idx]}\nA: {answer}\n")
                    
                    # Move to next question
                    next_idx = current_idx + 1
                    
                    if next_idx < len(questions):
                        next_question = questions[next_idx]
                        progress = f"Question {next_idx + 1} of {len(questions)}"
                        state["question_index"] = next_idx
                        state["history"] = history
                        return next_question, progress, "\n".join(history), state, ""
                    else:
                        # Training complete
                        final_history = "\n".join(history)
                        # Save to file
                        try:
                            from pathlib import Path
                            training_file = Path("training_data.txt")
                            with open(training_file, "w") as f:
                                f.write(final_history)
                        except:
                            pass
                        return "Training session complete! ✅", "Completed all questions. Training data saved.", final_history, {"question_index": 0, "history": []}, ""
                
                start_training_btn.click(
                    start_training,
                    outputs=[ai_question, training_progress, training_history]
                )
                
                submit_answer_btn.click(
                    submit_training_answer,
                    inputs=[user_answer, training_state],
                    outputs=[ai_question, training_progress, training_history, training_state, user_answer]
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
