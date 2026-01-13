"""
Training Export/Import & Versioning
Exports current rules and learnings to timestamped version files and imports them.
"""
import json
from pathlib import Path
from datetime import datetime
from typing import Tuple

PROJECT_ROOT = Path(__file__).parent.parent
VERSIONS_DIR = PROJECT_ROOT / "logs" / "training" / "versions"
RULES_FILE = PROJECT_ROOT / "quick_training_rules.json"
LEARNINGS_FILE = PROJECT_ROOT / "conversation_learnings.json"


def export_training() -> Tuple[bool, str]:
    """Export current training rules and learnings to a timestamped JSON file."""
    try:
        VERSIONS_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = VERSIONS_DIR / f"training_snapshot_{ts}.json"
        data = {
            "timestamp": datetime.now().isoformat(),
            "rules": {},
            "learnings": {}
        }
        if RULES_FILE.exists():
            with open(RULES_FILE, 'r', encoding='utf-8') as f:
                data["rules"] = json.load(f)
        if LEARNINGS_FILE.exists():
            with open(LEARNINGS_FILE, 'r', encoding='utf-8') as f:
                data["learnings"] = json.load(f)
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True, str(out_path)
    except Exception as e:
        return False, str(e)


def import_training(file_path: str) -> Tuple[bool, str]:
    """Import training rules and learnings from a version file."""
    try:
        p = Path(file_path)
        if not p.exists():
            return False, "File not found"
        with open(p, 'r', encoding='utf-8') as f:
            data = json.load(f)
        rules = data.get("rules")
        learnings = data.get("learnings")
        if rules:
            with open(RULES_FILE, 'w', encoding='utf-8') as f:
                json.dump(rules, f, indent=2, ensure_ascii=False)
        if learnings:
            with open(LEARNINGS_FILE, 'w', encoding='utf-8') as f:
                json.dump(learnings, f, indent=2, ensure_ascii=False)
        return True, "Imported training data successfully"
    except Exception as e:
        return False, str(e)
