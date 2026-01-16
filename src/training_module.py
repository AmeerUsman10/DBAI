"""
Data Training Module - Knowledge Capture System
Maps business questions to MSSQL/Oracle SQL with reasoning and metadata.
"""
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
import logging

logger = logging.getLogger(__name__)

# Categories for structured tagging
CATEGORY_OPTIONS = [
    "time_series", "aggregation", "ranking", "forecasting", "anomaly_detection",
    "joins", "window_functions", "business_metric", "filtering", "grouping",
    "subquery", "union", "cte", "data_transformation"
]

COMPLEXITY_LEVELS = ["simple", "intermediate", "advanced", "expert"]

@dataclass
class TrainingExample:
    """Single training example with dual-engine support."""
    id: str
    question: str
    schema_context: str
    mssql_query: str
    mssql_explanation: str
    oracle_query: str
    oracle_explanation: str
    categories: List[str]
    complexity: str
    assumptions: str
    processing_type: str  # "sql_only" or "sql_plus_postprocessing"
    created_at: str
    updated_at: str
    version: int = 1
    source: str = "manual"
    priority: int = 1
    validated: bool = False
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'TrainingExample':
        return cls(**data)

@dataclass 
class IngestedQuery:
    """Query captured from user interaction for review."""
    id: str
    question: str
    schema_used: str
    ai_response: Dict
    user_feedback: str
    user_correction: Optional[str]
    timestamp: str
    reviewed: bool = False
    converted_to_example: bool = False
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'IngestedQuery':
        return cls(**data)

