"""
Session Tracking and Observability
Captures complete application intelligence for analysis and debugging.
"""
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
import time

logger = logging.getLogger(__name__)

class SessionTracker:
    """
    Tracks complete session activity with configurable detail levels.
    
    Tier 1 (Always On): Essential metrics, errors, performance
    Tier 2 (Developer Mode): Full LLM interactions, reasoning chains
    Tier 3 (On-Demand): Complete package for Copilot analysis
    """
    
    def __init__(self):
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.started_at = datetime.now().isoformat()
        self.project_root = Path(__file__).parent.parent
        self.session_dir = self.project_root / "logs" / "sessions"
        self.session_dir.mkdir(parents=True, exist_ok=True)
        
        # Tracking state
        self.queries: List[Dict] = []
        self.errors: List[Dict] = []
        self.training_events: List[Dict] = []
        # Memoized user clarifications within this session
        self._clarifications: Dict[str, str] = {}
        
        # Configuration (loaded from settings)
        self.config = self.load_config()
        
        # Current state
        self.state = {
            "session_id": self.session_id,
            "started_at": self.started_at,
            "total_queries": 0,
            "total_errors": 0,
            "total_successes": 0,
            "current_state": {},
            "last_query": None,
            "session_timeline": [],
            # Expose memoized clarifications for diagnostics export
            "clarifications": self._clarifications
        }
        
        logger.info(f"Session tracker initialized: {self.session_id}")
    
    def load_config(self) -> Dict:
        """Load observability configuration."""
        config_file = self.project_root / "logs" / "observability_config.json"
        
        if config_file.exists():
            try:
                with open(config_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading config: {e}")
        
        # Default configuration
        return {
            "tier1_enabled": True,  # Always on - essential metrics
            "tier2_enabled": False,  # Developer mode - detailed debugging
            "capture_llm_prompts": False,
            "capture_sample_data": False,
            "capture_reasoning_chain": True,
            "max_queries_in_memory": 50,
            "auto_save_interval": 10  # Save after every 10 queries
        }
    
    def save_config(self, config: Dict):
        """Save observability configuration."""
        config_file = self.project_root / "logs" / "observability_config.json"
        try:
            with open(config_file, 'w') as f:
                json.dump(config, f, indent=2)
            self.config = config
            logger.info("Observability config updated")
        except Exception as e:
            logger.error(f"Error saving config: {e}")
    
    def track_query(
        self,
        user_question: str,
        clarity_analysis: Optional[Dict] = None,
        llm_interaction: Optional[Dict] = None,
        execution: Optional[Dict] = None,
        response: Optional[Dict] = None,
        performance: Optional[Dict] = None,
        error: Optional[str] = None
    ):
        """
        Track a complete query lifecycle.
        
        Args:
            user_question: The user's question
            clarity_analysis: Vagueness detection results
            llm_interaction: LLM prompt/response details
            execution: SQL execution details
            response: Response formatting details
            performance: Timing metrics
            error: Error message if query failed
        """
        timestamp = datetime.now().isoformat()
        
        query_data = {
            "timestamp": timestamp,
            "user_question": user_question,
            "success": error is None
        }
        
        # Tier 1: Always capture
        if self.config.get("tier1_enabled", True):
            query_data.update({
                "execution_time_ms": performance.get("total_time_ms") if performance else None,
                "success": error is None,
                "error": error if error else None
            })
            
            if execution:
                query_data["rows_returned"] = execution.get("rows_returned")
                query_data["execution_time_ms"] = execution.get("execution_time_ms")
        
        # Tier 2: Developer mode - detailed debugging
        if self.config.get("tier2_enabled", False):
            if clarity_analysis:
                query_data["clarity_analysis"] = clarity_analysis
            
            if self.config.get("capture_llm_prompts", False) and llm_interaction:
                query_data["llm_interaction"] = llm_interaction
            
            # REMOVED - Reasoning chain not implemented yet (placeholder feature)
            # if self.config.get("capture_reasoning_chain", True) and llm_interaction:
            #     query_data["reasoning"] = {
            #         "learnings_found": llm_interaction.get("learnings_found"),
            #         "training_rules_applied": llm_interaction.get("training_rules_applied"),
            #         "corrections_applied": llm_interaction.get("corrections_applied")
            #     }
            
            if execution:
                query_data["execution"] = {
                    "sql": execution.get("sql"),
                    "success": execution.get("success"),
                    "rows_returned": execution.get("rows_returned"),
                    "execution_time_ms": execution.get("execution_time_ms")
                }
                
                if self.config.get("capture_sample_data", False):
                    query_data["execution"]["sample_data"] = execution.get("sample_data", [])[:3]
            
            if response:
                query_data["response"] = response
            
            if performance:
                query_data["performance"] = performance
        
        # Track query
        self.queries.append(query_data)
        self.state["total_queries"] += 1
        
        if error:
            self.state["total_errors"] += 1
            self.errors.append({"timestamp": timestamp, "query": user_question, "error": error})
        else:
            self.state["total_successes"] += 1
        
        self.state["last_query"] = query_data
        self.state["session_timeline"].append({
            "type": "query",
            "timestamp": timestamp,
            "question": user_question[:100],  # Truncate for timeline
            "success": error is None
        })
        
        # Auto-save
        if self.state["total_queries"] % self.config.get("auto_save_interval", 10) == 0:
            self.save_session()
        
        logger.info(f"Tracked query: '{user_question[:50]}...' - Success: {error is None}")
    
    def track_training_event(self, event_type: str, details: Dict):
        """Track training-related events (adding rules, column training, etc.)"""
        timestamp = datetime.now().isoformat()
        
        event = {
            "timestamp": timestamp,
            "type": event_type,
            "details": details
        }
        
        self.training_events.append(event)
        self.state["session_timeline"].append({
            "type": "training",
            "timestamp": timestamp,
            "event_type": event_type
        })
        
        logger.info(f"Tracked training event: {event_type}")
    
    def track_error(self, error_type: str, error_message: str, context: Optional[Dict] = None):
        """Track errors that occur outside of queries."""
        timestamp = datetime.now().isoformat()
        
        error_data = {
            "timestamp": timestamp,
            "type": error_type,
            "message": error_message,
            "context": context or {}
        }
        
        self.errors.append(error_data)
        self.state["total_errors"] += 1
        self.state["session_timeline"].append({
            "type": "error",
            "timestamp": timestamp,
            "error_type": error_type
        })
        
        logger.error(f"Tracked error: {error_type} - {error_message}")
    
    def update_app_state(self, state: Dict):
        """Update current application state (provider, model, db connection, etc.)"""
        self.state["current_state"] = state

    def remember_clarification(self, original_query: str, selected_option: str):
        """Memoize a clarification selection for the given original query in this session."""
        try:
            key = (original_query or "").strip().lower()
            if key:
                self._clarifications[key] = selected_option
                # Keep state in sync for exports
                self.state["clarifications"] = self._clarifications
                logger.info(f"Memoized clarification for '{original_query[:50]}...': '{selected_option}'")
        except Exception as e:
            logger.warning(f"Failed to memoize clarification: {e}")

    def get_clarification(self, original_query: str) -> Optional[str]:
        """Retrieve a previously selected clarification for a query if available."""
        try:
            key = (original_query or "").strip().lower()
            return self._clarifications.get(key)
        except Exception:
            return None
    
    def save_session(self):
        """Save current session state to file."""
        session_file = self.session_dir / f"session_{self.session_id}.json"
        
        try:
            with open(session_file, 'w') as f:
                json.dump(self.state, f, indent=2)
            
            # Also save to latest_session.json for easy access
            latest_file = self.project_root / "logs" / "latest_session.json"
            with open(latest_file, 'w') as f:
                json.dump(self.state, f, indent=2)
            
            logger.debug(f"Session saved: {session_file}")
        except Exception as e:
            logger.error(f"Error saving session: {e}")
    
    def get_session_summary(self) -> Dict:
        """Get summary statistics for current session."""
        return {
            "session_id": self.session_id,
            "duration_minutes": self._get_session_duration(),
            "total_queries": self.state["total_queries"],
            "successful_queries": self.state["total_successes"],
            "failed_queries": self.state["total_errors"],
            "success_rate": (self.state["total_successes"] / max(self.state["total_queries"], 1)) * 100,
            "avg_response_time": self._calculate_avg_response_time(),
            "training_events": len(self.training_events),
            "errors": len(self.errors)
        }
    
    def _get_session_duration(self) -> float:
        """Calculate session duration in minutes."""
        start = datetime.fromisoformat(self.started_at)
        now = datetime.now()
        return (now - start).total_seconds() / 60
    
    def _calculate_avg_response_time(self) -> Optional[float]:
        """Calculate average query response time."""
        times = []
        for query in self.queries:
            if query.get("execution_time_ms"):
                times.append(query["execution_time_ms"])
        
        return sum(times) / len(times) if times else None
    
    def export_for_copilot(self) -> str:
        """
        Export complete session package for Copilot analysis.
        Returns path to exported file.
        """
        export_file = self.session_dir / f"copilot_report_{self.session_id}.json"
        
        report = {
            "session_summary": self.get_session_summary(),
            "configuration": self.config,
            "full_state": self.state,
            "all_queries": self.queries,
            "all_errors": self.errors,
            "training_events": self.training_events,
            "recommendations": self._generate_recommendations()
        }
        
        try:
            with open(export_file, 'w') as f:
                json.dump(report, f, indent=2)
            
            logger.info(f"Copilot report exported: {export_file}")
            return str(export_file)
        except Exception as e:
            logger.error(f"Error exporting report: {e}")
            return None
    
    def _generate_recommendations(self) -> List[str]:
        """Generate recommendations based on session data."""
        recommendations = []
        
        summary = self.get_session_summary()
        
        if summary["success_rate"] < 70:
            recommendations.append("⚠️ Low success rate - consider reviewing common error patterns")
        
        if summary["avg_response_time"] and summary["avg_response_time"] > 3000:
            recommendations.append("🐌 Slow response times - check database query optimization")
        
        if len(self.errors) > 5:
            recommendations.append("🔴 Multiple errors detected - review error patterns")
        
        if summary["total_queries"] > 0 and len(self.training_events) == 0:
            recommendations.append("💡 No training events - consider adding training rules for better accuracy")
        
        return recommendations


# Global session tracker instance
_session_tracker: Optional[SessionTracker] = None


def get_session_tracker() -> SessionTracker:
    """Get or create the global session tracker instance."""
    global _session_tracker
    if _session_tracker is None:
        _session_tracker = SessionTracker()
    return _session_tracker


def reset_session_tracker():
    """Reset the session tracker (e.g., on app restart)."""
    global _session_tracker
    if _session_tracker:
        _session_tracker.save_session()
    _session_tracker = SessionTracker()


def get_observability_config() -> Dict:
    """Get current observability configuration."""
    tracker = get_session_tracker()
    return tracker.config
