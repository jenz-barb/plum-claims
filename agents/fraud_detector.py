"""
Agent 4: Fraud Detector
Input: claim + claims history
Output: fraud_score, fraud_signals, recommendation
Routes to MANUAL_REVIEW if fraud_score >= threshold
"""
from typing import Dict, Any, List
from models.schemas import ClaimSubmission, TraceStep


def run_fraud_detector(state: Dict[str, Any]) -> Dict[str, Any]:
    claim: ClaimSubmission = state["claim"]
    policy = state["policy"]
    trace = state.get("trace", [])

    thresholds = policy.get("fraud_thresholds", {})
    same_day_limit = thresholds.get("same_day_claims_limit", 2)
    monthly_limit = thresholds.get("monthly_claims_limit", 6)
    high_value_threshold = thresholds.get("high_value_claim_threshold", 25000)
    fraud_score_threshold = thresholds.get("fraud_score_manual_review_threshold", 0.80)

    signals: List[str] = []
    fraud_score = 0.0

    history = claim.claims_history or []

    # Signal 1: Same-day claims
    same_day = [h for h in history if h.date == claim.treatment_date]
    if len(same_day) >= same_day_limit:
        signals.append(
            f"SAME_DAY_CLAIMS: Member has {len(same_day)} existing claims on {claim.treatment_date} "
            f"(limit: {same_day_limit}). Providers: {', '.join(h.provider or 'Unknown' for h in same_day)}."
        )
        fraud_score += 0.5

    # Signal 2: Multiple providers same day
    providers = set(h.provider for h in same_day if h.provider)
    if len(providers) > 1:
        signals.append(
            f"MULTIPLE_PROVIDERS_SAME_DAY: Claims from {len(providers)} different providers on the same day: "
            f"{', '.join(providers)}."
        )
        fraud_score += 0.2

    # Signal 3: High-value claim
    if claim.claimed_amount > high_value_threshold:
        signals.append(
            f"HIGH_VALUE_CLAIM: Claimed amount ₹{claim.claimed_amount:,.0f} exceeds "
            f"high-value threshold of ₹{high_value_threshold:,.0f}."
        )
        fraud_score += 0.15

    # Signal 4: Monthly claim volume
    treat_month = claim.treatment_date[:7]  # YYYY-MM
    monthly_claims = [h for h in history if h.date.startswith(treat_month)]
    if len(monthly_claims) >= monthly_limit:
        signals.append(
            f"HIGH_MONTHLY_VOLUME: {len(monthly_claims)} claims this month (limit: {monthly_limit})."
        )
        fraud_score += 0.2

    fraud_score = min(fraud_score, 1.0)
    requires_manual_review = fraud_score >= fraud_score_threshold or len(signals) >= 2

    trace.append(TraceStep(
        agent="FraudDetector",
        status="WARNING" if signals else "PASS",
        details=f"Fraud score: {fraud_score:.2f}. {len(signals)} signal(s) detected." if signals
                else "No fraud signals detected.",
        data={"fraud_score": fraud_score, "signals": signals, "manual_review": requires_manual_review}
    ))

    return {
        **state,
        "fraud_score": fraud_score,
        "fraud_signals": signals,
        "fraud_manual_review": requires_manual_review,
        "trace": trace,
    }
