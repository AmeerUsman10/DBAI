"""
Correction Detector for DBAI
Analyzes user corrections and negative feedback to suggest training rules.
"""
import logging
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

class CorrectionDetector:
    """Detects corrections and suggests natural language rules."""
    
    def __init__(self, llm):
        self.llm = llm
    
    def suggest_rule(self, question: str, original_sql: str, feedback_text: str, category: str = "") -> str:
        """
        Suggest a training rule based on feedback or correction.
        
        Args:
            question: Original user question
            original_sql: SQL that was generated
            feedback_text: User's correction or feedback
            category: The issue category selected by user
            
        Returns:
            A suggested natural language training rule
        """
        if not feedback_text and not category:
            return ""
            
        try:
            prompt = f"""
You are an expert at training AI models for text-to-SQL tasks. 
A user provided negative feedback on a generated SQL query. Your task is to draft a single, clear "Training Rule" in natural language that will prevent this error in the future.

Original Question: {question}
AI Generated SQL: {original_sql}
Issue Category: {category}
User's Correction/Feedback: {feedback_text}

Draft a compact natural language rule (1 sentence) that explains how to interpret this request correctly.
Example rules:
- "When users say 'total arrival yarn', return LBS received (not PKR amount)"
- "Greige received = meters of greige fabric from suppliers"
- "'Last month' always refers to the previous full calendar month"

Suggested Rule:"""
            
            suggestion = self.llm.invoke(prompt)
            if isinstance(suggestion, dict):
                suggestion = suggestion.get("text", suggestion.get("content", ""))
            
            return suggestion.strip().strip('"')
            
        except Exception as e:
            logger.error(f"Error suggesting rule: {e}")
            return f"CORRECTION for '{question}': {feedback_text}"

def get_correction_detector(llm):
    """Factory function for CorrectionDetector."""
    return CorrectionDetector(llm)
