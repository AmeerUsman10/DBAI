"""
DBAI Chainlit Application - Full Featured Version
Modern chat interface with ALL features from Gradio version.
"""

import logging
import os
import time
import re
import uuid
from pathlib import Path
from typing import Optional, Dict, Any
from dotenv import load_dotenv
import chainlit as cl
from chainlit.input_widget import Select, Slider, TextInput, Switch

# Import ALL backend modules
from src.providers import create_provider
from src.database import get_sql_database, test_connection, reload_engine, run_query
from src.llm import make_sql_chain, extract_sql_from_response
from src.feedback import save_feedback, get_feedback_statistics, format_feedback_for_display
from src.session_tracker import get_session_tracker
from src.query_classifier import classify_query, needs_movement_clarification, get_clarification_for_classification
from src.query_templates import generate_sql_from_template
from src.query_optimizer import cache_query_result, get_cached_result, get_cache_stats
from src.clarity import analyze_query_clarity, needs_clarification
from src.learnings import save_learning, get_learning_stats
from src.quick_training import add_training_rule, get_training_stats
from src.custom_personas import get_persona_effectiveness_ranking, generate_persona_prompt

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
load_dotenv()

# Global state
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


def is_conversational_query(question: str, last_question: Optional[str] = None) -> bool:
    """Detect if user is asking a conversational question vs a data query."""
    question_lower = question.lower()
    
    conversational_patterns = [
        r'\b(the above|these results?|that data|this table|previous)\b',
        r'\b(why|how come|explain|what does (this|that|it) mean)\b',
        r'\b(different|same|changed|not matching)\b',
        r'\b(you (said|showed|returned|gave))\b',
        r'\b(earlier|before|last time)\b',
        r'^(why|how|what) (is|are|did|does)',
        r'\btell me (about|why|how)\b'
    ]
    for pattern in conversational_patterns:
        if re.search(pattern, question_lower):
            return True
    
    if len(question.split()) < 5:
        data_keywords = ['total', 'sum', 'count', 'show', 'list', 'get', 'find', 'top', 'supplier', 'yarn', 'greige']
        has_data_keyword = any(keyword in question_lower for keyword in data_keywords)
        if not has_data_keyword:
            return True
    
    return False


