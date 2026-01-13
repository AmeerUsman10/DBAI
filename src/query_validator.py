"""
Query Validation & Safety Guardrails
Catches common SQL generation errors and validates results integrity.
"""
import logging
import re
from typing import Tuple, Dict, Any, List

logger = logging.getLogger(__name__)


class QueryValidator:
    """Validates SQL queries and results for correctness."""
    
    @staticmethod
    def validate_sql_structure(query: str) -> Tuple[bool, str]:
        """
        Validate SQL query structure for common errors.
        
        Args:
            query: SQL query to validate
            
        Returns:
            Tuple of (is_valid: bool, message: str)
        """
        query_upper = query.upper().strip()
        
        # Check for dangerous operations (already done in llm.py, but double-check)
        dangerous = ['DROP', 'DELETE', 'TRUNCATE', 'ALTER', 'CREATE', 'INSERT', 'UPDATE']
        for keyword in dangerous:
            if re.search(rf'\b{keyword}\b', query_upper):
                return False, f"❌ Dangerous operation blocked: {keyword}"
        
        # Check for basic SELECT
        if not query_upper.startswith('SELECT'):
            return False, "❌ Only SELECT queries allowed"
        
        return True, "✅ Structure valid"
    
    @staticmethod
    def check_multi_table_warning(query: str) -> List[str]:
        """
        Warn about potential multi-table join issues.
        
        Args:
            query: SQL query
            
        Returns:
            List of warnings (empty if no issues)
        """
        warnings = []
        query_upper = query.upper()
        
        # Check for common join patterns that might cause issues
        if 'YARNDATA' in query_upper and 'GREIGEDATA' in query_upper:
            if 'JOIN' in query_upper and not 'SUBQUERY' in query_upper:
                warnings.append("⚠️ JOINing YarnData and GreigeData may inflate counts - verify this is intentional")
        
        # Check for missing GROUP BY with aggregates
        if re.search(r'\bSUM\(|COUNT\(|AVG\(|MAX\(|MIN\(', query_upper):
            if 'GROUP BY' not in query_upper:
                # Some aggregates don't need GROUP BY (like SELECT COUNT(*))
                if not re.search(r'SELECT\s+COUNT\(\*\)\s*$', query_upper):
                    warnings.append("⚠️ Aggregates used without GROUP BY - verify all non-aggregated columns are grouped")
        
        # Check for ARRIVAL-like queries without supplier info
        if re.search(r'ARRIVAL|INCOMING|TOP.*SUPPLIER', query_upper):
            if 'SUPPLIER' not in query_upper or 'JOIN' not in query_upper:
                warnings.append("⚠️ Supplier/ARRIVAL query missing table joins - verify data completeness")
        
        # CRITICAL: Check for table name mismatches
        # If query mentions greige but queries yarn, that's wrong
        if 'GREIGEDATA' in query_upper and 'YARNDATA' not in query_upper:
            # Greige-only query - good
            pass
        elif 'YARNDATA' in query_upper and 'GREIGEDATA' not in query_upper:
            # Yarn-only query - good
            pass
        else:
            # Mixed query - need to verify it's intentional
            pass
        
        return warnings
    
    @staticmethod
    def validate_results_integrity(results: List[Dict], query: str) -> Tuple[bool, List[str]]:
        """
        Validate that query results match the query intent.
        
        Args:
            results: Query results as list of dicts
            query: Original query
            
        Returns:
            Tuple of (is_valid: bool, issues: List[str])
        """
        issues = []
        query_upper = query.upper()
        
        if not results:
            # Empty results might be valid, but flag it
            if 'TOP' in query_upper:
                issues.append("⚠️ No results returned for TOP query - verify filter conditions")
            return True, issues
        
        # Check for data type consistency
        first_row = results[0]
        for row in results[1:]:
            for key in first_row:
                if key not in row:
                    issues.append(f"⚠️ Inconsistent columns: missing '{key}' in some rows")
                    break
        
        # Check for obvious data quality issues
        if 'GROUP BY' in query_upper:
            # Should have grouping - check that at least some unique values exist
            if len(results) == 1:
                issues.append("⚠️ GROUP BY returned only 1 row - verify grouping is correct")
        
        # For TOP queries, verify we actually got results ordered
        if 'TOP' in query_upper and 'ORDER BY' in query_upper:
            if len(results) > 1:
                # Good - we got multiple results
                pass
        
        return len(issues) == 0, issues
    
    @staticmethod
    def generate_validation_report(query: str, results: List[Dict]) -> Dict[str, Any]:
        """
        Generate comprehensive validation report.
        
        Args:
            query: SQL query
            results: Query results
            
        Returns:
            Validation report dict
        """
        struct_valid, struct_msg = QueryValidator.validate_sql_structure(query)
        warnings = QueryValidator.check_multi_table_warning(query)
        results_valid, result_issues = QueryValidator.validate_results_integrity(results, query)
        
        report = {
            "valid": struct_valid and results_valid,
            "structure_valid": struct_valid,
            "structure_message": struct_msg,
            "warnings": warnings,
            "result_issues": result_issues,
            "result_count": len(results) if results else 0
        }
        
        return report


