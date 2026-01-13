import logging
import sys
import os
# Ensure workspace root is on sys.path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src import main


def test_console_handler_handles_unicode():
    # Install logging handlers
    main.setup_logging()

    root = logging.getLogger()
    console_handlers = [h for h in root.handlers if isinstance(h, logging.StreamHandler)]
    assert console_handlers, "No StreamHandler found on root logger"

    handler = console_handlers[0]

    # Create a record with emoji/unicode and ensure emit does not raise
    record = logging.LogRecord(name="test", level=logging.INFO, pathname=__file__, lineno=1, msg="Test emoji ✅ 🔥 🎉", args=(), exc_info=None)

    try:
        handler.emit(record)
    except Exception as e:
        raise AssertionError(f"Console handler failed to emit unicode message: {e}")

    # If no exception, pass
    assert True
