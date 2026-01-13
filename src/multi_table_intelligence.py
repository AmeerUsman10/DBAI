"""
Multi-Table Intelligence Module for DBAI
Handles domain-specific logic for Greige/Yarn parallel table structures
"""

import re
import yaml
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

logger = logging.getLogger(__name__)


class MultiTableIntelligence:
    """
    Intelligent query router and clarification system for multi-table domains.
    Specifically designed for Greige/Yarn parallel table structures.
    """

    def __init__(self, config_path: str = "domain_config.yaml"):
        self.config_path = Path(config_path)
        self.config = self._load_config()
        self.entities = self.config.get("entities", {})
        self.ambiguous_patterns = self.config.get("ambiguous_patterns", [])
        self.auto_combine_patterns = self.config.get("auto_combine_patterns", [])
        self.table_routing = self.config.get("table_routing", {})
        self.result_labels = self.config.get("result_labels", {})
        self.clarification_handling = self.config.get("clarification_handling", {})

        logger.info("MultiTableIntelligence initialized")

    def _load_config(self) -> Dict:
        """Load domain configuration from YAML."""
        try:
            if self.config_path.exists():
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    return yaml.safe_load(f) or {}
            else:
                logger.warning(f"Config file not found: {self.config_path}")
                return {}
        except Exception as e:
            logger.error(f"Failed to load domain config: {e}")
            return {}

    def analyze_query(self, user_query: str) -> Dict[str, Any]:
        """
        Analyze user query to determine:
        - Which table(s) to query
        - Whether clarification is needed
        - What labels to add to results

        Returns:
            {
                'needs_clarification': bool,
                'clarification_message': str or None,
                'target_tables': List[str],
                'target_entity': str or None,
                'result_label': str,
                'auto_combine': bool
            }
        """
        analysis = {
            'needs_clarification': False,
            'clarification_message': None,
            'target_tables': [],
            'target_entity': None,
            'result_label': '',
            'auto_combine': False,
            'confidence': 0.0
        }

        # Check for auto-combine patterns first
        for pattern_config in self.auto_combine_patterns:
            if re.search(pattern_config['pattern'], user_query):
                analysis['auto_combine'] = True
                analysis['target_tables'] = ['GreigeData', 'YarnData']
                analysis['result_label'] = self.result_labels.get('multi_table', '')
                analysis['confidence'] = 1.0
                return analysis

        # Check for table-specific keywords
        greige_match = self._check_table_keywords(user_query, 'GreigeData')
        yarn_match = self._check_table_keywords(user_query, 'YarnData')

        # Clear single table match
        if greige_match and not yarn_match:
            analysis['target_tables'] = ['GreigeData']
            analysis['target_entity'] = 'greige'
            analysis['result_label'] = self.result_labels['single_table']['greige']
            analysis['confidence'] = 0.9
            return analysis

        if yarn_match and not greige_match:
            analysis['target_tables'] = ['YarnData']
            analysis['target_entity'] = 'yarn'
            analysis['result_label'] = self.result_labels['single_table']['yarn']
            analysis['confidence'] = 0.9
            return analysis

        # Both matched - user wants combined data
        if greige_match and yarn_match:
            analysis['auto_combine'] = True
            analysis['target_tables'] = ['GreigeData', 'YarnData']
            analysis['result_label'] = self.result_labels.get('multi_table', '')
            analysis['confidence'] = 0.8
            return analysis

        # No clear match - check ambiguous patterns
        for pattern_config in self.ambiguous_patterns:
            if re.search(pattern_config['pattern'], user_query):
                analysis['needs_clarification'] = True
                analysis['clarification_message'] = pattern_config['clarification']
                analysis['confidence'] = 0.3
                return analysis

        # Default to greige if no pattern matches
        analysis['target_tables'] = ['GreigeData']
        analysis['target_entity'] = 'greige'
        analysis['result_label'] = self.result_labels['single_table']['greige']
        analysis['confidence'] = 0.5

        return analysis

    def _check_table_keywords(self, query: str, table_name: str) -> bool:
        """Check if query contains keywords specific to a table."""
        routing = self.table_routing.get(table_name, {})
        must_contain = routing.get('must_contain', [])
        metrics_keywords = routing.get('metrics_keywords', [])

        # Check primary keywords
        for pattern in must_contain:
            if re.search(pattern, query):
                return True

        # Check metric keywords (weaker signal)
        metric_matches = sum(1 for kw in metrics_keywords if kw.lower() in query.lower())
        return metric_matches >= 2  # Need at least 2 metric keywords

    def parse_clarification_response(self, user_response: str) -> Optional[str]:
        """
        Parse user's response to clarification question.

        Returns:
            'greige', 'yarn', 'both', or None if unclear
        """
        response_lower = user_response.strip().lower()

        # Extract numeric value from responses like "1", "1.", "option 1", etc.
        import re
        numeric_match = re.search(r'\b([123])\b', response_lower)
        if numeric_match:
            num = numeric_match.group(1)
            if num == '1':
                return 'greige'
            elif num == '2':
                return 'yarn'
            elif num == '3':
                return 'both'

        # Check text responses
        text_map = self.clarification_handling.get('text_responses', {})
        for key, value in text_map.items():
            if key in response_lower:
                if value == 'option_1':
                    return 'greige'
                elif value == 'option_2':
                    return 'yarn'
                elif value == 'option_3':
                    return 'both'

        # Default fallback
        default = self.clarification_handling.get('default_if_unclear', 'option_3')
        if default == 'option_3':
            return 'both'
        elif default == 'option_1':
            return 'greige'
        else:
            return 'yarn'

    def get_enhanced_prompt_context(self, target_entity: Optional[str] = None) -> str:
        """
        Get additional context to add to LLM prompt based on target entity.

        Args:
            target_entity: 'greige', 'yarn', or None for both

        Returns:
            Enhanced context string to prepend to prompt
        """
        base_context = self.config.get('prompt_additions', {}).get('context_reminder', '')
        format_reminder = self.config.get('prompt_additions', {}).get('result_format_reminder', '')

        entity_context = ""
        if target_entity and target_entity in self.entities:
            entity_info = self.entities[target_entity]
            entity_context = f"\n**Target Table:** {entity_info['table']}\n"
            entity_context += f"**Description:** {entity_info['description']}\n"
            entity_context += f"**Key Metrics:** {', '.join(entity_info.get('metrics', {}).keys())}\n"

        return f"{base_context}\n{entity_context}\n{format_reminder}"

    def get_result_label(self, entity: str) -> str:
        """Get the appropriate result label for an entity."""
        if entity == 'both':
            return self.result_labels.get('multi_table', '')

        return self.result_labels.get('single_table', {}).get(entity, '')

    def generate_combined_query_template(self, base_query: str, query_type: str = "summary") -> str:
        """
        Generate SQL template for combined greige + yarn queries.

        Args:
            base_query: The original user query
            query_type: Type of query ('summary', 'supplier', 'arrival', etc.)

        Returns:
            SQL template string with UNION ALL for both tables
        """
        templates = self.config.get('training_templates', {})

        if query_type == "summary":
            return templates.get('combined_summary', {}).get('sql_template', '')

        # For other types, return empty (will use LLM)
        return ""

    def should_add_source_column(self, analysis: Dict[str, Any]) -> bool:
        """Determine if results should include a 'Source' column."""
        return analysis.get('auto_combine', False) or len(analysis.get('target_tables', [])) > 1