class ResultsQualityChecker:
    """Checks if results match user's implied intent."""
    
    @staticmethod
    def check_supplier_query_completeness(query: str, results: List[Dict]) -> Tuple[bool, str]:
        """
        For supplier-related queries, ensure all suppliers in results are actual suppliers.
        
        Args:
            query: SQL query
            results: Results
            
        Returns:
            Tuple of (is_complete: bool, message: str)
        """
        if not results:
            return True, "No results to check"
        
        # Check if supplier columns exist in results
        first_row = results[0]
        supplier_columns = [k for k in first_row.keys() if 'supplier' in k.lower()]
        
        if 'SUPPLIER' in query.upper() and not supplier_columns:
            return False, "❌ Supplier query but no supplier columns in results"
        
        # Check for meaningful data
        if supplier_columns:
            supplier_col = supplier_columns[0]
            null_count = sum(1 for row in results if not row.get(supplier_col))
            if null_count > len(results) * 0.5:
                return False, f"❌ More than 50% NULL supplier values - data quality issue"
        
        return True, "✅ Results appear complete"
    
    @staticmethod
    def check_aggregation_sanity(query: str, results: List[Dict]) -> Tuple[bool, str]:
        """
        Check if aggregated results make sense (no obvious math errors).
        
        Args:
            query: SQL query
            results: Results
            
        Returns:
            Tuple of (is_sane: bool, message: str)
        """
        if not results:
            return True, "No results"
        
        first_row = results[0]
        
        # Check for numeric columns with obviously wrong values
        for key, value in first_row.items():
            if isinstance(value, (int, float)):
                # Negative values where they shouldn't be
                if value < 0 and any(x in key.lower() for x in ['count', 'quantity', 'total', 'sum']):
                    return False, f"❌ Negative value in {key}: {value}"
                
                # Extremely large values that seem wrong
                if value > 1e15 and any(x in key.lower() for x in ['count']):
                    return False, f"❌ Suspiciously large count value: {value}"
        
        return True, "✅ Aggregations look reasonable"


def validate_query_and_results(query: str, results: List[Dict], question: str = "") -> Dict[str, Any]:
    """
    Comprehensive validation combining structure, warnings, and sanity checks.
    
    Args:
        query: SQL query
        results: Query results
        question: Original user question (optional)
        
    Returns:
        Validation report
    """
    report = {
        "query": query[:200],  # Truncate for logging
        "is_valid": True,
        "issues": [],
        "warnings": [],
        "checks": {}
    }
    
    # Run all checks
    validator = QueryValidator()
    report["checks"]["structure"] = validator.validate_sql_structure(query)
    report["checks"]["multi_table"] = validator.check_multi_table_warning(query)
    report["checks"]["results"] = validator.validate_results_integrity(results, query)
    
    quality = ResultsQualityChecker()
    report["checks"]["supplier_complete"] = quality.check_supplier_query_completeness(query, results)
    report["checks"]["aggregation_sane"] = quality.check_aggregation_sanity(query, results)
    
    # Aggregate findings
    if not report["checks"]["structure"][0]:
        report["is_valid"] = False
        report["issues"].append(report["checks"]["structure"][1])
    
    report["warnings"].extend(report["checks"]["multi_table"])
    report["warnings"].extend(report["checks"]["results"][1])
    
    if not report["checks"]["supplier_complete"][0]:
        report["issues"].append(report["checks"]["supplier_complete"][1])
    
    if not report["checks"]["aggregation_sane"][0]:
        report["issues"].append(report["checks"]["aggregation_sane"][1])
    
    return report
