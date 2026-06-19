"""
Agent 6: Trace Builder
Input: full state after all agents
Output: final ClaimResult with complete audit trail
"""
import uuid
from typing import Dict, Any
from models.schemas import ClaimResult, ClaimDecision, TraceStep


def run_trace_builder(state: Dict[str, Any]) -> Dict[str, Any]:
    claim = state["claim"]
    trace = state.get("trace", [])
    component_failures = state.get("component_failures", [])

    # Add final summary trace step
    trace.append(TraceStep(
        agent="TraceBuilder",
        status="PASS",
        details="Full audit trail assembled.",
        data={
            "total_agents_run": len(trace),
            "component_failures": component_failures,
            "final_decision": state.get("decision"),
        }
    ))

    result = ClaimResult(
        claim_id=f"CLM-{uuid.uuid4().hex[:8].upper()}",
        member_id=claim.member_id,
        claim_category=claim.claim_category,
        claimed_amount=claim.claimed_amount,
        decision=state.get("decision"),
        approved_amount=state.get("approved_amount"),
        rejection_reasons=_extract_rejection_reasons(state),
        confidence_score=state.get("confidence_score"),
        message=state.get("message", ""),
        line_item_decisions=state.get("line_item_decisions", []),
        trace=trace,
        component_failures=component_failures,
        manual_review_recommended=state.get("manual_review_recommended", False),
        fraud_signals=state.get("fraud_signals", []),
        financial_breakdown=state.get("financial_breakdown", {}),
    )

    return {**state, "result": result}


def _extract_rejection_reasons(state: Dict) -> list:
    reasons = []
    for issue in state.get("policy_issues", []):
        if "WAITING_PERIOD" in issue:
            reasons.append("WAITING_PERIOD")
        elif "EXCLUDED_CONDITION" in issue:
            reasons.append("EXCLUDED_CONDITION")
        elif "PER_CLAIM_EXCEEDED" in issue:
            reasons.append("PER_CLAIM_EXCEEDED")
        elif "ANNUAL_LIMIT_EXCEEDED" in issue:
            reasons.append("ANNUAL_LIMIT_EXCEEDED")
        if "PRE_AUTH_REQUIRED" in issue:
            reasons.append("PRE_AUTH_MISSING")
    for signal in state.get("fraud_signals", []):
        if "SAME_DAY" in signal:
            reasons.append("FRAUD_SAME_DAY_CLAIMS")
    return list(set(reasons))
