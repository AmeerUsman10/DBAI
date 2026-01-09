"""
Correction Workflow Module for DBAI
Manages user-submitted corrections with IT approval queue
Build 30 - Phase 1
"""

import json
import logging
import os
import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from src.utils.atomic_write import atomic_write_json, atomic_read_json
from pathlib import Path

logger = logging.getLogger(__name__)

# =============================================================================
# CONSTANTS & ENUMS
# =============================================================================

class CorrectionStatus(str, Enum):
    """Status of a correction request"""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    MODIFIED = "modified"  # Approved with modifications


class CorrectionType(str, Enum):
    """Type of correction"""
    SQL_FIX = "sql_fix"           # Fix to generated SQL
    RESULT_WRONG = "result_wrong"  # Results don't match expectation
    MISSING_DATA = "missing_data"  # Query missed some data


# =============================================================================
# CORRECTION REQUEST MODEL
# =============================================================================

class CorrectionRequest:
    """Represents a single correction request"""
    
    def __init__(
        self,
        original_question: str,
        original_sql: str,
        suggested_sql: str,
        correction_type: CorrectionType = CorrectionType.SQL_FIX,
        user_notes: str = "",
        preview_results: Optional[Dict] = None,
        request_id: Optional[str] = None,
        created_at: Optional[str] = None,
        status: CorrectionStatus = CorrectionStatus.PENDING,
        reviewer_notes: str = "",
        reviewed_at: Optional[str] = None,
        final_sql: Optional[str] = None,
        create_training_rule: bool = False
    ):
        self.request_id = request_id or str(uuid.uuid4())[:8]
        self.original_question = original_question
        self.original_sql = original_sql
        self.suggested_sql = suggested_sql
        self.correction_type = correction_type
        self.user_notes = user_notes
        self.preview_results = preview_results
        self.created_at = created_at or datetime.now().isoformat()
        self.status = status
        self.reviewer_notes = reviewer_notes
        self.reviewed_at = reviewed_at
        self.final_sql = final_sql
        self.create_training_rule = create_training_rule
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON storage"""
        return {
            "request_id": self.request_id,
            "original_question": self.original_question,
            "original_sql": self.original_sql,
            "suggested_sql": self.suggested_sql,
            "correction_type": self.correction_type.value if isinstance(self.correction_type, CorrectionType) else self.correction_type,
            "user_notes": self.user_notes,
            "preview_results": self.preview_results,
            "created_at": self.created_at,
            "status": self.status.value if isinstance(self.status, CorrectionStatus) else self.status,
            "reviewer_notes": self.reviewer_notes,
            "reviewed_at": self.reviewed_at,
            "final_sql": self.final_sql,
            "create_training_rule": self.create_training_rule
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CorrectionRequest":
        """Create from dictionary"""
        # Handle enum conversion
        correction_type = data.get("correction_type", CorrectionType.SQL_FIX)
        if isinstance(correction_type, str):
            correction_type = CorrectionType(correction_type)
        
        status = data.get("status", CorrectionStatus.PENDING)
        if isinstance(status, str):
            status = CorrectionStatus(status)
        
        return cls(
            original_question=data.get("original_question", ""),
            original_sql=data.get("original_sql", ""),
            suggested_sql=data.get("suggested_sql", ""),
            correction_type=correction_type,
            user_notes=data.get("user_notes", ""),
            preview_results=data.get("preview_results"),
            request_id=data.get("request_id"),
            created_at=data.get("created_at"),
            status=status,
            reviewer_notes=data.get("reviewer_notes", ""),
            reviewed_at=data.get("reviewed_at"),
            final_sql=data.get("final_sql"),
            create_training_rule=data.get("create_training_rule", False)
        )


# =============================================================================
# CORRECTION WORKFLOW MANAGER
# =============================================================================

class CorrectionWorkflow:
    """
    Manages the correction request workflow.
    Handles submission, approval, rejection, and training rule creation.
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
        
        self._storage_path = Path(__file__).parent.parent / "logs" / "correction_requests.json"
        self._requests: Dict[str, CorrectionRequest] = {}
        self._load_requests()
        self._initialized = True
        
        logger.info("CorrectionWorkflow initialized")
    
    def _load_requests(self) -> None:
        """Load correction requests from storage"""
        if not self._storage_path.exists():
            self._requests = {}
            return
        
        try:
            with open(self._storage_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self._requests = {
                req_id: CorrectionRequest.from_dict(req_data)
                for req_id, req_data in data.items()
            }
            logger.info(f"Loaded {len(self._requests)} correction requests")
        except Exception as e:
            logger.error(f"Failed to load correction requests: {e}")
            self._requests = {}
    
    def _save_requests(self) -> bool:
        """Save correction requests to storage"""
        try:
            # Ensure logs directory exists
            self._storage_path.parent.mkdir(parents=True, exist_ok=True)
            
            data = {
                req_id: req.to_dict()
                for req_id, req in self._requests.items()
            }
            atomic_write_json(self._storage_path, data)
            return True
        except Exception as e:
            logger.error(f"Failed to save correction requests: {e}")
            return False
    
    def submit_correction(
        self,
        original_question: str,
        original_sql: str,
        suggested_sql: str,
        correction_type: CorrectionType = CorrectionType.SQL_FIX,
        user_notes: str = "",
        preview_results: Optional[Dict] = None
    ) -> Tuple[bool, str, Optional[CorrectionRequest]]:
        """
        Submit a new correction request.
        
        Args:
            original_question: The user's original question
            original_sql: The SQL that was generated
            suggested_sql: The corrected SQL from user
            correction_type: Type of correction
            user_notes: Optional notes from user
            preview_results: Optional preview query results
            
        Returns:
            Tuple of (success, message, request)
        """
        try:
            request = CorrectionRequest(
                original_question=original_question,
                original_sql=original_sql,
                suggested_sql=suggested_sql,
                correction_type=correction_type,
                user_notes=user_notes,
                preview_results=preview_results
            )
            
            self._requests[request.request_id] = request
            
            if self._save_requests():
                logger.info(f"Correction request submitted: {request.request_id}")
                return True, f"Correction submitted (ID: {request.request_id})", request
            else:
                return False, "Failed to save correction request", None
                
        except Exception as e:
            error_msg = f"Failed to submit correction: {str(e)}"
            logger.error(error_msg)
            return False, error_msg, None
    
    def get_pending_requests(self) -> List[CorrectionRequest]:
        """Get all pending correction requests"""
        return [
            req for req in self._requests.values()
            if req.status == CorrectionStatus.PENDING
        ]
    
    def get_all_requests(
        self,
        status_filter: Optional[CorrectionStatus] = None,
        limit: int = 100
    ) -> List[CorrectionRequest]:
        """
        Get correction requests with optional filtering.
        
        Args:
            status_filter: Filter by status, or None for all
            limit: Maximum number to return
            
        Returns:
            List of correction requests, newest first
        """
        requests = list(self._requests.values())
        
        if status_filter:
            requests = [r for r in requests if r.status == status_filter]
        
        # Sort by created_at descending
        requests.sort(key=lambda r: r.created_at, reverse=True)
        
        return requests[:limit]
    
    def get_request(self, request_id: str) -> Optional[CorrectionRequest]:
        """Get a specific correction request by ID"""
        return self._requests.get(request_id)
    
    def approve_request(
        self,
        request_id: str,
        reviewer_notes: str = "",
        final_sql: Optional[str] = None,
        create_training_rule: bool = True
    ) -> Tuple[bool, str]:
        """
        Approve a correction request.
        
        Args:
            request_id: ID of request to approve
            reviewer_notes: Optional reviewer notes
            final_sql: Modified SQL if changed, or None to use suggested_sql
            create_training_rule: Whether to create a training rule
            
        Returns:
            Tuple of (success, message)
        """
        request = self._requests.get(request_id)
        if not request:
            return False, f"Request not found: {request_id}"
        
        if request.status != CorrectionStatus.PENDING:
            return False, f"Request already processed: {request.status.value}"
        
        # Determine if this was modified or straight approved
        if final_sql and final_sql.strip() != request.suggested_sql.strip():
            request.status = CorrectionStatus.MODIFIED
            request.final_sql = final_sql
        else:
            request.status = CorrectionStatus.APPROVED
            request.final_sql = request.suggested_sql
        
        request.reviewer_notes = reviewer_notes
        request.reviewed_at = datetime.now().isoformat()
        request.create_training_rule = create_training_rule
        
        if self._save_requests():
            logger.info(f"Correction approved: {request_id}")
            
            # Create training rule if requested
            if create_training_rule:
                self._create_training_rule(request)
            
            return True, f"Request {request.status.value}"
        else:
            return False, "Failed to save approval"
    
    def reject_request(
        self,
        request_id: str,
        reviewer_notes: str = ""
    ) -> Tuple[bool, str]:
        """
        Reject a correction request.
        
        Args:
            request_id: ID of request to reject
            reviewer_notes: Reason for rejection
            
        Returns:
            Tuple of (success, message)
        """
        request = self._requests.get(request_id)
        if not request:
            return False, f"Request not found: {request_id}"
        
        if request.status != CorrectionStatus.PENDING:
            return False, f"Request already processed: {request.status.value}"
        
        request.status = CorrectionStatus.REJECTED
        request.reviewer_notes = reviewer_notes
        request.reviewed_at = datetime.now().isoformat()
        request.create_training_rule = False
        
        if self._save_requests():
            logger.info(f"Correction rejected: {request_id}")
            return True, "Request rejected"
        else:
            return False, "Failed to save rejection"
    
    def _create_training_rule(self, request: CorrectionRequest) -> bool:
        """
        Create a training rule from an approved correction.
        
        Args:
            request: The approved correction request
            
        Returns:
            True if rule created successfully
        """
        try:
            from src.trainer import load_training_rules, save_training_rule
            
            # Load existing rules
            rules = load_training_rules()
            
            # Create new rule
            rule_id = f"correction_{request.request_id}"
            new_rule = {
                "id": rule_id,
                "pattern": request.original_question.lower(),
                "sql_template": request.final_sql or request.suggested_sql,
                "description": f"Correction from request {request.request_id}",
                "created_at": datetime.now().isoformat(),
                "source": "correction_workflow",
                "original_sql": request.original_sql,
                "reviewer_notes": request.reviewer_notes
            }
            
            # Save rule
            if save_training_rule(new_rule):
                logger.info(f"Training rule created from correction: {rule_id}")
                return True
            else:
                logger.warning(f"Failed to save training rule: {rule_id}")
                return False
                
        except Exception as e:
            logger.error(f"Error creating training rule: {e}")
            return False
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get correction workflow statistics"""
        all_requests = list(self._requests.values())
        
        pending_count = sum(1 for r in all_requests if r.status == CorrectionStatus.PENDING)
        approved_count = sum(1 for r in all_requests if r.status == CorrectionStatus.APPROVED)
        rejected_count = sum(1 for r in all_requests if r.status == CorrectionStatus.REJECTED)
        modified_count = sum(1 for r in all_requests if r.status == CorrectionStatus.MODIFIED)
        
        # Calculate approval rate
        total_processed = approved_count + rejected_count + modified_count
        approval_rate = ((approved_count + modified_count) / total_processed * 100) if total_processed > 0 else 0
        
        return {
            "total": len(all_requests),
            "pending": pending_count,
            "approved": approved_count,
            "rejected": rejected_count,
            "modified": modified_count,
            "approval_rate": round(approval_rate, 1)
        }
    
    def clear_old_requests(self, days_to_keep: int = 90) -> int:
        """
        Clear old processed requests.
        
        Args:
            days_to_keep: Number of days to keep requests
            
        Returns:
            Number of requests cleared
        """
        from datetime import timedelta
        
        cutoff = datetime.now() - timedelta(days=days_to_keep)
        cutoff_str = cutoff.isoformat()
        
        to_remove = []
        for req_id, req in self._requests.items():
            # Only remove processed (not pending) requests older than cutoff
            if req.status != CorrectionStatus.PENDING and req.created_at < cutoff_str:
                to_remove.append(req_id)
        
        for req_id in to_remove:
            del self._requests[req_id]
        
        if to_remove:
            self._save_requests()
            logger.info(f"Cleared {len(to_remove)} old correction requests")
        
        return len(to_remove)


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def get_correction_workflow() -> CorrectionWorkflow:
    """Get the singleton CorrectionWorkflow instance"""
    return CorrectionWorkflow()


def submit_correction(
    original_question: str,
    original_sql: str,
    suggested_sql: str,
    user_notes: str = ""
) -> Tuple[bool, str]:
    """
    Submit a correction request.
    
    Args:
        original_question: The user's original question
        original_sql: The SQL that was generated
        suggested_sql: The corrected SQL
        user_notes: Optional notes
        
    Returns:
        Tuple of (success, message)
    """
    workflow = get_correction_workflow()
    success, message, _ = workflow.submit_correction(
        original_question=original_question,
        original_sql=original_sql,
        suggested_sql=suggested_sql,
        user_notes=user_notes
    )
    return success, message


def get_pending_count() -> int:
    """Get count of pending correction requests"""
    return len(get_correction_workflow().get_pending_requests())
