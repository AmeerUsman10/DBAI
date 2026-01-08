"""
Query Classification and Template Matching
Handles 80% of common queries with templates, falls back to LLM for complex cases.
"""
import re
import logging
from typing import Dict, Optional, List

logger = logging.getLogger(__name__)

# Query type patterns
RANKING_PATTERNS = [
    r'top\s+(\d+)\s+(\w+)',  # "top 10 suppliers"
    r'best\s+(\d+)\s+(\w+)',  # "best 5 customers"
    r'highest\s+(\w+)',  # "highest amount supplier"
    r'top\s+(\w+)',  # "top supplier" (assume top 10)
]

AGGREGATION_PATTERNS = [
    r'total\s+(\w+)',  # "total yarn"
    r'sum\s+of\s+(\w+)',  # "sum of amount"
    r'how\s+much\s+(\w+)',  # "how much inventory"
    r'(\w+)\s+total',  # "yarn total"
]

SEGMENTATION_PATTERNS = [
    r'by\s+(\w+)',  # "by supplier", "by type"
    r'each\s+(\w+)',  # "each department"
    r'all\s+(\w+)\s+types?',  # "all entry types"
    r'grouped?\s+by\s+(\w+)',  # "group by supplier"
]

DETAIL_PATTERNS = [
    r'show\s+(\w+)',  # "show supplier"
    r'list\s+(\w+)',  # "list arrivals"
    r'details?\s+(?:about|for|of)\s+(.+)',  # "detail about gul ahmad"
    r'all\s+(\w+)\s+records?',  # "all yarn records"
]

TIME_BASED_PATTERNS = [
    r'last\s+(\d+)\s+(days?|months?|years?)',  # "last 30 days", "last 3 months"
    r'this\s+(month|quarter|year)',  # "this month", "this year"
    r'(?:in|for)\s+(january|february|march|april|may|june|july|august|september|october|november|december)',  # "in January"
    r'between\s+(.+?)\s+and\s+(.+)',  # "between 2024-01-01 and 2024-12-31"
    r'(monthly|quarterly|yearly)\s+(?:total|breakdown|trend)',  # "monthly breakdown"
    r'year\s+to\s+date|ytd',  # "year to date"
]

COMPARISON_PATTERNS = [
    r'compare\s+(\w+)\s+(?:vs|versus|and)\s+(\w+)',  # "compare yarn vs greige"
    r'(\w+)\s+vs\s+(\w+)',  # "department A vs B"
    r'difference\s+between\s+(\w+)\s+and\s+(\w+)',  # "difference between yarn and greige"
    r'this\s+(month|quarter|year)\s+vs\s+last\s+(month|quarter|year)',  # "this month vs last month"
]

# Movement type keywords
MOVEMENT_TYPES = {
    'arrival': 'Yarn Arrival',
    'arrivals': 'Yarn Arrival',
    'issue': 'Yarn Issue',
    'issues': 'Yarn Issue',
    'rejection': 'Yarn Rejection',
    'rejections': 'Yarn Rejection',
}

# Metric mappings
METRICS = {
    'amount': {'yarn': 'AMOUNT', 'greige': 'AMOUNT'},
    'value': {'yarn': 'AMOUNT', 'greige': 'AMOUNT'},
    'quantity': {'yarn': 'LBS', 'greige': 'METER'},
    'lbs': {'yarn': 'LBS'},
    'meters': {'greige': 'METER'},
    'bags': {'yarn': 'BAGS'},
}

# Entity mappings
ENTITIES = {
    'supplier': {'yarn': 'SUPPLIER', 'greige': 'SUPP_NAME'},
    'suppliers': {'yarn': 'SUPPLIER', 'greige': 'SUPP_NAME'},
    'quality': {'yarn': 'QUALITY', 'greige': 'AC_NAME'},
    'type': {'yarn': 'YARN', 'greige': 'AC_NAME'},
}


