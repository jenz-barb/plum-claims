from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from enum import Enum


class ClaimDecision(str, Enum):
    APPROVED = "APPROVED"
    PARTIAL = "PARTIAL"
    REJECTED = "REJECTED"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    PENDING_DOCUMENTS = "PENDING_DOCUMENTS"


class DocumentType(str, Enum):
    PRESCRIPTION = "PRESCRIPTION"
    HOSPITAL_BILL = "HOSPITAL_BILL"
    LAB_REPORT = "LAB_REPORT"
    PHARMACY_BILL = "PHARMACY_BILL"
    DENTAL_REPORT = "DENTAL_REPORT"
    DIAGNOSTIC_REPORT = "DIAGNOSTIC_REPORT"
    DISCHARGE_SUMMARY = "DISCHARGE_SUMMARY"


class DocumentQuality(str, Enum):
    GOOD = "GOOD"
    POOR = "POOR"
    UNREADABLE = "UNREADABLE"


class Document(BaseModel):
    file_id: str
    file_name: Optional[str] = None
    actual_type: str
    quality: Optional[str] = "GOOD"
    patient_name_on_doc: Optional[str] = None
    content: Optional[Dict[str, Any]] = None


class ClaimsHistoryItem(BaseModel):
    claim_id: str
    date: str
    amount: float
    provider: Optional[str] = None


class ClaimSubmission(BaseModel):
    member_id: str
    policy_id: str
    claim_category: str
    treatment_date: str
    claimed_amount: float
    hospital_name: Optional[str] = None
    ytd_claims_amount: Optional[float] = 0.0
    claims_history: Optional[List[ClaimsHistoryItem]] = []
    documents: List[Document]
    simulate_component_failure: Optional[bool] = False


class LineItemDecision(BaseModel):
    description: str
    amount: float
    status: str  # APPROVED, REJECTED
    reason: Optional[str] = None


class TraceStep(BaseModel):
    agent: str
    status: str  # PASS, FAIL, SKIPPED, WARNING
    details: str
    data: Optional[Dict[str, Any]] = None


class ClaimResult(BaseModel):
    claim_id: str
    member_id: str
    claim_category: str
    claimed_amount: float
    decision: Optional[ClaimDecision]
    approved_amount: Optional[float] = None
    rejection_reasons: Optional[List[str]] = []
    confidence_score: Optional[float] = None
    message: str
    line_item_decisions: Optional[List[LineItemDecision]] = []
    trace: List[TraceStep] = []
    component_failures: Optional[List[str]] = []
    manual_review_recommended: Optional[bool] = False
    fraud_signals: Optional[List[str]] = []
    financial_breakdown: Optional[Dict[str, Any]] = None
