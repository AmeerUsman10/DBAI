"""
Training Consolidation Pipeline
Deduplicates and canonicalizes rules and learnings; promotes high-quality items.
"""

import logging
from pathlib import Path
import json
from datetime import datetime
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
RULES_FILE = PROJECT_ROOT / "quick_training_rules.json"
LEARNINGS_FILE = PROJECT_ROOT / "conversation_learnings.json"
SUGGESTIONS_FILE = PROJECT_ROOT / "logs" / "training" / "rule_suggestions.json"


def _load_json(path: Path) -> Dict:
    try:
        if path.exists():
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    except Exception as e:
        logger.error(f"Error loading {path}: {e}")
        return {}


def _save_json(path: Path, data: Dict) -> bool:
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        logger.error(f"Error saving {path}: {e}")
        return False


def consolidate_training() -> Tuple[bool, str]:
    """Run consolidation: dedupe suggestions, merge similar rules, promote approvals."""
    try:
        rules_data = _load_json(RULES_FILE) or {"rules": [], "metadata": {"total_rules": 0}}
        learnings_data = _load_json(LEARNINGS_FILE) or {"learnings": []}
        suggestions = _load_json(SUGGESTIONS_FILE) or []

        rules: List[Dict] = rules_data.get("rules", [])
        # 1) Deduplicate suggestions by text
        seen = set()
        unique_suggestions = []
        for s in suggestions:
            rule_text = (s.get("suggested_rule", "") or "").strip()
            if not rule_text:
                continue
            key = rule_text.lower()
            if key not in seen:
                seen.add(key)
                unique_suggestions.append(s)

        # 2) Promote repeated suggestions to approved rules
        suggestion_counts = {}
        for s in suggestions:
            text = (s.get("suggested_rule", "") or "").strip().lower()
            if text:
                suggestion_counts[text] = suggestion_counts.get(text, 0) + 1

        promoted = 0
        for s in unique_suggestions:
            text = (s.get("suggested_rule", "") or "").strip()
            if not text:
                continue
            count = suggestion_counts.get(text.lower(), 1)
            # Promote if suggested >= 2 times
            if count >= 2:
                # Check if already exists
                exists = any(r.get("instruction","" ).strip().lower() == text.lower() for r in rules)
                if not exists:
                    rules.append({
                        "instruction": text,
                        "added_at": datetime.now().isoformat(),
                        "usage_count": 0,
                        "owner": "auto",
                        "priority": 5,
                        "status": "approved"
                    })
                    promoted += 1

        # 3) Canonicalize learnings: merge duplicates by original_query
        learnings = learnings_data.get("learnings", [])
        by_original: Dict[str, Dict] = {}
        merged = 0
        for l in learnings:
            key = (l.get("original_query", "") or "").strip().lower()
            if not key:
                continue
            if key in by_original:
                # Merge usage_count and keep latest clarified/sql
                by_original[key]["usage_count"] = by_original[key].get("usage_count", 1) + l.get("usage_count", 1)
                by_original[key]["clarified_query"] = l.get("clarified_query") or by_original[key].get("clarified_query")
                by_original[key]["sql_query"] = l.get("sql_query") or by_original[key].get("sql_query")
                merged += 1
            else:
                by_original[key] = dict(l)

        # Rewrite learnings_data if any merges happened
        if merged > 0:
            learnings_data["learnings"] = list(by_original.values())

        # Update rules metadata
        rules_data["rules"] = rules
        rules_data.setdefault("metadata", {})
        rules_data["metadata"]["total_rules"] = len(rules)
        rules_data["metadata"]["last_updated"] = datetime.now().isoformat()

        _save_json(RULES_FILE, rules_data)
        _save_json(LEARNINGS_FILE, learnings_data)

        msg = (
            f"Consolidation complete: promoted={promoted}, merged_learnings={merged}, "
            f"total_rules={len(rules)}"
        )
        logger.info(msg)
        return True, msg
    except Exception as e:
        logger.error(f"Consolidation failed: {e}")
        return False, f"Error: {e}"
