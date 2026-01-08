"""
Quick Training Module
Handles free-form natural language training instructions.
"""
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)

TRAINING_FILE = Path(__file__).parent.parent / "quick_training_rules.json"
AUDIT_FILE = Path(__file__).parent.parent / "logs" / "training_rule_audit.json"

def load_training_rules() -> Dict:
    """Load quick training rules."""
    if not TRAINING_FILE.exists():
        return {
            "rules": [],
            "metadata": {
                "total_rules": 0,
                "last_updated": None
            }
        }
    
    try:
        with open(TRAINING_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading training rules: {e}")
        return {"rules": [], "metadata": {"total_rules": 0, "last_updated": None}}

def save_training_rules(rules_data: Dict) -> bool:
    """Save training rules."""
    try:
        with open(TRAINING_FILE, 'w', encoding='utf-8') as f:
            json.dump(rules_data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        logger.error(f"Error saving training rules: {e}")
        return False

def _append_rule_audit(action: str, rule_index: int, details: Dict):
    """Append a rule audit event to JSON log."""
    try:
        AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)
        event = {
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "rule_index": rule_index,
            "details": details or {}
        }
        data = []
        if AUDIT_FILE.exists():
            try:
                with open(AUDIT_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except Exception:
                data = []
        data.append(event)
        with open(AUDIT_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

def add_training_rule(instruction: str, owner: str = "", priority: int = 5, status: str = "draft") -> Tuple[bool, str]:
    """
    Add a free-form training instruction.
    
    Args:
        instruction: Natural language training instruction
        
    Returns:
        Tuple of (success, message)
    """
    if not instruction.strip():
        return False, "Instruction cannot be empty"
    
    try:
        rules_data = load_training_rules()
        
        # Add new rule
        # Normalize fields
        status_norm = status if status in {"draft", "approved", "deprecated"} else "draft"
        try:
            prio = int(priority)
        except Exception:
            prio = 5
        prio = max(1, min(prio, 10))

        new_rule = {
            "instruction": instruction.strip(),
            "added_at": datetime.now().isoformat(),
            "usage_count": 0,
            "owner": owner or "",
            "priority": prio,
            "status": status_norm
        }
        
        rules_data["rules"].append(new_rule)
        rules_data["metadata"]["total_rules"] = len(rules_data["rules"])
        rules_data["metadata"]["last_updated"] = datetime.now().isoformat()
        
        # Save
        if save_training_rules(rules_data):
            try:
                _append_rule_audit("add", len(rules_data["rules"]), {"instruction": instruction.strip(), "owner": owner, "priority": prio, "status": status_norm})
            except Exception:
                pass
            return True, f"✅ Training rule added! Total rules: {rules_data['metadata']['total_rules']}"
        else:
            return False, "Failed to save training rule"
            
    except Exception as e:
        logger.error(f"Error adding training rule: {e}", exc_info=True)
        return False, f"Error: {str(e)}"

def get_training_rules_for_prompt() -> str:
    """
    Get all training rules formatted for LLM prompt injection.
    
    Returns:
        Formatted string with all training rules
    """
    try:
        rules_data = load_training_rules()
        
        if not rules_data["rules"]:
            return ""
        
        # Use only approved rules, ordered by priority (lower number = higher priority)
        approved = [r for r in rules_data["rules"] if r.get("status", "draft") == "approved"]
        approved = sorted(approved, key=lambda r: r.get("priority", 5))
        if not approved:
            return ""

        prompt = "\n### User-Defined Training Rules (Approved):\n"
        prompt += "The user has provided the following specific instructions on how to interpret queries:\n\n"
        for i, rule in enumerate(approved, 1):
            prompt += f"{i}. {rule['instruction']}\n"
        
        prompt += "\nIMPORTANT: Follow these rules precisely when generating SQL queries.\n"
        
        return prompt
        
    except Exception as e:
        logger.error(f"Error formatting training rules: {e}")
        return ""

def get_relevant_approved_rules(question: str, max_rules: int = 3) -> List[Tuple[int, Dict]]:
    """
    Select a small set of approved rules relevant to the current question.
    Returns list of tuples (global_index, rule_dict) ordered by relevance and priority.
    """
    try:
        data = load_training_rules()
        rules = data.get("rules", [])
        if not rules:
            return []

        # Tokenize question
        q_tokens = set(_tokenize(question))
        if not q_tokens:
            q_tokens = set()

        # Common domain keywords to help matching
        domain_keywords = {"supplier","arrival","issue","rejection","movement","yarn","greige","count","top","total","ranking","breakdown"}
        q_tokens |= (domain_keywords & q_tokens)

        # Score approved rules by token overlap + priority
        scored: List[Tuple[int, Dict, float, int]] = []  # (index, rule, score, priority)
        for i, r in enumerate(rules, 1):  # global 1-based index
            if r.get("status","draft") != "approved":
                continue
            r_tokens = set(_tokenize(r.get("instruction","")))
            if not r_tokens:
                continue
            inter = len(q_tokens & r_tokens)
            union = len(q_tokens | r_tokens) or 1
            overlap = inter / union
            prio = int(r.get("priority",5))
            # Combine: higher overlap, lower priority is better
            score = overlap + (1.0 / (prio + 1))
            scored.append((i, r, score, prio))

        if not scored:
            return []

        # Sort by score desc, then priority asc
        scored.sort(key=lambda t: (-t[2], t[3]))
        top = scored[:max_rules]
        return [(idx, rule) for idx, rule, _, _ in top]
    except Exception as e:
        logger.error(f"Error selecting relevant rules: {e}")
        return []

def get_approved_rules() -> List[Dict]:
    """Return approved training rules ordered by priority."""
    try:
        data = load_training_rules()
        rules = [r for r in data.get("rules", []) if r.get("status", "draft") == "approved"]
        rules.sort(key=lambda r: r.get("priority", 5))
        return rules
    except Exception as e:
        logger.error(f"Error getting approved rules: {e}")
        return []

def bump_rule_usage(indices: List[int]) -> None:
    """Increment usage_count for specific rules by 1 each. Indices are 1-based into current rules list."""
    if not indices:
        return
    try:
        data = load_training_rules()
        rules = data.get("rules", [])
        # Ensure unique indices and valid range
        for idx in sorted(set(indices)):
            if 1 <= idx <= len(rules):
                rules[idx - 1]["usage_count"] = int(rules[idx - 1].get("usage_count", 0)) + 1
        data["metadata"]["last_updated"] = datetime.now().isoformat()
        save_training_rules(data)
    except Exception as e:
        logger.error(f"Error bumping rule usage: {e}")

def get_training_stats() -> Dict:
    """Get training rules statistics."""
    try:
        rules_data = load_training_rules()
        
        return {
            "total": rules_data["metadata"]["total_rules"],
            "last_updated": rules_data["metadata"].get("last_updated"),
            "recent_rules": rules_data["rules"][-5:] if rules_data["rules"] else []
        }
    except Exception as e:
        logger.error(f"Error getting training stats: {e}")
        return {"total": 0, "last_updated": None, "recent_rules": []}

def format_rules_display() -> str:
    """Format all rules for display in UI."""
    try:
        rules_data = load_training_rules()
        
        if not rules_data["rules"]:
            return "No training rules yet. Add your first rule above!"
        
        output = f"### Active Training Rules ({rules_data['metadata']['total_rules']} total)\n\n"
        
        for i, rule in enumerate(reversed(rules_data["rules"]), 1):
            added_date = rule.get("added_at", "Unknown")
            if added_date != "Unknown":
                try:
                    dt = datetime.fromisoformat(added_date)
                    added_date = dt.strftime("%Y-%m-%d %H:%M")
                except:
                    pass
            
            output += f"**Rule #{len(rules_data['rules']) - i + 1}** (Added: {added_date})\n"
            output += f"> {rule['instruction']}\n"
            output += f"- Status: {rule.get('status','draft')} · Priority: {rule.get('priority',5)} · Owner: {rule.get('owner','')}\n\n"
        
        return output
        
    except Exception as e:
        logger.error(f"Error formatting rules display: {e}")
        return f"Error loading rules: {str(e)}"

def delete_rule(rule_index: int) -> Tuple[bool, str]:
    """Delete a training rule by index (1-based)."""
    try:
        rules_data = load_training_rules()
        
        if rule_index < 1 or rule_index > len(rules_data["rules"]):
            return False, f"Invalid rule number. Must be between 1 and {len(rules_data['rules'])}"
        
        # Remove rule (convert to 0-based index)
        deleted_rule = rules_data["rules"].pop(rule_index - 1)
        
        # Update metadata
        rules_data["metadata"]["total_rules"] = len(rules_data["rules"])
        rules_data["metadata"]["last_updated"] = datetime.now().isoformat()
        
        # Save
        if save_training_rules(rules_data):
            try:
                _append_rule_audit("delete", rule_index, {"instruction": deleted_rule.get("instruction",""), "owner": deleted_rule.get("owner",""), "priority": deleted_rule.get("priority",5), "status": deleted_rule.get("status","draft")})
            except Exception:
                pass
            return True, f"✅ Deleted rule: \"{deleted_rule['instruction'][:50]}...\""
        else:
            return False, "Failed to save changes"
            
    except Exception as e:
        logger.error(f"Error deleting rule: {e}", exc_info=True)
        return False, f"Error: {str(e)}"

def update_rule(rule_index: int, owner: str = None, priority: int = None, status: str = None) -> Tuple[bool, str]:
    """Update governance fields for a rule by index (1-based)."""
    try:
        rules_data = load_training_rules()
        if rule_index < 1 or rule_index > len(rules_data["rules"]):
            return False, f"Invalid rule number. Must be between 1 and {len(rules_data['rules'])}"

        rule = rules_data["rules"][rule_index - 1]

        if owner is not None:
            rule["owner"] = owner
        if priority is not None:
            try:
                prio = int(priority)
            except Exception:
                prio = rule.get("priority", 5)
            rule["priority"] = max(1, min(prio, 10))
        if status is not None:
            rule["status"] = status if status in {"draft", "approved", "deprecated"} else rule.get("status", "draft")

        rules_data["metadata"]["last_updated"] = datetime.now().isoformat()
        if save_training_rules(rules_data):
            try:
                _append_rule_audit("update", rule_index, {"owner": owner, "priority": priority, "status": status})
            except Exception:
                pass
            return True, "✅ Rule updated"
        else:
            return False, "Failed to save changes"
    except Exception as e:
        logger.error(f"Error updating rule: {e}", exc_info=True)
        return False, f"Error: {str(e)}"

def _tokenize(text: str) -> List[str]:
    """Simple tokenizer for conflict detection."""
    if not text:
        return []
    import re
    tokens = re.findall(r"[a-zA-Z0-9]+", text.lower())
    stop = {"the","and","of","to","in","for","by","with","a","an","on","as","is","are","be"}
    return [t for t in tokens if t not in stop]

def detect_rule_conflicts(threshold: float = 0.6) -> List[Tuple[int,int,float]]:
    """Detect potentially overlapping/duplicate rules via Jaccard similarity.
    Returns list of (rule_index1, rule_index2, score) with 1-based indices.
    """
    try:
        data = load_training_rules()
        rules = data.get("rules", [])
        pairs: List[Tuple[int,int,float]] = []
        for i in range(len(rules)):
            t1 = set(_tokenize(rules[i].get("instruction","")))
            if not t1:
                continue
            for j in range(i+1, len(rules)):
                t2 = set(_tokenize(rules[j].get("instruction","")))
                if not t2:
                    continue
                inter = len(t1 & t2)
                union = len(t1 | t2)
                score = (inter / union) if union else 0.0
                if score >= threshold:
                    pairs.append((i+1, j+1, round(score, 2)))
        return pairs
    except Exception as e:
        logger.error(f"Error detecting rule conflicts: {e}")
        return []
