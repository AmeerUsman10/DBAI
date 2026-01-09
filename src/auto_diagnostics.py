"""
One-Button Auto-Diagnostics System
Captures everything needed for AI-assisted debugging and improvement.
"""
import json
import re
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


class AutoDiagnostics:
    """Automated diagnostics capture and analysis for AI-assisted improvement."""
    
    def __init__(self):
        self.output_dir = Path(__file__).parent.parent / "logs" / "auto_diagnostics"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
    def sanitize(self, text: str) -> str:
        """Remove sensitive data while preserving error context."""
        if not isinstance(text, str):
            text = str(text)
        
        # Passwords
        text = re.sub(r'PWD=([^;]+)', 'PWD=***', text)
        text = re.sub(r'password["\']?\s*[:=]\s*["\']?([^,"\'\s]+)', 'password=***', text, flags=re.IGNORECASE)
        
        # API keys
        text = re.sub(r'sk-[a-zA-Z0-9]{48}', '***OPENAI_KEY***', text)
        text = re.sub(r'gsk_[a-zA-Z0-9]{52}', '***GROQ_KEY***', text)
        
        # Connection strings
        text = re.sub(r'SERVER=([^;]+)', 'SERVER=***', text)
        text = re.sub(r'server["\']?\s*[:=]\s*["\']?([^,"\'\s;]+)', 'server=***', text, flags=re.IGNORECASE)
        
        return text
    
    def capture_recent_errors(self) -> List[Dict]:
        """Extract recent errors from audit log."""
        errors = []
        audit_file = Path(__file__).parent.parent / "logs" / "audit_events.json"
        
        if audit_file.exists():
            try:
                events = json.loads(audit_file.read_text(encoding='utf-8'))
                for event in events[-50:]:  # Last 50 events
                    if event.get("status") == "error" or event.get("success") is False:
                        errors.append({
                            "time": event.get("timestamp", "unknown"),
                            "query": self.sanitize(event.get("natural_language_query", ""))[:200],
                            "error": self.sanitize(event.get("error_message", ""))[:300],
                            "sql": self.sanitize(event.get("generated_sql", ""))[:500]
                        })
            except Exception as e:
                logger.error(f"Failed to read audit log: {e}")
                errors.append({"error": f"Failed to read audit log: {str(e)}"})
        
        return errors
    
    def capture_feedback_issues(self) -> List[Dict]:
        """Extract negative feedback patterns."""
        issues = []
        feedback_file = Path(__file__).parent.parent / "logs" / "feedback" / "feedback_data.json"
        
        if feedback_file.exists():
            try:
                data = json.loads(feedback_file.read_text(encoding='utf-8'))
                events = data.get("feedback_events", [])
                
                for fb in events[-20:]:  # Last 20 feedback items
                    if fb.get("feedback_type") == "thumbs_down":
                        issues.append({
                            "time": fb.get("timestamp", "unknown"),
                            "query": self.sanitize(fb.get("question", ""))[:200],
                            "issue": self.sanitize(fb.get("feedback_text", ""))[:300]
                        })
            except Exception as e:
                logger.error(f"Failed to read feedback: {e}")
        
        return issues
    
    def check_system_health(self) -> Dict[str, Any]:
        """Run system health checks."""
        health = {
            "database": "unknown",
            "config": "unknown",
            "training_rules": 0,
            "cache_files": 0
        }
        
        # Database
        try:
            from src.database import get_engine
            engine = get_engine()
            if engine:
                health["database"] = "connected"
            else:
                health["database"] = "not connected"
        except Exception as e:
            health["database"] = f"error: {self.sanitize(str(e)[:100])}"
        
        # Config
        config_file = Path(__file__).parent.parent / "config.yaml"
        if config_file.exists():
            health["config"] = "present"
        else:
            health["config"] = "missing"
        
        # Training rules
        try:
            from src.quick_training import load_training_rules
            rules_data = load_training_rules()
            health["training_rules"] = len(rules_data.get("rules", []))
        except Exception as e:
            logger.error(f"Failed to load training rules: {e}")
        
        # Cache
        cache_dir = Path(__file__).parent.parent / "cache"
        if cache_dir.exists():
            health["cache_files"] = len(list(cache_dir.glob("*.json")))
        
        return health
    
    def analyze_patterns(self, errors: List[Dict]) -> Dict[str, Any]:
        """Analyze error patterns and generate insights."""
        patterns = {
            "common_errors": {},
            "recommendations": []
        }
        
        # Count error types
        for err in errors:
            error_msg = err.get("error", "")
            
            if "ModuleNotFoundError" in error_msg or "ImportError" in error_msg:
                patterns["common_errors"]["missing_module"] = patterns["common_errors"].get("missing_module", 0) + 1
            elif "connection" in error_msg.lower() or "connect" in error_msg.lower():
                patterns["common_errors"]["connection"] = patterns["common_errors"].get("connection", 0) + 1
            elif "syntax" in error_msg.lower() or "sql" in error_msg.lower():
                patterns["common_errors"]["sql_generation"] = patterns["common_errors"].get("sql_generation", 0) + 1
            elif "timeout" in error_msg.lower():
                patterns["common_errors"]["timeout"] = patterns["common_errors"].get("timeout", 0) + 1
            elif "api" in error_msg.lower() or "key" in error_msg.lower():
                patterns["common_errors"]["api_error"] = patterns["common_errors"].get("api_error", 0) + 1
            else:
                patterns["common_errors"]["other"] = patterns["common_errors"].get("other", 0) + 1
        
        # Generate recommendations
        if patterns["common_errors"].get("missing_module", 0) > 0:
            patterns["recommendations"].append({
                "priority": "HIGH",
                "issue": "Missing Python dependencies",
                "fix": "Run: pip install -r requirements.txt"
            })
        
        if patterns["common_errors"].get("connection", 0) > 2:
            patterns["recommendations"].append({
                "priority": "HIGH",
                "issue": "Repeated database connection failures",
                "fix": "Check database server status and credentials in Settings tab"
            })
        
        if patterns["common_errors"].get("api_error", 0) > 0:
            patterns["recommendations"].append({
                "priority": "HIGH",
                "issue": "LLM API errors",
                "fix": "Verify API keys are set in .env file or environment variables"
            })
        
        if patterns["common_errors"].get("sql_generation", 0) > 3:
            patterns["recommendations"].append({
                "priority": "MEDIUM",
                "issue": "LLM generating invalid SQL repeatedly",
                "fix": "Add training rules in Train tab for common query patterns"
            })
        
        if patterns["common_errors"].get("timeout", 0) > 1:
            patterns["recommendations"].append({
                "priority": "MEDIUM",
                "issue": "Query timeouts",
                "fix": "Optimize database queries or increase timeout settings"
            })
        
        return patterns
    
    def generate_ai_context(self, errors: List[Dict], feedback: List[Dict], 
                           health: Dict, patterns: Dict) -> str:
        """Generate context document for AI review."""
        lines = [
            "# Auto-Diagnostics Report",
            f"Generated: {datetime.now().isoformat()}",
            "",
            "## System Health",
            f"- Database: {health['database']}",
            f"- Config: {health['config']}",
            f"- Training Rules: {health['training_rules']}",
            f"- Cache Files: {health['cache_files']}",
            "",
            "## Error Summary",
            f"- Total errors captured: {len(errors)}",
            f"- Negative feedback: {len(feedback)}",
            ""
        ]
        
        if patterns["common_errors"]:
            lines.append("### Error Breakdown")
            for err_type, count in sorted(patterns["common_errors"].items(), key=lambda x: x[1], reverse=True):
                lines.append(f"- {err_type}: {count}")
            lines.append("")
        
        if patterns["recommendations"]:
            lines.append("## Recommended Actions")
            for rec in patterns["recommendations"]:
                lines.append(f"\n**[{rec['priority']}] {rec['issue']}**")
                lines.append(f"Fix: {rec['fix']}")
            lines.append("")
        
        if errors:
            lines.append("## Recent Errors (Last 10)")
            for i, err in enumerate(errors[-10:], 1):
                lines.append(f"\n### Error {i}")
                lines.append(f"**Time:** {err.get('time', 'N/A')}")
                lines.append(f"**Query:** {err.get('query', 'N/A')}")
                lines.append(f"**Error:** {err.get('error', 'N/A')}")
                if err.get('sql'):
                    lines.append(f"**Generated SQL:**\n```sql\n{err.get('sql')}\n```")
        
        if feedback:
            lines.append("\n## User Feedback Issues (Last 5)")
            for i, fb in enumerate(feedback[-5:], 1):
                lines.append(f"\n{i}. **Query:** {fb.get('query', 'N/A')}")
                lines.append(f"   **Issue:** {fb.get('issue', 'N/A')}")
        
        lines.append("\n---")
        lines.append("*All sensitive data (passwords, API keys, servers) has been sanitized.*")
        
        return "\n".join(lines)
    
    def run_full_capture(self) -> Dict[str, Any]:
        """Execute complete diagnostic capture and analysis."""
        logger.info("Starting auto-diagnostics...")
        
        # 1. Capture data
        errors = self.capture_recent_errors()
        feedback = self.capture_feedback_issues()
        health = self.check_system_health()
        
        # 2. Analyze
        patterns = self.analyze_patterns(errors)
        
        # 3. Generate AI context
        ai_context = self.generate_ai_context(errors, feedback, health, patterns)
        
        # 4. Save outputs
        report_file = self.output_dir / f"ai_review_{self.timestamp}.md"
        report_file.write_text(ai_context, encoding='utf-8')
        
        # 5. Create full bundle
        bundle_path = "Bundle creation skipped (use full export if needed)"
        try:
            from src.diagnostics import collect_full_session_bundle
            bundle_path = collect_full_session_bundle(include_sensitive=False)
        except Exception as e:
            logger.error(f"Bundle creation failed: {e}")
            bundle_path = f"Bundle creation failed: {str(e)[:100]}"
        
        # 6. Save structured data
        structured_file = self.output_dir / f"structured_{self.timestamp}.json"
        structured_data = {
            "timestamp": self.timestamp,
            "errors": errors,
            "feedback": feedback,
            "health": health,
            "patterns": patterns,
            "bundle_path": str(bundle_path) if isinstance(bundle_path, Path) else bundle_path
        }
        structured_file.write_text(json.dumps(structured_data, indent=2), encoding='utf-8')
        
        logger.info(f"Auto-diagnostics complete: {report_file}")
        
        # Create summary for UI
        summary = {
            "status": "success",
            "timestamp": self.timestamp,
            "errors_found": len(errors),
            "feedback_issues": len(feedback),
            "health_status": health["database"],
            "report_path": str(report_file),
            "structured_path": str(structured_file),
            "recommendations_count": len(patterns["recommendations"])
        }
        
        return summary


def run_auto_diagnostics() -> str:
    """Main entry point for UI button."""
    try:
        auto_diag = AutoDiagnostics()
        result = auto_diag.run_full_capture()
        
        # Format for UI display
        msg = f"""## 🎯 Auto-Diagnostics Complete

**Status:** ✅ {result['status']}  
**Timestamp:** {result['timestamp']}

### 📊 Captured:
- ❌ **Errors:** {result['errors_found']}
- 💬 **Feedback Issues:** {result['feedback_issues']}
- 🗄️ **Database:** {result['health_status']}
- 💡 **Recommendations:** {result['recommendations_count']}

### 📁 Files Generated:
- 📄 AI Review: `{result['report_path']}`
- 📊 Structured Data: `{result['structured_path']}`

---

✅ **All done!** Just say **"testing done"** and I'll review the diagnostics to help improve your chatbot.

*All sensitive data has been automatically sanitized.*
"""
        return msg
    
    except Exception as e:
        logger.error(f"Auto-diagnostics failed: {e}", exc_info=True)
        return f"❌ **Auto-diagnostics failed:** {str(e)}\n\nPlease check the logs for details."
