# DBAI - Database AI Assistant

An interactive AI-powered database assistant with natural language query capabilities.

## Features

- 💬 **Natural Language Queries**: Ask questions about your database in plain English
- ⚙️ **Flexible Provider Support**: Works with Groq and OpenAI models
- 📥 **Excel Import**: Upload and import Excel files directly to your database
- 🔍 **AI-Powered Analysis**: Automatic data description and schema inference
- 🎯 **Interactive Settings**: Configure database and LLM settings without restarting
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

## Security Notes

- API keys are stored in `.env` and never exposed in the UI
- Database passwords are redacted in diagnostics output
- SQL queries are validated to prevent dangerous operations (DROP, DELETE, etc.)
- Table names are sanitized before import

## Development

The application structure:
- `app.py` - Application entry point
- `src/main.py` - Main launcher with logging setup
- `src/ui.py` - Gradio UI interface
- `src/providers.py` - LLM provider wrapper
- `src/database.py` - Database connection management
- `src/llm.py` - Prompt templates and chains
- `src/uploader.py` - Excel import functionality
- `src/diagnostics.py` - Diagnostics collection
- `src/trainer.py` - Training module (demo)