@cl.on_chat_start
async def start():
    """Initialize chat session with settings."""
    
    # Welcome message
    await cl.Message(
        content="""# 🤖 Welcome to DBAI!

I'm your Database AI Assistant. Ask me questions about your database in natural language.

**Features:**
- 🧠 Smart query classification with templates
- ⚡ Query caching for faster responses
- 🎯 Clarity checking and clarifications
- 📊 Learning from your feedback
- 👍👎 Per-message feedback

*Configure settings using the sidebar →*
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
                values=["gpt-4o-mini", "gpt-4", "gpt-3.5-turbo"],
                initial_index=0,
            ),
            Slider(
                id="temperature",
                label="🌡️ Temperature",
                initial=0.1,
                min=0,
                max=2,
                step=0.1,
            ),
            Slider(
                id="max_tokens",
                label="📝 Max Tokens",
                initial=2000,
                min=500,
                max=4000,
                step=100,
            ),
            Select(
                id="persona",
                label="👤 Persona",
                values=list(PERSONAS.keys()),
                initial_index=0,
            ),
            TextInput(
                id="db_server",
                label="🗄️ Database Server",
                initial="localhost",
            ),
            TextInput(
                id="db_name",
                label="📊 Database Name",
                initial="master",
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
        cl.user_session.set("provider_name", "openai")
        cl.user_session.set("model_name", "gpt-4o-mini")
        cl.user_session.set("pending_clarification", {})
        cl.user_session.set("last_query_info", {})
        
        logger.info("Session initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing session: {e}")
        await cl.Message(
            content=f"⚠️ **Initialization Error:** {str(e)}",
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
        
        # Update provider/LLM if changed
        if provider_name != cl.user_session.get("provider_name") or model != cl.user_session.get("model_name"):
            provider = create_provider(provider_name)
            llm = provider.get_llm(model, temperature, max_tokens)
            
            cl.user_session.set("provider", provider)
            cl.user_session.set("llm", llm)
            cl.user_session.set("provider_name", provider_name)
            cl.user_session.set("model_name", model)
            
            await cl.Message(
                content=f"✅ Updated to {provider_name} / {model}",
                author="System"
            ).send()
        
        cl.user_session.set("persona", persona)
        cl.user_session.set("temperature", temperature)
        cl.user_session.set("max_tokens", max_tokens)
        
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
        last_query = cl.user_session.get("last_query_info", {})
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
        
        await action.remove()
        
    except Exception as e:
        logger.error(f"Error saving thumbs up: {e}")


@cl.action_callback("thumbs_down")
async def on_thumbs_down(action: cl.Action):
    """Handle thumbs down feedback with comment collection."""
    message_id = action.value
    
    try:
        last_query = cl.user_session.get("last_query_info", {})
        
        # Ask for feedback details
        res = await cl.AskUserMessage(
            content="👎 What could be improved about this response?",
            timeout=300
        ).send()
        
        if res:
            feedback_text = res.get("output", "")
            
            # Save feedback with comment
            save_feedback(
                message_id=message_id,
                feedback_type="thumbs_down",
                question=last_query.get("question", ""),
                sql_query=last_query.get("sql", ""),
                response=last_query.get("response", ""),
                feedback_text=feedback_text,
                session_id=session_tracker.session_id
            )
            
            # Create training rule if comment provided
            if feedback_text:
                rule = f"CORRECTION for '{last_query.get('question', '')}': {feedback_text}"
                add_training_rule(rule)
                
                await cl.Message(
                    content="✅ Feedback submitted and training rule created! This will help improve similar queries.",
                    author="System"
                ).send()
            else:
                await cl.Message(
                    content="✅ Feedback submitted. Thanks!",
                    author="System"
                ).send()
        
        await action.remove()
        
    except Exception as e:
        logger.error(f"Error saving thumbs down: {e}")


@cl.on_message
async def main(message: cl.Message):
    """Process user messages with FULL feature set."""
    
    start_time = time.time()
    llm = cl.user_session.get("llm")
    persona = cl.user_session.get("persona", "default")
    pending_clarification = cl.user_session.get("pending_clarification", {})
    last_query_info = cl.user_session.get("last_query_info", {})
    
    if not llm:
        await cl.Message(
            content="❌ LLM not initialized. Please check your settings.",
            author="System"
        ).send()
        return
    
    # Check if this is a response to a clarification (user typed a number)
    if pending_clarification.get("question") and message.content.strip().isdigit():
        choice_num = int(message.content.strip())
        options = pending_clarification.get("options", [])
        
        if 1 <= choice_num <= len(options):
            original_query = pending_clarification.get("original_query", "")
            question = options[choice_num - 1]
            
            # Clear pending state
            cl.user_session.set("pending_clarification", {})
            
            # Process the clarified query
            await cl.Message(
                content=f"✅ Got it! Processing: **{question}**",
                author="System"
            ).send()
            
            # Reprocess with clarified question
            message.content = question
        else:
            await cl.Message(
                content=f"⚠️ Please choose a number between 1 and {len(options)}",
                author="System"
            ).send()
            return
    
    # Check for conversational query
    is_conversation = is_conversational_query(message.content, last_query_info.get("question"))
    
    if is_conversation and last_query_info.get("response"):
        # Handle as conversation
        try:
            msg = await cl.Message(content="", author="DBAI").send()
            await msg.stream_token("💬 ")
            
            conversation_prompt = f"""The user is asking a conversational question about previous results.

User's question: "{message.content}"
Previous query: "{last_query_info.get('question', 'None')}"
Previous result: "{str(last_query_info.get('response', ''))[:500]}"

Respond conversationally. Do NOT generate SQL."""
            
            response = llm.invoke(conversation_prompt)
            response_text = response.content if hasattr(response, 'content') else str(response)
            
            await msg.stream_token(response_text)
            await msg.update()
            return
            
        except Exception as e:
            logger.error(f"Conversation error: {e}")
            # Fall through to normal query handling
    
    # Get database
    db = get_sql_database()
    if not db:
        await cl.Message(
            content="❌ Database not connected. Please configure your database in settings.",
            author="System"
        ).send()
        return
    
    try:
        message_id = str(uuid.uuid4())[:8]
        msg = await cl.Message(content="", author="DBAI").send()
        
        # CLASSIFY QUERY
        classification = classify_query(message.content)
        logger.info(f"Query classified as: {classification['type']} (confidence: {classification['confidence']}%)")
        
        # Check if needs clarification
        if needs_movement_clarification(classification):
            clarifications = get_clarification_for_classification(classification)
            
            cl.user_session.set("pending_clarification", {
                "question": message.content,
                "options": clarifications,
                "original_query": message.content
            })
            
            response = f"I'd like to better understand your query: **\"{message.content}\"**\n\n"
            response += f"Could you clarify which of these you're looking for?\n\n"
            
            for i, option in enumerate(clarifications, 1):
                response += f"**{i}.** {option}\n"
            
            response += "\n*Simply reply with the number (1-4) that matches your intent.*"
            
            await msg.stream_token(response)
            await msg.update()
            return
        
        # CHECK CACHE FIRST
        cached_result = get_cached_result(message.content, fuzzy_match=True)
        if cached_result:
            sql_query, result, cache_metadata = cached_result
            logger.info(f"⚡ CACHE HIT!")
            
            await msg.stream_token(f"⚡ **From Cache** (saved {cache_metadata.get('tokens_saved', 50)} tokens)\n\n")
            
            if isinstance(result, dict) and 'rows' in result and 'columns' in result:
                await msg.stream_token(f"✅ **Found {len(result['rows'])} results:**\n\n")
                await msg.stream_token(format_result_table(result['rows'], result['columns']))
            
            await msg.update()
            
            # Add feedback
            await add_feedback_actions(msg, message_id, message.content, sql_query, str(result), True)
            return
        
        # GENERATE SQL (Template or LLM)
        sql_query = None
        generation_method = "llm"
        
        if classification['confidence'] >= 80:
            template_sql = generate_sql_from_template(classification)
            if template_sql:
                sql_query = template_sql
                generation_method = "template"
                logger.info(f"✅ Using TEMPLATE generation")
        
        if not sql_query:
            await msg.stream_token("🔍 Analyzing your question...\n\n")
            sql_chain = make_sql_chain(llm, db)
            sql_response = sql_chain({"question": message.content})
            
            if isinstance(sql_response, dict):
                sql_query = sql_response.get('result', '')
            else:
                sql_query = str(sql_response)
            sql_query = extract_sql_from_response(sql_query)
        
        method_icon = "⚡" if generation_method == "template" else "🤖"
        await msg.stream_token(f"{method_icon} **Generated SQL:**\n```sql\n{sql_query}\n```\n\n")
        
        # EXECUTE QUERY
        await msg.stream_token("⚙️ Executing query...\n\n")
        success, result = run_query(sql_query)
        
        if success:
            if isinstance(result, dict) and 'rows' in result and 'columns' in result:
                rows, columns = result['rows'], result['columns']
                
                await msg.stream_token(f"✅ **Found {len(rows)} results:**\n\n")
                await msg.stream_token(format_result_table(rows, columns))
                
                response_text = f"Found {len(rows)} results"
                
                # CACHE RESULT
                cache_query_result(message.content, sql_query, result, {
                    "generation_method": generation_method,
                    "tokens_saved": 50
                })
            else:
                await msg.stream_token(f"**Result:** {result}\n")
                response_text = str(result)
        else:
            await msg.stream_token(f"❌ **Error:** {result}\n")
            response_text = f"Error: {result}"
        
        # Add stats
        learning_stats = get_learning_stats()
        training_stats = get_training_stats()
        
        if learning_stats["total"] > 0 or training_stats["total"] > 0:
            await msg.stream_token(f"\n<sub>🧠 {learning_stats['total']} learned patterns · {training_stats['total']} training rules · {method_icon} {generation_method.title()}</sub>")
        
        await msg.update()
        
        # TRACK QUERY
        total_time_ms = int((time.time() - start_time) * 1000)
        session_tracker.track_query(
            user_question=message.content,
            clarity_analysis=None,
            llm_interaction={"provider": cl.user_session.get("provider_name"), "model": cl.user_session.get("model_name"), "generation_method": generation_method},
            execution={"sql_query": sql_query, "success": success},
            response={"type": "data" if success else "error", "text": response_text},
            performance={"total_time_ms": total_time_ms},
            error=None if success else {"message": response_text}
        )
        
        # Store for feedback
        cl.user_session.set("last_query_info", {
            "question": message.content,
            "sql": sql_query,
            "response": response_text,
            "success": success
        })
        
        # Add feedback actions
        await add_feedback_actions(msg, message_id, message.content, sql_query, response_text, success)
        
    except Exception as e:
        logger.error(f"Error processing message: {e}", exc_info=True)
        await cl.Message(
            content=f"❌ **Error:** {str(e)}",
            author="System"
        ).send()


def format_result_table(rows, columns, limit=50):
    """Format query result as markdown table."""
    table = "| " + " | ".join(columns) + " |\n"
    table += "| " + " | ".join(["---"] * len(columns)) + " |\n"
    
    for row in rows[:limit]:
        table += "| " + " | ".join(str(val) if val is not None else "" for val in row) + " |\n"
    
    if len(rows) > limit:
        table += f"\n*Showing first {limit} of {len(rows)} results*\n"
    
    return table


async def add_feedback_actions(msg, message_id, question, sql, response, success):
    """Add feedback action buttons to a message."""
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
    
    await cl.Message(
        content="**Rate this response:**",
        actions=actions,
        author="DBAI"
    ).send()
    
    cl.user_session.set("last_query_info", {
        "message_id": message_id,
        "question": question,
        "sql": sql,
        "response": response,
        "success": success
    })


if __name__ == "__main__":
    # Run with: chainlit run chainlit_app.py
    pass
