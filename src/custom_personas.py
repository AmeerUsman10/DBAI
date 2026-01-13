"""
Custom Persona Management

Allows users to create, edit, and manage custom AI personas with tracking of effectiveness.
"""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

CUSTOM_PERSONAS_FILE = Path(__file__).parent.parent / "custom_personas.json"


def load_custom_personas() -> Dict:
    """Load custom personas from file."""
    try:
        if CUSTOM_PERSONAS_FILE.exists():
            with open(CUSTOM_PERSONAS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return _create_default_structure()
    except Exception as e:
        logger.error(f"Error loading custom personas: {e}")
        return _create_default_structure()


def _create_default_structure() -> Dict:
    """Create default personas structure."""
    return {
        "version": "1.0",
        "personas": {},
        "metadata": {
            "total_custom_personas": 0,
            "last_updated": None
        }
    }


def save_custom_persona(
    persona_id: str,
    name: str,
    description: str,
    tone: str = "professional",
    complexity: str = "balanced",
    domain_expertise: str = "general",
    custom_instructions: str = ""
) -> bool:
    """
    Save a custom persona.

    Args:
        persona_id: Unique identifier for the persona
        name: Display name
        description: Persona description
        tone: Communication tone (friendly/professional/technical)
        complexity: Response complexity (simple/balanced/detailed)
        domain_expertise: Domain focus (general/finance/logistics/retail/manufacturing)
        custom_instructions: Additional custom instructions for the LLM

    Returns:
        True if saved successfully
    """
    try:
        data = load_custom_personas()

        persona = {
            "id": persona_id,
            "name": name,
            "description": description,
            "tone": tone,
            "complexity": complexity,
            "domain_expertise": domain_expertise,
            "custom_instructions": custom_instructions,
            "created_at": data["personas"].get(persona_id, {}).get("created_at", datetime.now().isoformat()),
            "updated_at": datetime.now().isoformat(),
            "stats": data["personas"].get(persona_id, {}).get("stats", {
                "total_queries": 0,
                "successful_queries": 0,
                "failed_queries": 0,
                "avg_tokens": 0,
                "total_tokens": 0
            })
        }

        data["personas"][persona_id] = persona
        data["metadata"]["total_custom_personas"] = len(data["personas"])
        data["metadata"]["last_updated"] = datetime.now().isoformat()

        with open(CUSTOM_PERSONAS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.info(f"Saved custom persona: {name}")
        return True

    except Exception as e:
        logger.error(f"Error saving custom persona: {e}")
        return False


def delete_custom_persona(persona_id: str) -> bool:
    """Delete a custom persona."""
    try:
        data = load_custom_personas()

        if persona_id in data["personas"]:
            del data["personas"][persona_id]
            data["metadata"]["total_custom_personas"] = len(data["personas"])
            data["metadata"]["last_updated"] = datetime.now().isoformat()

            with open(CUSTOM_PERSONAS_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            logger.info(f"Deleted custom persona: {persona_id}")
            return True

        return False

    except Exception as e:
        logger.error(f"Error deleting custom persona: {e}")
        return False


def get_custom_persona(persona_id: str) -> Optional[Dict]:
    """Get a specific custom persona."""
    try:
        data = load_custom_personas()
        return data["personas"].get(persona_id)
    except Exception as e:
        logger.error(f"Error getting custom persona: {e}")
        return None


def list_custom_personas() -> List[Dict]:
    """List all custom personas."""
    try:
        data = load_custom_personas()
        return list(data["personas"].values())
    except Exception as e:
        logger.error(f"Error listing custom personas: {e}")
        return []


def update_persona_stats(persona_id: str, success: bool, tokens: int = 0):
    """
    Update usage statistics for a persona.

    Args:
        persona_id: Persona identifier
        success: Whether the query was successful
        tokens: Number of tokens used
    """
    try:
        data = load_custom_personas()

        if persona_id in data["personas"]:
            stats = data["personas"][persona_id]["stats"]
            stats["total_queries"] = stats.get("total_queries", 0) + 1

            if success:
                stats["successful_queries"] = stats.get("successful_queries", 0) + 1
            else:
                stats["failed_queries"] = stats.get("failed_queries", 0) + 1

            stats["total_tokens"] = stats.get("total_tokens", 0) + tokens
            stats["avg_tokens"] = stats["total_tokens"] / stats["total_queries"]

            with open(CUSTOM_PERSONAS_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            logger.debug(f"Updated stats for persona: {persona_id}")

    except Exception as e:
        logger.error(f"Error updating persona stats: {e}")


def get_persona_effectiveness_ranking() -> List[Dict]:
    """
    Get personas ranked by effectiveness (success rate).

    Returns:
        List of personas with their effectiveness scores
    """
    try:
        personas = list_custom_personas()

        ranked = []
        for persona in personas:
            stats = persona.get("stats", {})
            total = stats.get("total_queries", 0)

            if total > 0:
                success_rate = (stats.get("successful_queries", 0) / total) * 100
                avg_tokens = stats.get("avg_tokens", 0)

                ranked.append({
                    "id": persona["id"],
                    "name": persona["name"],
                    "success_rate": success_rate,
                    "total_queries": total,
                    "avg_tokens": avg_tokens,
                    "efficiency_score": (success_rate * 0.7) + ((1000 - min(avg_tokens, 1000)) / 1000 * 30)
                })

        # Sort by efficiency score
        ranked.sort(key=lambda x: x["efficiency_score"], reverse=True)
        return ranked

    except Exception as e:
        logger.error(f"Error getting persona effectiveness ranking: {e}")
        return []


def generate_persona_prompt(persona: Dict) -> str:
    """
    Generate additional prompt instructions for a custom persona.

    Args:
        persona: Persona dictionary

    Returns:
        Formatted prompt text
    """
    tone_map = {
        "friendly": "Use a warm, friendly, and conversational tone.",
        "professional": "Maintain a professional and business-appropriate tone.",
        "technical": "Use precise technical language and detailed explanations."
    }

    complexity_map = {
        "simple": "Keep responses simple and concise. Avoid technical jargon.",
        "balanced": "Balance detail with clarity. Explain technical terms when needed.",
        "detailed": "Provide comprehensive, detailed responses with technical depth."
    }

    domain_map = {
        "general": "",
        "finance": "Focus on financial metrics, cost analysis, and budget considerations.",
        "logistics": "Emphasize supply chain, inventory, and delivery metrics.",
        "retail": "Highlight sales trends, customer patterns, and product performance.",
        "manufacturing": "Focus on production metrics, quality control, and efficiency."
    }

    prompt = f"\n**PERSONA: {persona['name']}**\n"
    prompt += f"{persona['description']}\n\n"
    prompt += f"Tone: {tone_map.get(persona['tone'], tone_map['professional'])}\n"
    prompt += f"Complexity: {complexity_map.get(persona['complexity'], complexity_map['balanced'])}\n"

    if persona['domain_expertise'] != "general":
        prompt += f"Domain Focus: {domain_map.get(persona['domain_expertise'], '')}\n"

    if persona.get('custom_instructions'):
        prompt += f"\nAdditional Instructions:\n{persona['custom_instructions']}\n"

    return prompt