def classify_query(query: str) -> Dict:
    """
    Classify user query and extract parameters.
    
    Returns:
        {
            'type': 'ranking|aggregation|segmentation|detail|comparison|unknown',
            'confidence': 0-100,
            'params': {
                'entity': 'supplier|quality|type',
                'metric': 'AMOUNT|LBS|METER',
                'limit': int,
                'movement_type': 'Yarn Arrival|Yarn Issue|Yarn Rejection',
                'department': 'yarn|greige|both',
                'specific_value': str (for detail queries)
            }
        }
    """
    query_lower = query.lower().strip()
    params = {
        'entity': None,
        'metric': 'AMOUNT',  # Default to amount
        'limit': 10,  # Default top 10
        'movement_type': None,
        'department': 'both',  # BUSINESS RULE: Default to both departments for suppliers
        'specific_value': None,
        'breakdown': None,  # For multi-dimensional segmentation
        'time_filter': None,  # For date-based filtering
        'comparison': None  # For comparison queries
    }
    
    # Detect breakdown/segmentation request
    breakdown_keywords = [
        'department wise', 'by department', 'departmentwise',
        'by movement type', 'movement type wise', 
        'broken down', 'breakdown', 'break down',
        'segmented', 'segment',
        'across all', 'all movement types',
        'for each', 'each department'
    ]
    
    if any(keyword in query_lower for keyword in breakdown_keywords):
        params['breakdown'] = ['department', 'movement_type']
        logger.info(f"Detected breakdown request in query: {query}")
    
    # Detect department
    if 'greige' in query_lower and 'yarn' in query_lower:
        params['department'] = 'both'
    elif 'greige' in query_lower:
        params['department'] = 'greige'
    elif 'yarn' in query_lower:
        params['department'] = 'yarn'
    
    # Detect movement type
    for keyword, entry_type in MOVEMENT_TYPES.items():
        if keyword in query_lower:
            params['movement_type'] = entry_type
            break
    
    # Try TIME_BASED patterns first (high priority)
    for pattern in TIME_BASED_PATTERNS:
        match = re.search(pattern, query_lower)
        if match:
            groups = match.groups()
            
            # Detect if it's a time-filtered ranking/aggregation
            is_ranking = any(re.search(p, query_lower) for p in RANKING_PATTERNS)
            is_aggregation = any(re.search(p, query_lower) for p in AGGREGATION_PATTERNS)
            is_breakdown = 'monthly' in query_lower or 'quarterly' in query_lower or 'yearly' in query_lower
            
            if is_breakdown:
                params['time_filter'] = {'type': 'breakdown', 'period': groups[0] if groups else 'monthly'}
                params['breakdown'] = ['time']
                return {
                    'type': 'time_breakdown',
                    'confidence': 90,
                    'params': params
                }
            else:
                # Extract time filter details
                params['time_filter'] = {'type': 'filter', 'raw': match.group(0), 'groups': groups}
                # Continue to check if it's ranking or aggregation with time filter
                break
    
    # Try COMPARISON patterns
    for pattern in COMPARISON_PATTERNS:
        match = re.search(pattern, query_lower)
        if match:
            groups = match.groups()
            params['comparison'] = {'entities': groups}
            
            return {
                'type': 'comparison',
                'confidence': 85,
                'params': params
            }
    
    # Try RANKING patterns
    for pattern in RANKING_PATTERNS:
        match = re.search(pattern, query_lower)
        if match:
            groups = match.groups()
            
            # Extract limit
            if groups[0].isdigit():
                params['limit'] = int(groups[0])
                entity_word = groups[1] if len(groups) > 1 else 'supplier'
            else:
                entity_word = groups[0]
            
            # Map entity
            for entity_key, entity_map in ENTITIES.items():
                if entity_key in entity_word:
                    params['entity'] = entity_key
                    break
            
            if not params['entity']:
                params['entity'] = 'supplier'  # Default
            
            return {
                'type': 'ranking',
                'confidence': 95,
                'params': params
            }
    
    # Try AGGREGATION patterns
    for pattern in AGGREGATION_PATTERNS:
        match = re.search(pattern, query_lower)
        if match:
            return {
                'type': 'aggregation',
                'confidence': 90,
                'params': params
            }
    
    # Try SEGMENTATION patterns
    for pattern in SEGMENTATION_PATTERNS:
        match = re.search(pattern, query_lower)
        if match:
            dimension = match.group(1)
            
            # Map dimension to entity
            for entity_key in ENTITIES.keys():
                if entity_key in dimension:
                    params['entity'] = entity_key
                    break
            
            if 'type' in dimension or 'entry' in dimension:
                params['entity'] = 'entry_type'
            
            return {
                'type': 'segmentation',
                'confidence': 85,
                'params': params
            }
    
    # Try DETAIL patterns
    for pattern in DETAIL_PATTERNS:
        match = re.search(pattern, query_lower)
        if match:
            params['specific_value'] = match.group(1).strip()
            
            return {
                'type': 'detail',
                'confidence': 80,
                'params': params
            }
    
    # Unknown - needs LLM
    return {
        'type': 'unknown',
        'confidence': 0,
        'params': params
    }


def needs_movement_clarification(classification: Dict) -> bool:
    """Check if query needs movement type clarification (minimal adaptive rule)."""
    try:
        params = classification.get('params', {})
        # Ask when ranking suppliers without explicit movement type
        return (
            classification.get('type') == 'ranking' and
            params.get('entity') in ('supplier', 'suppliers') and
            not params.get('movement_type')
        )
    except Exception:
        return False


def get_clarification_for_classification(classification: Dict) -> List[str]:
    """Get specific clarification options based on classification (with minimal adaptive bias)."""
    if not needs_movement_clarification(classification):
        return None
    options = [
        "Top suppliers by ARRIVAL (incoming stock)",
        "Top suppliers by ISSUE (outgoing/used stock)",
        "Top suppliers by REJECTION (returned stock)",
        "Top suppliers across ALL movement types"
    ]
    # Keep a stable option order to avoid user confusion
    return options
