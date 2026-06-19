"""
LangGraph Claims Processing Pipeline
Nodes: doc_verifier → doc_parser → policy_checker → fraud_detector → decision_engine → trace_builder
Conditional edge: if doc verification fails, skip to early_exit
"""
from langgraph.graph import StateGraph, END
from typing import TypedDict, List, Dict, Any, Optional
from models.schemas import ClaimSubmission, ClaimResult, TraceStep
from agents.document_verifier import run_document_verifier
from agents.document_parser import run_document_parser
from agents.policy_checker import run_policy_checker
from agents.fraud_detector import run_fraud_detector
from agents.decision_engine import run_decision_engine
from agents.trace_builder import run_trace_builder
from models.policy_loader import load_policy
import uuid


class ClaimsState(TypedDict):
    claim: ClaimSubmission
    policy: Dict[str, Any]
    trace: List[TraceStep]
    component_failures: List[str]

    # Doc verification
    doc_verification_passed: Optional[bool]
    doc_errors: Optional[List[Dict]]

    # Parsing
    parsed_documents: Optional[List[Dict]]
    parse_confidence: Optional[float]

    # Policy
    policy_issues: Optional[List[str]]
    policy_data: Optional[Dict]
    policy_passed: Optional[bool]
    diagnosis: Optional[str]
    line_items: Optional[List[Dict]]

    # Fraud
    fraud_score: Optional[float]
    fraud_signals: Optional[List[str]]
    fraud_manual_review: Optional[bool]

    # Decision
    decision: Optional[str]
    approved_amount: Optional[float]
    message: Optional[str]
    confidence_score: Optional[float]
    line_item_decisions: Optional[List]
    financial_breakdown: Optional[Dict]
    manual_review_recommended: Optional[bool]

    # Result
    result: Optional[ClaimResult]


def early_exit_node(state: ClaimsState) -> ClaimsState:
    """Handles doc verification failures — produce a PENDING_DOCUMENTS result"""
    from models.schemas import ClaimDecision
    trace = state.get("trace", [])
    doc_errors = state.get("doc_errors", [])

    messages = [e["message"] for e in doc_errors]
    combined_message = " | ".join(messages)

    trace.append(TraceStep(
        agent="EarlyExit",
        status="FAIL",
        details="Pipeline stopped due to document issues. Member must resubmit.",
        data={"doc_errors": doc_errors}
    ))

    import uuid
    result = __import__("models.schemas", fromlist=["ClaimResult"]).ClaimResult(
        claim_id=f"CLM-{uuid.uuid4().hex[:8].upper()}",
        member_id=state["claim"].member_id,
        claim_category=state["claim"].claim_category,
        claimed_amount=state["claim"].claimed_amount,
        decision=ClaimDecision.PENDING_DOCUMENTS,
        approved_amount=None,
        confidence_score=None,
        message=combined_message,
        trace=trace,
        component_failures=[],
        manual_review_recommended=False,
        fraud_signals=[],
    )

    return {**state, "result": result, "trace": trace}


def route_after_doc_verification(state: ClaimsState) -> str:
    if not state.get("doc_verification_passed", False):
        return "early_exit"
    return "doc_parser"


def build_graph():
    graph = StateGraph(ClaimsState)

    graph.add_node("doc_verifier", run_document_verifier)
    graph.add_node("early_exit", early_exit_node)
    graph.add_node("doc_parser", run_document_parser)
    graph.add_node("policy_checker", run_policy_checker)
    graph.add_node("fraud_detector", run_fraud_detector)
    graph.add_node("decision_engine", run_decision_engine)
    graph.add_node("trace_builder", run_trace_builder)

    graph.set_entry_point("doc_verifier")

    graph.add_conditional_edges(
        "doc_verifier",
        route_after_doc_verification,
        {"early_exit": "early_exit", "doc_parser": "doc_parser"}
    )

    graph.add_edge("early_exit", END)
    graph.add_edge("doc_parser", "policy_checker")
    graph.add_edge("policy_checker", "fraud_detector")
    graph.add_edge("fraud_detector", "decision_engine")
    graph.add_edge("decision_engine", "trace_builder")
    graph.add_edge("trace_builder", END)

    return graph.compile()


def process_claim(claim: ClaimSubmission) -> ClaimResult:
    policy = load_policy()
    graph = build_graph()

    initial_state: ClaimsState = {
        "claim": claim,
        "policy": policy,
        "trace": [],
        "component_failures": [],
        "doc_verification_passed": None,
        "doc_errors": None,
        "parsed_documents": None,
        "parse_confidence": None,
        "policy_issues": None,
        "policy_data": None,
        "policy_passed": None,
        "diagnosis": None,
        "line_items": None,
        "fraud_score": None,
        "fraud_signals": None,
        "fraud_manual_review": None,
        "decision": None,
        "approved_amount": None,
        "message": None,
        "confidence_score": None,
        "line_item_decisions": None,
        "financial_breakdown": None,
        "manual_review_recommended": None,
        "result": None,
    }

    final_state = graph.invoke(initial_state)
    return final_state["result"]