class TrainingDataManager:
    """Manages training examples and ingested queries."""
    
    def __init__(self, data_dir: Path = None):
        if data_dir is None:
            data_dir = Path(__file__).parent.parent / "training_data"
        
        self.data_dir = data_dir
        self.data_dir.mkdir(exist_ok=True)
        
        self.examples_file = self.data_dir / "training_examples.json"
        self.ingested_file = self.data_dir / "ingested_queries.json"
        self.history_dir = self.data_dir / "history"
        self.history_dir.mkdir(exist_ok=True)
        
        self.examples: Dict[str, TrainingExample] = self._load_examples()
        self.ingested: Dict[str, IngestedQuery] = self._load_ingested()
    
    def _load_examples(self) -> Dict[str, TrainingExample]:
        if not self.examples_file.exists():
            return {}
        try:
            with open(self.examples_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return {k: TrainingExample.from_dict(v) for k, v in data.items()}
        except Exception as e:
            logger.error(f"Error loading training examples: {e}")
            return {}
    
    def _load_ingested(self) -> Dict[str, IngestedQuery]:
        if not self.ingested_file.exists():
            return {}
        try:
            with open(self.ingested_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return {k: IngestedQuery.from_dict(v) for k, v in data.items()}
        except Exception as e:
            logger.error(f"Error loading ingested queries: {e}")
            return {}
    
    def _save_examples(self):
        if self.examples_file.exists():
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = self.history_dir / f"examples_backup_{timestamp}.json"
            import shutil
            shutil.copy2(self.examples_file, backup_file)
        
        data = {k: v.to_dict() for k, v in self.examples.items()}
        with open(self.examples_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def _save_ingested(self):
        data = {k: v.to_dict() for k, v in self.ingested.items()}
        with open(self.ingested_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def add_example(self, example: TrainingExample) -> str:
        if example.id in self.examples:
            example.version = self.examples[example.id].version + 1
            example.updated_at = datetime.now().isoformat()
        
        self.examples[example.id] = example
        self._save_examples()
        logger.info(f"Saved training example: {example.id} (v{example.version})")
        return example.id
    
    def get_example(self, example_id: str) -> Optional[TrainingExample]:
        return self.examples.get(example_id)
    
    def delete_example(self, example_id: str) -> bool:
        if example_id in self.examples:
            del self.examples[example_id]
            self._save_examples()
            logger.info(f"Deleted training example: {example_id}")
            return True
        return False
    
    def list_examples(self, category: Optional[str] = None, 
                     complexity: Optional[str] = None) -> List[TrainingExample]:
        examples = list(self.examples.values())
        
        if category:
            examples = [e for e in examples if category in e.categories]
        
        if complexity:
            examples = [e for e in examples if e.complexity == complexity]
        
        return sorted(examples, key=lambda x: (-x.priority, x.updated_at), reverse=False)
    
    def ingest_query(self, question: str, schema: str, ai_response: Dict,
                     feedback: str, correction: Optional[str] = None) -> str:
        query_id = str(uuid.uuid4())[:8]
        ingested = IngestedQuery(
            id=query_id,
            question=question,
            schema_used=schema,
            ai_response=ai_response,
            user_feedback=feedback,
            user_correction=correction,
            timestamp=datetime.now().isoformat(),
            reviewed=False,
            converted_to_example=False
        )
        
        self.ingested[query_id] = ingested
        self._save_ingested()
        logger.info(f"Ingested query: {query_id}")
        return query_id
    
    def get_ingested_for_review(self) -> List[IngestedQuery]:
        return [q for q in self.ingested.values() 
                if not q.reviewed and q.user_feedback in ["corrected", "rejected"]]
    
    def mark_reviewed(self, ingested_id: str):
        """Mark an ingested query as reviewed."""
        if ingested_id in self.ingested:
            self.ingested[ingested_id].reviewed = True
            self._save_ingested()
    
    def convert_ingested_to_example(self, ingested_id: str, example: TrainingExample) -> str:
        if ingested_id in self.ingested:
            self.ingested[ingested_id].converted_to_example = True
            self.ingested[ingested_id].reviewed = True
            self._save_ingested()
            
            example.source = "ingested"
            return self.add_example(example)
        return ""
    
    def get_coverage_stats(self) -> Dict[str, Any]:
        stats = {
            "total_examples": len(self.examples),
            "by_category": {},
            "by_complexity": {},
            "by_engine": {"mssql": 0, "oracle": 0, "both": 0},
            "by_priority": {},
            "validated": 0,
            "needs_review": len(self.get_ingested_for_review())
        }
        
        for example in self.examples.values():
            for cat in example.categories:
                stats["by_category"][cat] = stats["by_category"].get(cat, 0) + 1
            
            stats["by_complexity"][example.complexity] = \
                stats["by_complexity"].get(example.complexity, 0) + 1
            
            has_mssql = bool(example.mssql_query.strip())
            has_oracle = bool(example.oracle_query.strip())
            if has_mssql and has_oracle:
                stats["by_engine"]["both"] += 1
            elif has_mssql:
                stats["by_engine"]["mssql"] += 1
            elif has_oracle:
                stats["by_engine"]["oracle"] += 1
            
            stats["by_priority"][example.priority] = \
                stats["by_priority"].get(example.priority, 0) + 1
            
            if example.validated:
                stats["validated"] += 1
        
        return stats
    
    def search_examples(self, query: str) -> List[TrainingExample]:
        query_lower = query.lower()
        results = []
        
        for example in self.examples.values():
            if (query_lower in example.question.lower() or
                query_lower in example.mssql_query.lower() or
                query_lower in example.oracle_query.lower() or
                query_lower in example.assumptions.lower()):
                results.append(example)
        
        return results
    
    def run_regression_test(self, test_questions: List[str]) -> Dict[str, Any]:
        """Run regression tests against canonical examples."""
        from src.llm import make_sql_chain
        from src.database import get_sql_database
        
        results = {
            "total_tests": 0,
            "passed": 0,
            "failed": 0,
            "details": []
        }
        
        # Find examples matching test questions
        for question in test_questions:
            matching = [e for e in self.examples.values() 
                       if question.lower() in e.question.lower()]
            
            if not matching:
                continue
            
            example = matching[0]
            results["total_tests"] += 1
            
            # Test MSSQL if available
            if example.mssql_query.strip():
                try:
                    db = get_sql_database()
                    chain = make_sql_chain(db, "mssql")
                    response = chain.invoke({"question": example.question})
                    
                    # Simple comparison (could be enhanced)
                    generated_sql = response.get("result", "").strip()
                    expected_sql = example.mssql_query.strip()
                    
                    passed = generated_sql == expected_sql
                    if passed:
                        results["passed"] += 1
                    else:
                        results["failed"] += 1
                    
                    results["details"].append({
                        "question": example.question,
                        "engine": "mssql",
                        "passed": passed,
                        "expected": expected_sql,
                        "generated": generated_sql
                    })
                except Exception as e:
                    results["failed"] += 1
                    results["details"].append({
                        "question": example.question,
                        "engine": "mssql",
                        "passed": False,
                        "error": str(e)
                    })
        
        return results

_training_manager: Optional[TrainingDataManager] = None

def get_training_manager() -> TrainingDataManager:
    global _training_manager
    if _training_manager is None:
        _training_manager = TrainingDataManager()
    return _training_manager
