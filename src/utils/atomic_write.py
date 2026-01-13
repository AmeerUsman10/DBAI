"""
Atomic write helpers for JSON files used in demo-safe persistence.

Provides simple atomic write (write temp + os.replace) and safe read helpers.
This intentionally avoids external locking libraries to keep the demo lightweight.
"""
import json
import os
import tempfile
from pathlib import Path
from typing import Any


def atomic_write_json(path: Path, data: Any) -> None:
    """Write JSON to `path` atomically by writing to a temp file and replacing.

    Args:
        path: destination Path
        data: Python object to serialize as JSON
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Create temp file in same directory to ensure os.replace is atomic on same FS
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp", text=True)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as tf:
            json.dump(data, tf, indent=2, ensure_ascii=False)
            tf.flush()
            os.fsync(tf.fileno())
        os.replace(tmp_path, str(path))
    finally:
        # Ensure no stray tmp file remains
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass


def atomic_read_json(path: Path, default: Any = None) -> Any:
    """Read JSON from `path`, returning `default` if unreadable or missing."""
    path = Path(path)
    if not path.exists():
        return default
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default
