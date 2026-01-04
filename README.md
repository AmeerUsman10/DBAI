# DBAI - Database AI Assistant

An interactive AI-powered database assistant with natural language query capabilities and intelligent training system.

## Features

- 💬 **Natural Language Queries**: Ask questions about your database in plain English
- 🧠 **Intelligent Training System**: AI learns from your interactions and gets smarter over time
- 🎯 **Smart Clarifications**: Detects vague queries and offers context-aware suggestions
- 🏭 **Business Context Aware**: Pre-configured for Pakistani textile industry (PKR, LBS, greige, etc.)
- ⚙️ **Flexible Provider Support**: Works with Groq and OpenAI models
- 📥 **Excel Import**: Upload and import Excel files directly to your database
- 🔍 **AI-Powered Analysis**: Automatic data description and schema inference
- 💾 **Learning Management**: Automatically saves successful query patterns for future use
- 📊 **Diagnostics**: Built-in diagnostics collector for troubleshooting

## Quick Start

### Installation

1. Clone the repository
2. Install dependencies:
   ```bash
   py -m pip install -r requirements.txt
   ```

3. Configure your database and API keys:
   - Copy `config.yaml.example` to `config.yaml` and update with your database settings
   - Copy `.env.example` to `.env` and add your API keys (Groq or OpenAI)

### Running the Application

Start the application:
```bash
py app.py
```

Open your browser and navigate to:
```
http://127.0.0.1:7860
```

## Usage Guide

### Settings Tab
- **Provider Selection**: Choose between Groq or OpenAI
- **Model Auto-Population**: Models are automatically listed when you select a provider
- **API Key Management**: Enter and save your API keys securely
- **Connection Testing**: Test provider connectivity before saving
- **Database Configuration**: Change database settings and they take effect immediately (no restart required)

### Chat Tab
- Ask natural language questions about your database
- View generated SQL queries and results
- Chat history is maintained during the session

### Import Data Tab
1. Upload one or more Excel files (.xlsx or .xls)
2. Click "Analyze Files" to preview data and see suggested table structures
3. Click "Describe with AI" for AI-powered insights about your data
4. Click "Import to Database" to create tables and import data
   - Table names are automatically sanitized and prefixed with `import_`
   - Enable "Overwrite existing tables" to replace existing data

### Diagnostics Tab
- Click "Collect Diagnostics" to gather system information, logs, and configuration
- Download the diagnostics file for troubleshooting
- API keys and passwords are automatically redacted

## Configuration

### config.yaml
```yaml
database:
  server: localhost
  database: your_database_name
  driver: ODBC Driver 17 for SQL Server
  username: your_username  # optional for Windows Auth
  password: your_password  # optional for Windows Auth

llm:
  provider: groq  # or openai
  model: llama-3.1-8b-instant
  temperature: 0.1
  max_tokens: 2000
```

### .env
```
GROQ_API_KEY=your_groq_api_key_here
OPENAI_API_KEY=your_openai_api_key_here
```

## Troubleshooting

If you encounter issues:
1. Check the Diagnostics tab for detailed logs
2. Verify your database connection settings in the Settings tab
3. Ensure your API keys are correctly configured
4. Check the `logs/diagnostics.log` file for detailed error messages

## 🎓 Intelligent Training System

This version includes an **amazing data training system** that makes your AI assistant smarter over time:

### Quick Start Guides
- **[QUICK_TRAINING_GUIDE.md](QUICK_TRAINING_GUIDE.md)** - ⚡ NEW! Write training rules in plain English
- **[TRAINING_GUIDE.md](TRAINING_GUIDE.md)** - Complete system documentation
- **[QUICK_REFERENCE.md](QUICK_REFERENCE.md)** - User-friendly quick reference

### What It Does
1. **⚡ Quick Training**: Write rules in plain English - "When I ask X, return Y"
2. **Understands Business Context**: Pre-loaded with Pakistani textile terminology (PKR, LBS, greige, CT, PC)
3. **Detects Vague Queries**: Automatically identifies when users need clarification
4. **Learns from Interactions**: Saves successful query patterns for future use
5. **Gets Smarter Over Time**: Each team member's clarifications help everyone else

### Quick Training Example
```
You write: "When I ask 'total greige rcvd', always return meters of greige fabric received"
Next query: "total greige rcvd"
AI returns: "1,234,556 Meters" ✅ (follows your rule immediately!)
```

### Traditional Flow Example
```
You: "supplier total"
AI: Could you clarify which of these you're looking for?
    1. Total amount in PKR per supplier
    2. Total LBS ordered per supplier
    3. Total bags per supplier
    4. List all supplier names
You: 1
AI: [Shows results]
    🧠 AI has learned 1 pattern from your team
```

Next time someone asks "supplier wise total", AI knows what they mean!

### System Files
- `metadata.json` - Business context and column definitions
- `conversation_learnings.json` - Learned query patterns (auto-generated)
- `src/clarity.py` - Query clarity analyzer
- `src/learnings.py` - Learning management system

## Security Notes

- API keys are stored in `.env` and never exposed in the UI
- Database passwords are redacted in diagnostics output
- SQL queries are validated to prevent dangerous operations (DROP, DELETE, etc.)
- Table names are sanitized before import

## Development

The application structure:
- `app.py` - Application entry point
- `src/main.py` - Main launcher with logging setup
- `src/ui.py` - Gradio UI interface with clarity integration
- `src/providers.py` - LLM provider wrapper
- `src/database.py` - Database connection management + metadata functions
- `src/llm.py` - Enhanced prompt templates with learning injection
- `src/uploader.py` - Excel import functionality
- `src/clarity.py` - Query clarity analysis and clarification generation
- `src/learnings.py` - Learning management with fuzzy matching
- `metadata.json` - Business context and column definitions
- `conversation_learnings.json` - Learned patterns storage
- `src/diagnostics.py` - Diagnostics collection
- `src/trainer.py` - Training module (demo)
