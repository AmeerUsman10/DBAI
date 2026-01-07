"""
DBAI Chainlit Application
Modern chat interface for database AI assistant with per-message feedback.
"""

import logging
import os
from pathlib import Path
from dotenv import load_dotenv
import chainlit as cl
from chainlit.input_widget import Select, Slider, TextInput, Switch

# Import existing backend modules
from src.providers import create_provider
from src.database import get_sql_database, test_connection, reload_engine
from src.llm import make_sql_chain
from src.feedback import save_feedback
from src.session_tracker import get_session_tracker

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
load_dotenv()

# Global state (will be replaced with user session)
session_tracker = get_session_tracker()

# Persona definitions
PERSONAS = {
    "default": "You are a helpful AI assistant for database queries. Provide clear, accurate answers.",
    "data_analyst": "You are a senior data analyst. Provide detailed, technical answers with statistical insights.",
    "business_executive": "You are a business executive. Provide high-level summaries focused on KPIs and business impact.",
    "inventory_manager": "You are an inventory manager. Focus on stock levels, supplier performance, and logistics.",
    "sql_expert": "You are a SQL database expert. Focus on query optimization and performance.",
    "financial_analyst": "You are a financial analyst. Focus on financial metrics, profitability, and trends.",
}


@cl.on_chat_start
async def start():
    """Initialize chat session with settings."""
    
    # Welcome message
    await cl.Message(
        content="""# 🤖 Welcome to DBAI!

I'm your Database AI Assistant. Ask me questions about your database in natural language, and I'll help you get the answers you need.

**Quick Start:**
1. Select your preferred persona from settings ⚙️
2. Ask a question like: "Show me top 5 suppliers by yarn quantity"
3. Rate my responses with 👍 or 👎 to help me improve

*Configure your database and LLM settings using the sidebar →*
        """,
        author="DBAI"
    ).send()
    
    # Initialize session settings
    settings = await cl.ChatSettings(
        [
            Select(
                id="provider",
                label="🤖 LLM Provider",
                values=["openai", "groq"],
                initial_index=0,
            ),
            Select(
                id="model",
                label="📦 Model",
                values=["gpt-4o-mini", "gpt-4", "gpt-3.5-turbo"],  # Will update based on provider
                initial_index=0,
            ),
            Slider(
                id="temperature",
                label="🌡️ Temperature",
                initial=0.1,
                min=0,
                max=2,
                step=0.1,
                description="Controls randomness. Lower = more focused, higher = more creative"
            ),
            Slider(
                id="max_tokens",
                label="📝 Max Tokens",
                initial=2000,
                min=500,
                max=4000,
                step=100,
                description="Maximum length of generated responses"
            ),
            Select(
                id="persona",
                label="👤 Persona",
                values=list(PERSONAS.keys()),
                initial_index=0,
                description="Choose how the AI should respond to your questions"
            ),
            TextInput(
                id="db_server",
                label="🗄️ Database Server",
                initial="localhost",
                description="SQL Server hostname or IP"
            ),
            TextInput(
                id="db_name",
                label="📊 Database Name",
                initial="master",
                description="Name of the database to query"
            ),
        ]
    ).send()
    
    # Initialize provider and LLM
    try:
        provider = create_provider("openai")
        llm = provider.get_llm("gpt-4o-mini", 0.1, 2000)
        
        # Store in user session
        cl.user_session.set("provider", provider)
        cl.user_session.set("llm", llm)
        cl.user_session.set("persona", "default")
        cl.user_session.set("db_server", "localhost")
        cl.user_session.set("db_name", "master")
        
        logger.info("Session initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing session: {e}")
        await cl.Message(
            content=f"⚠️ **Initialization Error:** {str(e)}\n\nPlease check your API keys and database configuration.",
            author="System"
        ).send()


@cl.on_settings_update
async def settings_update(settings):
    """Handle settings changes."""
    try:
        provider_name = settings["provider"]
        model = settings["model"]
        temperature = settings["temperature"]
        max_tokens = settings["max_tokens"]
        persona = settings["persona"]
        db_server = settings["db_server"]
        db_name = settings["db_name"]
        
        # Update provider/LLM if changed
        current_provider = cl.user_session.get("provider")
        if current_provider is None or provider_name != cl.user_session.get("provider_name"):
            provider = create_provider(provider_name)
            llm = provider.get_llm(model, temperature, max_tokens)
            
            cl.user_session.set("provider", provider)
            cl.user_session.set("llm", llm)
            cl.user_session.set("provider_name", provider_name)
            
            await cl.Message(
                content=f"✅ Updated to {provider_name} / {model}",
                author="System"
            ).send()
        
        # Update session settings
        cl.user_session.set("persona", persona)
        cl.user_session.set("db_server", db_server)
        cl.user_session.set("db_name", db_name)
        cl.user_session.set("temperature", temperature)
        cl.user_session.set("max_tokens", max_tokens)
        
        logger.info(f"Settings updated: {provider_name}/{model}, persona={persona}")
        
    except Exception as e:
        logger.error(f"Error updating settings: {e}")
        await cl.Message(
            content=f"❌ **Settings Error:** {str(e)}",
            author="System"
        ).send()