def get_multi_table_intelligence() -> MultiTableIntelligence:
    """Get singleton instance of MultiTableIntelligence."""
    if not hasattr(get_multi_table_intelligence, '_instance'):
        get_multi_table_intelligence._instance = MultiTableIntelligence()
    return get_multi_table_intelligence._instance


# Convenience functions for easy integration

def analyze_for_clarification(user_query: str) -> Tuple[bool, Optional[str]]:
    """
    Quick check if query needs clarification.

    Returns:
        (needs_clarification, clarification_message)
    """
    mti = get_multi_table_intelligence()
    analysis = mti.analyze_query(user_query)
    return analysis['needs_clarification'], analysis.get('clarification_message')


def get_target_tables(user_query: str, clarification_response: Optional[str] = None) -> List[str]:
    """
    Get list of tables to query based on user input.

    Args:
        user_query: Original user query
        clarification_response: User's response if clarification was asked

    Returns:
        List of table names to query
    """
    mti = get_multi_table_intelligence()

    if clarification_response:
        entity = mti.parse_clarification_response(clarification_response)
        if entity == 'greige':
            return ['GreigeData']
        elif entity == 'yarn':
            return ['YarnData']
        else:  # 'both'
            return ['GreigeData', 'YarnData']

    analysis = mti.analyze_query(user_query)
    return analysis.get('target_tables', ['GreigeData'])


def get_enhanced_context_for_llm(user_query: str, target_entity: Optional[str] = None) -> str:
    """
    Get enhanced context to add to LLM prompt.

    Args:
        user_query: User's question
        target_entity: 'greige', 'yarn', or None

    Returns:
        Context string to prepend to LLM prompt
    """
    mti = get_multi_table_intelligence()
    return mti.get_enhanced_prompt_context(target_entity)
