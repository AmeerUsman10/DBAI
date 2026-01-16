"""
Insight Generator for DBAI
Analyzes query results to provide interesting insights, trends, and outliers using LLM.
"""
import logging
from typing import Dict, List, Optional, Any
import pandas as pd

logger = logging.getLogger(__name__)

class InsightGenerator:
    """Generates natural language insights from data results."""
    
    def __init__(self, llm):
        self.llm = llm
    
    def generate_insights(self, question: str, sql: str, rows: List[Dict], columns: List[str]) -> str:
        """
        Generate insights from the query results.
        
        Args:
            question: Original user question
            sql: SQL query executed
            rows: Result rows
            columns: Column names
            
        Returns:
            String containing natural language insights
        """
        if not rows or not columns or len(rows) < 2:
            return ""
        
        try:
            # Prepare data summary for LLM
            df = pd.DataFrame(rows, columns=columns)
            
            # Basic stats summary
            stats = ""
            numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
            if numeric_cols:
                stats = df[numeric_cols].describe().to_string()
            
            # Head and tail of data
            data_sample = df.head(10).to_string()
            
            prompt = f"""
Analyze the following database query results and provide 2-3 concise, high-value business insights.
Focus on:
1. Significant trends or patterns
2. Outliers or anomalies
3. Aggregated totals or averages that stand out

User Question: {question}
SQL Executed: {sql}

Data Preview:
{data_sample}

Statistical Summary:
{stats}

Provide insights as a bulleted list. Keep each insight short and professional. 
Do not suggest charts or graphs. Focus only on the data patterns.
"""
            
            insights = self.llm.invoke(prompt)
            if isinstance(insights, dict):
                insights = insights.get("text", insights.get("content", ""))
            
            return insights.strip()
            
        except Exception as e:
            logger.error(f"Error generating insights: {e}")
            return ""

def get_insight_generator(llm):
    """Factory function for InsightGenerator."""
    return InsightGenerator(llm)
