"""
Query Clarity Analyzer

Intelligently analyzes user queries to detect ambiguity and provide helpful clarifications.
Designed for Pakistani textile business context with understanding of informal query patterns.
"""

import re
import logging
from typing import Tuple, List, Dict
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)

# Vague query patterns commonly seen in business queries
VAGUE_PATTERNS = [
    (r'^\w+\s+name$', 'column_name_only', 'Requesting just a column name without action'),
    (r'^\w{1,15}$', 'single_word', 'Single word query without context'),
    (r'^\w+\s+total$', 'ambiguous_total', 'Total request without specifying what to aggregate'),
    (r'\bwise$', 'grouping_unclear', 'Grouping request without clear dimension'),
    (r'^show\s+\w+$', 'show_vague', 'Show command without specifics'),
    (r'^list\s+\w+$', 'list_vague', 'List command without details'),
    (r'^get\s+\w+$', 'get_vague', 'Get command without specifics'),
]

# Ambiguous terms that need clarification
AMBIGUOUS_TERMS = {
    'total': ['sum of amounts', 'count of records', 'aggregated metrics', 'grand total'],
    'name': ['list all names', 'search specific name', 'name with details'],
    'supplier': ['all suppliers', 'specific supplier', 'supplier summary', 'top suppliers'],
    'amount': ['total amount', 'average amount', 'amount breakdown', 'amount by category'],
    'show': ['display all records', 'display summary', 'display specific item'],
    'list': ['simple list', 'detailed list', 'sorted list', 'filtered list'],
    'greige': ['greige quantity', 'greige amount', 'greige suppliers', 'greige departments'],
    'yarn': ['yarn quantity', 'yarn amount', 'yarn suppliers', 'yarn types'],
    'top': ['top by amount', 'top by quantity', 'top by frequency', 'top overall'],
}

# Context-aware clarification templates
CLARIFICATION_TEMPLATES = {
    'supplier_name': [
        "List all unique supplier names",
        "Show top suppliers by total purchase amount",
        "Display supplier-wise summary with totals",
        "Search for a specific supplier by name"
    ],
    'greige_total': [
        "Total greige fabric quantity in meters",
        "Total greige fabric amount in PKR",
        "Greige fabric totals grouped by department",
        "Greige fabric totals grouped by supplier"
    ],
    'yarn_total': [
        "Total yarn weight in LBS",
        "Total yarn purchase amount in PKR",
        "Yarn totals grouped by supplier",
        "Yarn totals grouped by type"
    ],
    'amount_total': [
        "Sum of all amounts in PKR",
        "Total amount grouped by supplier",
        "Total amount by month/period",
        "Average amount per transaction"
    ],
    'department_wise': [
        "Show totals grouped by department",
        "Show record counts by department",
        "Show detailed breakdown by department",
        "Compare departments by total value"
    ],
    'supplier_wise': [
        "Show totals grouped by supplier",
        "Show purchase counts by supplier",
        "Show detailed transactions by supplier",
        "Rank suppliers by total amount"
    ],
    'top_supplier': [
        "Top suppliers by ARRIVAL (incoming stock)",
        "Top suppliers by ISSUE (outgoing/used stock)",
        "Top suppliers by REJECTION (returned stock)",
        "Top suppliers across ALL movement types"
    ],
    'quality_wise': [
        "Show fabric quantities by quality grade",
        "Show amounts by quality grade",
        "Compare quality grades by meters",
        "List all quality grades with counts"
    ],
    'generic': [
        "Show all matching records",
        "Show summary totals",
        "Show top results ranked by value",
        "Show detailed breakdown"
    ]
}


