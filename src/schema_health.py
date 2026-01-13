"""
Schema Health Analyzer for DBAI
Analyzes database schema to identify potential issues, missing relationships, and ambiguities.
"""
import logging
from typing import Dict, List, Optional, Any
from sqlalchemy import inspect
from src.database import get_engine

logger = logging.getLogger(__name__)

class SchemaHealthAnalyzer:
    """Analyzes database schema for health and common pitfalls."""
    
    def __init__(self, engine=None):
        self.engine = engine or get_engine()
        
    def analyze(self) -> Dict[str, Any]:
        """
        Run a full schema health analysis.
        
        Returns:
            Dict containing health report, issues, and statistics.
        """
        if not self.engine:
             return {"status": "error", "message": "No database engine available"}
             
        try:
            inspector = inspect(self.engine)
            tables = inspector.get_table_names()
            
            report = {
                "status": "success",
                "table_count": len(tables),
                "issues": [],
                "stats": {
                    "no_pk": 0,
                    "ambiguous_columns": {},
                    "missing_fk": 0
                }
            }
            
            column_locations = {} # col_name -> [table_name]
            
            for table in tables:
                columns = inspector.get_columns(table)
                pk = inspector.get_pk_constraint(table)
                fks = inspector.get_foreign_keys(table)
                
                # Check for Primary Key
                if not pk or not pk.get('constrained_columns'):
                    report["stats"]["no_pk"] += 1
                    report["issues"].append({
                        "severity": "MEDIUM",
                        "table": table,
                        "type": "MISSING_PK",
                        "description": f"Table '{table}' has no primary key. This can lead to performance issues and ambiguity."
                    })
                
                # Check for Foreign Keys
                if not fks:
                    # Heuristic check: look for columns ending in _id or ID that might be missing FKs
                    for col in columns:
                        if col['name'].lower().endswith(('_id', 'id')) and col['name'].lower() != 'id':
                            # Check if another table exists with this name (e.g. customer_id -> Customer)
                            potential_target = col['name'].lower().replace('_id', '').replace('id', '')
                            if any(t.lower() == potential_target for t in tables):
                                report["stats"]["missing_fk"] += 1
                                report["issues"].append({
                                    "severity": "LOW",
                                    "table": table,
                                    "type": "POTENTIAL_MISSING_FK",
                                    "description": f"Column '{col['name']}' in table '{table}' might be a missing foreign key to table '{potential_target}'."
                                })
                
                # Track column locations for ambiguity check
                for col in columns:
                    name = col['name'].lower()
                    if name not in column_locations:
                        column_locations[name] = []
                    column_locations[name].append(table)
            
            # Check for Ambiguous Columns (same name in many tables)
            for name, locs in column_locations.items():
                if len(locs) > 3: # arbitrary threshold for "many"
                    report["stats"]["ambiguous_columns"][name] = len(locs)
                    report["issues"].append({
                        "severity": "LOW",
                        "type": "AMBIGUOUS_COLUMN",
                        "description": f"Column '{name}' exists in {len(locs)} tables. Consider using schema mappings or column aliases to resolve ambiguity."
                    })
            
            return report
            
        except Exception as e:
            logger.error(f"Schema health analysis failed: {e}")
            return {"status": "error", "message": str(e)}

def get_schema_health_report() -> Dict[str, Any]:
    """Helper function to run analysis and return report."""
    analyzer = SchemaHealthAnalyzer()
    return analyzer.analyze()

def format_health_report_markdown(report: Dict[str, Any]) -> str:
    """Format the health report for display in Gradi UI."""
    if report.get("status") == "error":
        return f"❌ **Error:** {report.get('message')}"
        
    output = f"## 🏥 Schema Health Report\n\n"
    output += f"**Tables Analyzed:** {report.get('table_count', 0)}\n\n"
    
    stats = report.get("stats", {})
    output += "### 📊 Statistics\n"
    output += f"- Tables without PK: {stats.get('no_pk', 0)}\n"
    output += f"- Potential missing FKs: {stats.get('missing_fk', 0)}\n"
    output += f"- Highly ambiguous columns: {len(stats.get('ambiguous_columns', {}))}\n\n"
    
    issues = report.get("issues", [])
    if not issues:
        output += "✅ **No major schema issues found! Your database structure looks healthy.**"
    else:
        output += "### ⚠️ Identified Issues\n"
        # Sort by severity
        severity_map = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
        sorted_issues = sorted(issues, key=lambda x: severity_map.get(x['severity'], 3))
        
        for issue in sorted_issues:
            icon = "🔴" if issue['severity'] == "HIGH" else ("🟡" if issue['severity'] == "MEDIUM" else "🔵")
            output += f"- {icon} **[{issue['severity']}]** {issue['description']}\n"
            
    return output
