"""
Report Templates Module for DBAI
Pre-defined SQL templates with semantic matching
Build 30 - Phase 1
"""

import json
import logging
import re
import uuid
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path
from src.utils.atomic_write import atomic_write_json, atomic_read_json

logger = logging.getLogger(__name__)

# =============================================================================
# TEMPLATE MODEL
# =============================================================================

class ReportTemplate:
    """Represents a pre-defined report template"""
    
    def __init__(
        self,
        name: str,
        description: str,
        sql_template: str,
        parameters: Optional[List[Dict[str, Any]]] = None,
        sample_questions: Optional[List[str]] = None,
        category: str = "General",
        database_type: str = "mssql",
        template_id: Optional[str] = None,
        created_at: Optional[str] = None,
        last_used: Optional[str] = None,
        use_count: int = 0,
        is_active: bool = True,
        source: str = "manual"
    ):
        self.template_id = template_id or str(uuid.uuid4())[:8]
        self.name = name
        self.description = description
        self.sql_template = sql_template
        self.parameters = parameters or []
        self.sample_questions = sample_questions or []
        self.category = category
        self.database_type = database_type
        self.created_at = created_at or datetime.now().isoformat()
        self.last_used = last_used
        self.use_count = use_count
        self.is_active = is_active
        self.source = source  # "manual", "imported", "correction"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON storage"""
        return {
            "template_id": self.template_id,
            "name": self.name,
            "description": self.description,
            "sql_template": self.sql_template,
            "parameters": self.parameters,
            "sample_questions": self.sample_questions,
            "category": self.category,
            "database_type": self.database_type,
            "created_at": self.created_at,
            "last_used": self.last_used,
            "use_count": self.use_count,
            "is_active": self.is_active,
            "source": self.source
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReportTemplate":
        """Create from dictionary"""
        return cls(
            template_id=data.get("template_id"),
            name=data.get("name", "Untitled"),
            description=data.get("description", ""),
            sql_template=data.get("sql_template", ""),
            parameters=data.get("parameters", []),
            sample_questions=data.get("sample_questions", []),
            category=data.get("category", "General"),
            database_type=data.get("database_type", "mssql"),
            created_at=data.get("created_at"),
            last_used=data.get("last_used"),
            use_count=data.get("use_count", 0),
            is_active=data.get("is_active", True),
            source=data.get("source", "manual")
        )


# =============================================================================
# PARAMETER EXTRACTION
# =============================================================================

class ParameterExtractor:
    """Extracts parameters from user questions"""
    
    # Common patterns for parameter extraction
    PATTERNS = {
        "top_n": [
            r"top\s+(\d+)",
            r"first\s+(\d+)",
            r"(\d+)\s+(?:items|records|rows)"
        ],
        "date": [
            r"(\d{4}-\d{2}-\d{2})",
            r"(\d{1,2}/\d{1,2}/\d{4})",
            r"(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{4}",
            r"(last|this)\s+(week|month|year)"
        ],
        "year": [
            r"(?:year|in)\s+(\d{4})",
            r"(\d{4})(?:\s+data|\s+report)?"
        ],
        "month": [
            r"(january|february|march|april|may|june|july|august|september|october|november|december)",
            r"month\s+(\d{1,2})"
        ],
        "limit": [
            r"limit\s+(\d+)",
            r"show\s+(\d+)"
        ]
    }
    
    @classmethod
    def extract_parameters(cls, question: str) -> Dict[str, Any]:
        """
        Extract parameters from user question.
        
        Args:
            question: User's question text
            
        Returns:
            Dictionary of extracted parameters
        """
        params = {}
        question_lower = question.lower()
        
        for param_name, patterns in cls.PATTERNS.items():
            for pattern in patterns:
                match = re.search(pattern, question_lower)
                if match:
                    value = match.group(1)
                    # Convert numeric strings
                    if value.isdigit():
                        value = int(value)
                    params[param_name] = value
                    break  # Take first match for this param
        
        return params
    
    @classmethod
    def apply_parameters(cls, sql_template: str, params: Dict[str, Any]) -> str:
        """
        Apply extracted parameters to SQL template.
        
        Args:
            sql_template: SQL template with {param} placeholders
            params: Dictionary of parameter values
            
        Returns:
            SQL with parameters applied
        """
        result = sql_template
        
        # Replace {param} style placeholders
        for param_name, value in params.items():
            placeholder = "{" + param_name + "}"
            if placeholder in result:
                # Handle different value types
                if isinstance(value, int):
                    result = result.replace(placeholder, str(value))
                elif isinstance(value, str):
                    # Escape single quotes for SQL
                    safe_value = value.replace("'", "''")
                    result = result.replace(placeholder, safe_value)
        
        # Handle TOP N pattern specifically for MSSQL
        top_n = params.get("top_n") or params.get("limit")
        if top_n:
            # Replace TOP {n} patterns
            result = re.sub(r"TOP\s+\{\w+\}", f"TOP {top_n}", result, flags=re.IGNORECASE)
            # If no TOP clause but has LIMIT, convert for MSSQL
            if "TOP" not in result.upper() and "LIMIT" in result.upper():
                result = re.sub(r"LIMIT\s+\d+", f"", result)
                # Add TOP after SELECT
                result = re.sub(r"SELECT\s+", f"SELECT TOP {top_n} ", result, count=1, flags=re.IGNORECASE)
        
        return result


# =============================================================================
# TEMPLATE MATCHER
# =============================================================================

class TemplateMatcher:
    """Matches user questions to templates using semantic similarity"""
    
    def __init__(self, match_threshold: float = 0.90, suggest_threshold: float = 0.70):
        self.match_threshold = match_threshold
        self.suggest_threshold = suggest_threshold
    
    def similarity(self, text1: str, text2: str) -> float:
        """
        Calculate similarity between two texts.
        
        Uses SequenceMatcher for basic similarity.
        Could be enhanced with embeddings for better semantic matching.
        
        Args:
            text1: First text
            text2: Second text
            
        Returns:
            Similarity score 0.0 to 1.0
        """
        # Normalize texts
        t1 = text1.lower().strip()
        t2 = text2.lower().strip()
        
        # Use SequenceMatcher for string similarity
        return SequenceMatcher(None, t1, t2).ratio()
    
    def match_template(
        self,
        question: str,
        templates: List[ReportTemplate]
    ) -> Tuple[Optional[ReportTemplate], float, List[Tuple[ReportTemplate, float]]]:
        """
        Find best matching template for a question.
        
        Args:
            question: User's question
            templates: List of available templates
            
        Returns:
            Tuple of (best_match, confidence, suggestions)
            - best_match: Template if above match_threshold, else None
            - confidence: Confidence score of best match
            - suggestions: List of (template, score) for templates above suggest_threshold
        """
        if not templates:
            return None, 0.0, []
        
        scores = []
        question_lower = question.lower()
        
        for template in templates:
            if not template.is_active:
                continue
            
            # Score against name and description
            name_score = self.similarity(question, template.name)
            desc_score = self.similarity(question, template.description)
            
            # Score against sample questions
            sample_scores = [
                self.similarity(question, sample)
                for sample in template.sample_questions
            ]
            best_sample_score = max(sample_scores) if sample_scores else 0.0
            
            # Weight: sample questions > description > name
            final_score = max(
                best_sample_score * 1.0,
                desc_score * 0.9,
                name_score * 0.8
            )
            
            scores.append((template, final_score))
        
        # Sort by score descending
        scores.sort(key=lambda x: x[1], reverse=True)
        
        # Get suggestions above suggest_threshold
        suggestions = [(t, s) for t, s in scores if s >= self.suggest_threshold]
        
        # Get best match if above match_threshold
        if scores and scores[0][1] >= self.match_threshold:
            return scores[0][0], scores[0][1], suggestions
        else:
            best_score = scores[0][1] if scores else 0.0
            return None, best_score, suggestions


# =============================================================================
# TEMPLATE MANAGER
# =============================================================================

class ReportTemplateManager:
    """
    Manages report templates.
    Handles CRUD operations, matching, and statistics.
    """
    
    _instance = None
    
    def __new__(cls):
        """Singleton pattern"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._storage_path = Path(__file__).parent.parent / "cache" / "report_templates.json"
        self._templates: Dict[str, ReportTemplate] = {}
        self._matcher = TemplateMatcher()
        self._load_templates()
        self._initialized = True
        
        logger.info("ReportTemplateManager initialized")
    
    def _load_templates(self) -> None:
        """Load templates from storage"""
        if not self._storage_path.exists():
            self._templates = {}
            self._create_default_templates()
            return
        
        try:
            with open(self._storage_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self._templates = {
                tid: ReportTemplate.from_dict(tdata)
                for tid, tdata in data.items()
            }
            logger.info(f"Loaded {len(self._templates)} report templates")
        except Exception as e:
            logger.error(f"Failed to load templates: {e}")
            self._templates = {}
    
    def _save_templates(self) -> bool:
        """Save templates to storage"""
        try:
            self._storage_path.parent.mkdir(parents=True, exist_ok=True)
            
            data = {
                tid: t.to_dict()
                for tid, t in self._templates.items()
            }
            atomic_write_json(self._storage_path, data)
            return True
        except Exception as e:
            logger.error(f"Failed to save templates: {e}")
            return False
    
    def _create_default_templates(self) -> None:
        """Create some default templates for demonstration"""
        defaults = [
            ReportTemplate(
                name="GreigeData Overview",
                description="Overview of GreigeData by supplier with date and type filtering",
                sql_template=(
                    "SELECT SUPP_NAME, DATEPART(month, DOCDATE) AS Month, "
                    "SUM(METER) AS TotalMeter, SUM(AMOUNT) AS TotalAmount, "
                    "AVG(PRICE) AS AvgPrice "
                    "FROM [kam].[dbo].[GreigeData] "
                    "WHERE DOCDATE BETWEEN '{start_date}' AND '{end_date}' "
                    "{type_filter} "
                    "GROUP BY SUPP_NAME, DATEPART(month, DOCDATE) "
                    "ORDER BY TotalAmount DESC"
                ),
                parameters=[
                    {"name": "start_date", "type": "date", "default": "2024-01-01"},
                    {"name": "end_date", "type": "date", "default": "2025-12-31"},
                    {"name": "type_filter", "type": "string", "default": ""}
                ],
                sample_questions=[
                    "show griege overview by supplier this month",
                    "griege arrival data from Jan to Mar 2025",
                    "total griege amount by supplier",
                    "griege data excluding rejections"
                ],
                category="GreigeData",
                database_type="mssql"
            ),
            ReportTemplate(
                name="YarnData Trend",
                description="Yarndata trends across suppliers with date, type and top N filtering",
                sql_template=(
                    "SELECT TOP {top_n} SUPPLIER, DATEPART(year, DOCDATE) AS Year, "
                    "DATEPART(month, DOCDATE) AS Month, "
                    "SUM(LBS) AS TotalLBS, SUM(AMOUNT) AS TotalAmount "
                    "FROM [kam].[dbo].[YarnData] "
                    "WHERE DOCDATE >= '{start_date}' "
                    "{type_filter} "
                    "GROUP BY SUPPLIER, DATEPART(year, DOCDATE), DATEPART(month, DOCDATE) "
                    "ORDER BY TotalAmount DESC"
                ),
                parameters=[
                    {"name": "start_date", "type": "date", "default": "2024-01-01"},
                    {"name": "top_n", "type": "int", "default": 10},
                    {"name": "type_filter", "type": "string", "default": ""}
                ],
                sample_questions=[
                    "show top 5 yarn suppliers by amount this month",
                    "yarn issue data since Jan 2025",
                    "total yarn in LBS by supplier",
                    "yarn trends excluding arrivals",
                    "top 10 yarn suppliers this year"
                ],
                category="YarnData",
                database_type="mssql"
            ),
            ReportTemplate(
                name="Top N Sales",
                description="Get top N sales by amount",
                sql_template="SELECT TOP {top_n} * FROM Sales ORDER BY Amount DESC",
                parameters=[{"name": "top_n", "type": "int", "default": 10}],
                sample_questions=[
                    "show top 10 sales",
                    "top 5 sales by amount",
                    "what are the highest sales"
                ],
                category="Sales"
            ),
            ReportTemplate(
                name="Daily Summary",
                description="Get summary for a specific date",
                sql_template="SELECT * FROM DailySummary WHERE Date = '{date}'",
                parameters=[{"name": "date", "type": "date", "default": "today"}],
                sample_questions=[
                    "daily summary for 2024-01-15",
                    "summary for today",
                    "what happened on this date"
                ],
                category="Reports"
            )
        ]
        
        for template in defaults:
            self._templates[template.template_id] = template
        
        self._save_templates()
        logger.info(f"Created {len(defaults)} default templates")
    
    def set_thresholds(self, match_threshold: float = 0.90, suggest_threshold: float = 0.70) -> None:
        """Update matching thresholds"""
        self._matcher.match_threshold = match_threshold
        self._matcher.suggest_threshold = suggest_threshold
    
    def add_template(self, template: ReportTemplate) -> Tuple[bool, str]:
        """Add a new template"""
        self._templates[template.template_id] = template
        
        if self._save_templates():
            logger.info(f"Template added: {template.template_id}")
            return True, f"Template '{template.name}' added"
        else:
            return False, "Failed to save template"
    
    def update_template(self, template_id: str, updates: Dict[str, Any]) -> Tuple[bool, str]:
        """Update an existing template"""
        if template_id not in self._templates:
            return False, f"Template not found: {template_id}"
        
        template = self._templates[template_id]
        
        for key, value in updates.items():
            if hasattr(template, key):
                setattr(template, key, value)
        
        if self._save_templates():
            return True, "Template updated"
        else:
            return False, "Failed to save template"
    
    def delete_template(self, template_id: str) -> Tuple[bool, str]:
        """Delete a template"""
        if template_id not in self._templates:
            return False, f"Template not found: {template_id}"
        
        del self._templates[template_id]
        
        if self._save_templates():
            return True, "Template deleted"
        else:
            return False, "Failed to delete template"
    
    def get_template(self, template_id: str) -> Optional[ReportTemplate]:
        """Get a specific template"""
        return self._templates.get(template_id)
    
    def get_all_templates(
        self,
        category: Optional[str] = None,
        active_only: bool = True
    ) -> List[ReportTemplate]:
        """Get all templates with optional filtering"""
        templates = list(self._templates.values())
        
        if active_only:
            templates = [t for t in templates if t.is_active]
        
        if category:
            templates = [t for t in templates if t.category == category]
        
        # Sort by use_count descending
        templates.sort(key=lambda t: t.use_count, reverse=True)
        
        return templates
    
    def get_categories(self) -> List[str]:
        """Get list of all categories"""
        categories = set(t.category for t in self._templates.values())
        return sorted(categories)
    
    def match_question(
        self,
        question: str,
        database_type: Optional[str] = None
    ) -> Tuple[Optional[ReportTemplate], float, List[Tuple[ReportTemplate, float]]]:
        """
        Match a question to templates.
        
        Args:
            question: User's question
            database_type: Filter by database type, or None for all
            
        Returns:
            Tuple of (best_match, confidence, suggestions)
        """
        templates = self.get_all_templates(active_only=True)
        
        if database_type:
            templates = [t for t in templates if t.database_type == database_type]
        
        return self._matcher.match_template(question, templates)
    
    def execute_template(
        self,
        template_id: str,
        question: str,
        run_query_func
    ) -> Dict[str, Any]:
        """
        Execute a template with extracted parameters.
        
        Args:
            template_id: ID of template to execute
            question: User's question (for parameter extraction)
            run_query_func: Function to run the SQL query
            
        Returns:
            Query result dictionary
        """
        template = self.get_template(template_id)
        if not template:
            return {"error": f"Template not found: {template_id}"}
        
        # Extract parameters from question
        params = ParameterExtractor.extract_parameters(question)
        
        # Apply default values for missing parameters
        for param_def in template.parameters:
            param_name = param_def.get("name")
            if param_name and param_name not in params:
                params[param_name] = param_def.get("default", "")
        
        # Apply parameters to SQL
        sql = ParameterExtractor.apply_parameters(template.sql_template, params)
        
        # Update usage stats
        template.use_count += 1
        template.last_used = datetime.now().isoformat()
        self._save_templates()
        
        # Execute query
        result = run_query_func(sql)
        
        return {
            "template": template.name,
            "sql": sql,
            "parameters": params,
            "result": result
        }
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get template usage statistics"""
        templates = list(self._templates.values())
        
        total = len(templates)
        active = sum(1 for t in templates if t.is_active)
        total_uses = sum(t.use_count for t in templates)
        
        # Top 5 most used
        by_usage = sorted(templates, key=lambda t: t.use_count, reverse=True)[:5]
        top_used = [{"name": t.name, "uses": t.use_count} for t in by_usage]
        
        return {
            "total": total,
            "active": active,
            "total_uses": total_uses,
            "top_used": top_used
        }
    
    def import_from_csv_analysis(
        self,
        analysis_result: Dict[str, Any],
        name: str,
        description: str
    ) -> Tuple[bool, str, Optional[ReportTemplate]]:
        """
        Import a template from CSV analysis results.
        
        Args:
            analysis_result: Result from CSV analysis containing SQL
            name: Name for the template
            description: Description of what the template does
            
        Returns:
            Tuple of (success, message, template)
        """
        sql = analysis_result.get("suggested_sql", "")
        if not sql:
            return False, "No SQL found in analysis result", None
        
        # Extract sample question if available
        sample_questions = []
        if "original_question" in analysis_result:
            sample_questions.append(analysis_result["original_question"])
        
        template = ReportTemplate(
            name=name,
            description=description,
            sql_template=sql,
            sample_questions=sample_questions,
            source="imported"
        )
        
        success, message = self.add_template(template)
        return success, message, template if success else None


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def get_template_manager() -> ReportTemplateManager:
    """Get the singleton ReportTemplateManager instance"""
    return ReportTemplateManager()


def match_question_to_template(
    question: str,
    threshold: Optional[float] = None
) -> Tuple[Optional[Dict], float]:
    """
    Quick function to check if a question matches a template.
    
    Args:
        question: User's question
        threshold: Override match threshold
        
    Returns:
        Tuple of (template_dict, confidence) or (None, 0.0)
    """
    manager = get_template_manager()
    
    if threshold:
        manager.set_thresholds(match_threshold=threshold)
    
    match, confidence, _ = manager.match_question(question)
    
    if match:
        return match.to_dict(), confidence
    return None, confidence
