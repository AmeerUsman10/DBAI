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
            return True, "✅ Rule updated"
        else:
            return False, "Failed to save changes"
    except Exception as e:
        logger.error(f"Error updating rule: {e}", exc_info=True)
        return False, f"Error: {str(e)}"