@cl.action_callback("thumbs_up")
async def on_thumbs_up(action: cl.Action):
    """Handle thumbs up feedback."""
    message_id = action.value
    
    try:
        # Save feedback
        last_query = cl.user_session.get("last_query", {})
        save_feedback(
            message_id=message_id,
            feedback_type="thumbs_up",
            question=last_query.get("question", ""),
            sql_query=last_query.get("sql", ""),
            response=last_query.get("response", ""),
            session_id=session_tracker.session_id
        )
        
        await cl.Message(
            content="✅ Thanks for your positive feedback!",
            author="System"
        ).send()
        
        # Remove the action buttons
        await action.remove()
        
    except Exception as e:
        logger.error(f"Error saving thumbs up: {e}")


@cl.action_callback("thumbs_down")
async def on_thumbs_down(action: cl.Action):
    """Handle thumbs down feedback."""
    message_id = action.value
    
    try:
        # Save feedback
        last_query = cl.user_session.get("last_query", {})
        save_feedback(
            message_id=message_id,
            feedback_type="thumbs_down",
            question=last_query.get("question", ""),
            sql_query=last_query.get("sql", ""),
            response=last_query.get("response", ""),
            session_id=session_tracker.session_id
        )
        
        # Ask for details
        await cl.Message(
            content="👎 Thanks for the feedback! What could be improved about this response?",
            author="System"
        ).send()
        
        # Remove the action buttons
        await action.remove()
        
    except Exception as e:
        logger.error(f"Error saving thumbs down: {e}")


@cl.on_message
async def main(message: cl.Message):
    """Process user messages."""
    
    # Get session state
    llm = cl.user_session.get("llm")
    persona = cl.user_session.get("persona", "default")
    
    if not llm:
        await cl.Message(
            content="❌ LLM not initialized. Please check your settings.",
            author="System"
        ).send()
        return
    
    # Get database
    db = get_sql_database()
    if not db:
        await cl.Message(
            content="❌ Database not connected. Please configure your database in settings.",
            author="System"
        ).send()
        return
    
    try:
        # Show thinking indicator
        msg = cl.Message(content="", author="DBAI")
        await msg.send()
        
        # Generate SQL
        await msg.stream_token("🔍 Analyzing your question...\n\n")
        
        sql_chain = make_sql_chain(llm, db)
        sql_response = sql_chain({"question": message.content})
        
        # Extract SQL
        from src.llm import extract_sql_from_response
        if isinstance(sql_response, dict):
            sql_query = sql_response.get('result', '')
        else:
            sql_query = str(sql_response)
        sql_query = extract_sql_from_response(sql_query)
        
        await msg.stream_token(f"**Generated SQL:**\n```sql\n{sql_query}\n```\n\n")
        
        # Execute query
        await msg.stream_token("⚙️ Executing query...\n\n")
        
        from src.database import run_query
        success, result = run_query(sql_query)
        
        if success:
            # Format result
            if isinstance(result, dict) and 'rows' in result and 'columns' in result:
                rows = result['rows']
                columns = result['columns']
                
                await msg.stream_token(f"✅ **Found {len(rows)} results:**\n\n")
                
                # Create table
                table_md = "| " + " | ".join(columns) + " |\n"
                table_md += "| " + " | ".join(["---"] * len(columns)) + " |\n"
                
                for row in rows[:50]:  # Limit to 50 rows
                    table_md += "| " + " | ".join(str(val) if val is not None else "" for val in row) + " |\n"
                
                if len(rows) > 50:
                    table_md += f"\n*Showing first 50 of {len(rows)} results*\n"
                
                await msg.stream_token(table_md)
                
                response_text = f"Found {len(rows)} results"
            else:
                await msg.stream_token(f"**Result:** {result}\n")
                response_text = str(result)
        else:
            await msg.stream_token(f"❌ **Error:** {result}\n")
            response_text = f"Error: {result}"
        
        # Finalize message
        await msg.update()
        
        # Add feedback actions
        import uuid
        message_id = str(uuid.uuid4())[:8]
        
        actions = [
            cl.Action(
                name="thumbs_up",
                value=message_id,
                icon="thumbs-up",
                label="Helpful",
                description="This response was helpful"
            ),
            cl.Action(
                name="thumbs_down",
                value=message_id,
                icon="thumbs-down",
                label="Not helpful",
                description="This response needs improvement"
            ),
        ]
        
        # Send feedback prompt as separate message with actions
        await cl.Message(
            content="**Rate this response:**",
            actions=actions,
            author="DBAI"
        ).send()
        
        # Store query info for feedback
        cl.user_session.set("last_query", {
            "message_id": message_id,
            "question": message.content,
            "sql": sql_query,
            "response": response_text,
            "success": success
        })
        
        # Track in session
        session_tracker.track_query(
            user_question=message.content,
            clarity_analysis=None,
            llm_interaction={"provider": cl.user_session.get("provider_name", "unknown"), "model": "unknown"},
            execution={"sql_query": sql_query, "success": success},
            response={"type": "data" if success else "error", "text": response_text},
            performance={"total_time_ms": 0},
            error=None if success else {"message": response_text}
        )
        
    except Exception as e:
        logger.error(f"Error processing message: {e}", exc_info=True)
        await cl.Message(
            content=f"❌ **Error:** {str(e)}",
            author="System"
        ).send()


if __name__ == "__main__":
    # This will be called by: chainlit run chainlit_app.py
    pass
