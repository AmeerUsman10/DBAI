"""
DBAI Main Application Entry Point
Sets up logging and launches the Gradio UI.
"""
import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler

def setup_logging():
    """Configure logging with console and rotating file handler."""
    # Create logs directory if it doesn't exist
    log_dir = Path(__file__).parent.parent / "logs"
    log_dir.mkdir(exist_ok=True)
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Console handler with Unicode-safe emit to avoid Windows cp1252 crashes
    class SafeStreamHandler(logging.StreamHandler):
        def emit(self, record):
            try:
                super().emit(record)
            except UnicodeEncodeError:
                # Formatting first to avoid relying on super() after encoding failure
                try:
                    msg = self.format(record)
                except Exception:
                    msg = str(record)
                stream = self.stream
                # Try writing with replacement for unencodable characters
                try:
                    stream.write(msg + self.terminator)
                    stream.flush()
                except Exception:
                    try:
                        safe_msg = msg.encode(getattr(stream, 'encoding', 'utf-8') or 'utf-8', errors='replace').decode(getattr(stream, 'encoding', 'utf-8') or 'utf-8', errors='replace')
                        stream.write(safe_msg + self.terminator)
                        stream.flush()
                    except Exception:
                        # Give up silently to avoid crashing the app due to logging
                        pass

    console_handler = SafeStreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    
    # Rotating file handler for diagnostics (force UTF-8 encoding)
    file_handler = RotatingFileHandler(
        log_dir / "diagnostics.log",
        maxBytes=5*1024*1024,  # 5 MB
        backupCount=3,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    
    # Root logger configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
    
    # Reduce verbosity of some libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("gradio").setLevel(logging.INFO)
    logging.getLogger("PIL").setLevel(logging.INFO)  # Suppress PIL image plugin debug messages
    logging.getLogger("matplotlib").setLevel(logging.INFO)  # Suppress matplotlib debug messages
    logging.getLogger("asyncio").setLevel(logging.INFO)  # Suppress asyncio debug messages
    logging.getLogger("urllib3").setLevel(logging.INFO)  # Suppress urllib3 debug messages
    logging.getLogger("openai._base_client").setLevel(logging.INFO)  # Suppress OpenAI debug messages
    
    logging.info("DBAI application starting...")

def main():
    """Main application entry point."""
    setup_logging()
    
    try:
        from src.ui import build_ui
        import gradio as gr
        
        # Build and launch the Gradio interface
        demo = build_ui()
        demo.launch(
            server_name="127.0.0.1",
            server_port=7860,
            share=False,
            show_error=True
        )
    except Exception as e:
        logging.error(f"Failed to start application: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
