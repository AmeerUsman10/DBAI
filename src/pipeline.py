"""
Query Pipeline Module
Modularizes the query processing flow from natural language to formatted results.
"""
import logging
import time
import uuid
import re
from typing import List, Dict, Any, Tuple, Optional

# Core imports
from src.query_classifier import classify_query
from src.clarity import analyze_query_clarity, needs_clarification
from src.llm import make_sql_chain, extract_sql_from_response, validate_sql
from src.database import get_sql_database
from src.query_optimizer import get_cached_result
from src.session_tracker import get_session_tracker
from src.multi_table_intelligence import MultiTableIntelligence
from src.insight_generator import get_insight_generator

logger = logging.getLogger(__name__)

class QueryPipeline:
    """
    Handles the end-to-end processing of a database query.
    """
    
    def __init__(self, llm, provider_name: str, model_name: str):
        self.llm = llm
        self.provider_name = provider_name
        self.model_name = model_name
        self.session_tracker = get_session_tracker()
        self.db = get_sql_database()
        
        try:
            self.mti = MultiTableIntelligence()
        except Exception as e:
            logger.warning(f"Multi-table intelligence unavailable: {e}")
            self.mti = None

    def process_query(self, question: str, persona_overlay: str = "", choice: Optional[int] = None) -> Dict[str, Any]:
        """
        Executes the full pipeline for a question.
        """
        context = {
            "start_time": time.time(),
            "message_id": str(uuid.uuid4())[:8],
            "original_question": question,
            "persona_overlay": persona_overlay,
            "choice": choice,
            "steps": []
        }
        
        try:
            # 0. Conversational Check
            if self._is_conversational(question):
                return self._handle_conversation(question, persona_overlay)

            # 1. Classification & Ambiguity Detection
            intent = self._detect_intent(question)
            context["intent"] = intent
            
            # Check for multi-table ambiguity
            mti_result = self._check_mti(question)
            if mti_result: return mti_result
            
            # Check for general clarity
            clarity_result = self._check_clarity(question)
            if clarity_result: return clarity_result
            
            # 2. Intelligence & Caching
            cached = self._check_cache(question)
            if cached: return cached
            
            # 3. SQL Generation
            sql_query, gen_method, metadata = self._generate_sql(question, persona_overlay, intent)
            
            # 4. Validation & Execution
            result = self._execute_safe(sql_query)
            
            # 5. Response Formatting
            return self._format_response(question, sql_query, result, gen_method, metadata)

        except Exception as e:
            logger.error(f"Pipeline error: {e}", exc_info=True)
            return {"error": str(e), "type": "error"}

    def _detect_intent(self, question: str) -> Dict[str, Any]:
        """Step 1: Classify what the user wants."""
        classification = classify_query(question)
        logger.info(f"Pipeline: Detected intent {classification.get('type')}")
        return classification

    def _check_mti(self, question: str) -> Optional[Dict]:
        """Check for multi-table confusion."""
        if not self.mti: return None
        
        analysis = self.mti.analyze_query(question)
        if analysis.get("needs_clarification"):
            # Return a specialized clarification result
            return {
                "type": "clarification",
                "subtype": "multi_table",
                "options": analysis["target_tables"],
                "message": analysis.get("clarification_message", "Please specify which data:")
            }
        return None

    def _check_clarity(self, question: str) -> Optional[Dict]:
        """Check for general vagueness."""
        score, reason, options = analyze_query_clarity(question)
        if needs_clarification(score):
            return {
                "type": "clarification",
                "subtype": "general",
                "options": options,
                "message": reason
            }
        return None

    def _check_cache(self, question: str) -> Optional[Dict]:
        """Check if we already have the answer."""
        cached = get_cached_result(question, fuzzy_match=True)
        if cached:
            sql, result, meta = cached
            return {
                "type": "success",
                "sql": sql,
                "result": result,
                "method": "cache",
                "metadata": meta
            }
        return None

    def _generate_sql(self, question: str, persona: str, intent: Dict) -> Tuple[str, str, Dict]:
        """Generate the SQL query."""
        # High confidence template match?
        if intent.get('confidence', 0) >= 80:
            from src.query_templates import generate_sql_from_template
            sql = generate_sql_from_template(intent)
            if sql:
                return sql, "template", {}
        
        # LLM Generation
        chain = make_sql_chain(self.llm, self.db)
        response = chain({"question": question, "persona_overlay": persona})
        
        sql = extract_sql_from_response(response.get("result", ""))
        return sql, "llm", {"tokens": response.get("response")}

    def _execute_safe(self, sql: str) -> Any:
        """Validate and run the query."""
        valid, msg = validate_sql(sql)
        if not valid:
            raise ValueError(f"Safety Block: {msg}")
            
        return self.db.run(sql)

    def _is_conversational(self, question: str) -> bool:
        """Detect if user is asking a conversational question."""
        question_lower = question.lower()
        conversational_patterns = [
            r'\b(the above|these results?|that data|this table|previous)\b',
            r'\b(why|how come|explain|what does (this|that|it) mean)\b',
            r'\b(different|same|changed|not matching)\b',
            r'\b(you (said|showed|returned|gave))\b',
            r'\b(earlier|before|last time)\b',
            r'^(why|how|what) (is|are|did|does)',
            r'\btell me (about|why|how)\b'
        ]
        import re
        for pattern in conversational_patterns:
            if re.search(pattern, question_lower):
                return True
        if len(question.split()) < 5:
            data_keywords = ['total', 'sum', 'count', 'show', 'list', 'get', 'find', 'top', 'supplier', 'yarn', 'greige']
            if not any(keyword in question_lower for keyword in data_keywords):
                return True
        return False

    def _handle_conversation(self, question: str, persona: str) -> Dict[str, Any]:
        """Handle conversational queries using the LLM."""
        # Simple implementation for now, can be expanded
        prompt = f"The user is asking a conversational question about data or context.\nQuestion: {question}\nRespond naturally."
        response = self.llm.invoke(prompt)
        content = response.content if hasattr(response, 'content') else str(response)
        return {
            "type": "conversation",
            "text": content,
            "metadata": {"tokens": response}
        }

    def _format_response(self, question: str, sql: str, result: Any, method: str, metadata: Dict) -> Dict:
        """Final output preparation."""
        # This will eventually call specialized formatters for Plotly, etc.
        # Run Insight Generator for high-value results
        insights = ""
        try:
            generator = get_insight_generator(self.llm)
            insights = generator.generate_insights(
                question=question,
                sql=sql,
                rows=result.get('rows', []),
                columns=result.get('columns', [])
            )
        except Exception as e:
            logger.warning(f"Insight generation skipped: {e}")

        return {
            "type": "success",
            "question": question,
            "sql": sql,
            "result": result,
            "method": method,
            "metadata": metadata,
            "rows": result.get('rows', []) if isinstance(result, dict) else [],
            "columns": result.get('columns', []) if isinstance(result, dict) else [],
            "rules_applied": metadata.get("rules_applied", []),
            "insights": insights
        }