def analyze_query_clarity(query: str) -> Tuple[int, str, List[str]]:
    """
    Analyze query clarity and provide intelligent suggestions.
    
    Args:
        query: User's natural language query
        
    Returns:
        Tuple of (clarity_score, reason, clarification_options)
        - clarity_score: 0-100 (100 = perfectly clear)
        - reason: Explanation of the score
        - clarification_options: List of 4 suggested interpretations
    """
    if not query or not query.strip():
        return 0, "Empty query", []
    
    query_lower = query.strip().lower()
    score = 100
    reasons = []
    vague_type = None
    
    # Check query length
    word_count = len(query_lower.split())
    if word_count == 1:
        score -= 40
        reasons.append("Single word query - needs more context")
    elif word_count < 3:
        score -= 25
        reasons.append("Very short query - may be ambiguous")
    elif word_count < 5:
        score -= 15
        reasons.append("Short query - could be more specific")
    
    # Check for vague patterns
    for pattern, pattern_type, description in VAGUE_PATTERNS:
        if re.search(pattern, query_lower):
            score -= 25
            reasons.append(description)
            vague_type = pattern_type
            break
    
    # Check for ambiguous terms
    for term, interpretations in AMBIGUOUS_TERMS.items():
        if term in query_lower.split():
            score -= 15
            reasons.append(f"Ambiguous term: '{term}'")
            break
    
    # Check for missing key information
    if 'total' in query_lower and 'by' not in query_lower and 'of' not in query_lower:
        score -= 10
        reasons.append("Total requested without specifying dimension")
    
    # Check for supplier queries without movement type (CRITICAL business rule)
    supplier_keywords = ['top supplier', 'supplier rank', 'best supplier', 'supplier list', 'supplier']
    movement_keywords = ['arrival', 'issue', 'rejection', 'movement']
    
    if any(kw in query_lower for kw in supplier_keywords):
        if not any(mk in query_lower for mk in movement_keywords):
            score -= 35  # CRITICAL: Must go below 70 threshold to trigger clarification
            reasons.append("Supplier query without movement type (arrival/issue/rejection)")
            vague_type = 'top_supplier'
    
    # Ensure score stays in range
    score = max(0, min(100, score))
    
    # Generate reason string
    if score >= 80:
        reason = "Query is clear and specific"
    elif score >= 60:
        reason = "Query is somewhat clear: " + "; ".join(reasons[:2])
    else:
        reason = "Query needs clarification: " + "; ".join(reasons[:3])
    
    # Generate contextual clarifications
    clarifications = generate_clarifications(query_lower, vague_type)
    
    logger.info(f"Clarity analysis: '{query}' -> Score: {score}, Type: {vague_type}")
    
    return score, reason, clarifications


def generate_clarifications(query: str, vague_type: str = None) -> List[str]:
    """
    Generate intelligent, context-aware clarification options.
    
    Args:
        query: User's query (lowercase)
        vague_type: Type of vagueness detected
        
    Returns:
        List of 4 specific clarification options
    """
    # Detect query context
    if re.search(r'supplier.*name', query):
        return CLARIFICATION_TEMPLATES['supplier_name']
    
    elif re.search(r'greige.*total', query) or re.search(r'total.*greige', query):
        return CLARIFICATION_TEMPLATES['greige_total']
    
    elif re.search(r'yarn.*total', query) or re.search(r'total.*yarn', query):
        return CLARIFICATION_TEMPLATES['yarn_total']
    
    elif re.search(r'(amount|total).*total', query) or query in ['total', 'amount']:
        return CLARIFICATION_TEMPLATES['amount_total']
    
    elif re.search(r'department.*wise', query):
        return CLARIFICATION_TEMPLATES['department_wise']
    
    elif re.search(r'supplier.*wise', query):
        return CLARIFICATION_TEMPLATES['supplier_wise']
    
    elif re.search(r'quality.*wise', query):
        return CLARIFICATION_TEMPLATES['quality_wise']
    
    # Context-specific single words
    elif query == 'supplier' or query == 'suppliers':
        return CLARIFICATION_TEMPLATES['supplier_name']
    
    elif query == 'greige':
        return CLARIFICATION_TEMPLATES['greige_total']
    
    elif query == 'yarn':
        return CLARIFICATION_TEMPLATES['yarn_total']
    
    elif query in ['amount', 'total', 'price']:
        return CLARIFICATION_TEMPLATES['amount_total']
    
    # Default contextual suggestions
    else:
        return CLARIFICATION_TEMPLATES['generic']


def needs_clarification(score: int, threshold: int = 70) -> bool:
    """
    Determine if query needs clarification based on score.
    
    Args:
        score: Clarity score (0-100)
        threshold: Minimum acceptable score
        
    Returns:
        True if query should be clarified
    """
    return score < threshold


def get_clarification_stats() -> Dict:
    """Get statistics about clarity analysis."""
    try:
        from pathlib import Path
        import json
        
        learnings_file = Path(__file__).parent.parent / "conversation_learnings.json"
        if learnings_file.exists():
            with open(learnings_file, 'r') as f:
                data = json.load(f)
                return {
                    "total_clarifications": data['metadata'].get('clarifications_provided', 0),
                    "total_queries": data['metadata'].get('total_queries_processed', 0)
                }
        return {"total_clarifications": 0, "total_queries": 0}
    except Exception as e:
        logger.error(f"Error getting clarification stats: {e}")
        return {"total_clarifications": 0, "total_queries": 0}
