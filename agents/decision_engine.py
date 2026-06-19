"""
Agent 5: Decision Engine
Input: all prior agent outputs
Output: APPROVED / PARTIAL / REJECTED / MANUAL_REVIEW + approved_amount + financial breakdown
Critical: network discount applied BEFORE co-pay
"""
from typing import Dict, Any, List
from models.schemas import ClaimSubmission, ClaimDecision, TraceStep, LineItemDecision


def calculate_approved_amount(
    claimed_amount: float,
    cat_rules: Dict,
    is_network: bool,
    line_items: List[Dict],
    claim_category: str,
    policy: Dict
) -> Dict:
    """
    Financial calculation order:
    1. Remove excluded line items
    2. Apply sub-limit cap
    3. Apply network discount (if network hospital)
    4. Apply co-pay deduction
    """
    breakdown = {}
    line_item_decisions = []

    # Step 1: Line-item level filtering (dental/vision)
    approved_items = []
    rejected_items = []

    if line_items and claim_category in ("DENTAL", "VISION"):
        exclusions = policy.get("exclusions", {})
        dental_excl = [e.lower() for e in exclusions.get("dental_exclusions", [])]
        vision_excl = [e.lower() for e in exclusions.get("vision_exclusions", [])]
        excluded_list = dental_excl + vision_excl

        for item in line_items:
            desc_lower = item.get("description", "").lower()
            amt = item.get("amount", 0)
            if any(excl in desc_lower for excl in excluded_list):
                rejected_items.append(item)
                line_item_decisions.append(LineItemDecision(
                    description=item["description"],
                    amount=amt,
                    status="REJECTED",
                    reason="Excluded procedure (cosmetic/non-covered)"
                ))
            else:
                approved_items.append(item)
                line_item_decisions.append(LineItemDecision(
                    description=item["description"],
                    amount=amt,
                    status="APPROVED",
                    reason="Covered procedure"
                ))
        base_amount = sum(i.get("amount", 0) for i in approved_items)
    else:
        base_amount = claimed_amount

    breakdown["base_amount"] = base_amount

    # Step 2: Per-claim limit cap (from coverage, not category sub_limit)
    # sub_limit is the annual category budget, not a per-claim ceiling
    # We only cap at claimed_amount itself
    breakdown["after_sublimit"] = base_amount

    # Step 3: Network discount (BEFORE co-pay)
    network_discount = cat_rules.get("network_discount_percent", 0) if is_network else 0
    if network_discount > 0:
        discount_amount = base_amount * (network_discount / 100)
        base_amount = base_amount - discount_amount
        breakdown["network_discount_percent"] = network_discount
        breakdown["network_discount_amount"] = round(discount_amount, 2)

    breakdown["after_network_discount"] = round(base_amount, 2)

    # Step 4: Co-pay deduction (AFTER network discount)
    copay_percent = cat_rules.get("copay_percent", 0)
    copay_amount = 0
    if copay_percent > 0:
        copay_amount = base_amount * (copay_percent / 100)
        base_amount = base_amount - copay_amount
        breakdown["copay_percent"] = copay_percent
        breakdown["copay_amount"] = round(copay_amount, 2)

    breakdown["final_approved_amount"] = round(base_amount, 2)

    return {
        "approved_amount": round(base_amount, 2),
        "breakdown": breakdown,
        "line_item_decisions": line_item_decisions,
        "has_partial": len(rejected_items) > 0
    }


def run_decision_engine(state: Dict[str, Any]) -> Dict[str, Any]:
    claim: ClaimSubmission = state["claim"]
    policy = state["policy"]
    trace = state.get("trace", [])
    policy_issues = state.get("policy_issues", [])
    fraud_manual_review = state.get("fraud_manual_review", False)
    fraud_signals = state.get("fraud_signals", [])
    policy_data = state.get("policy_data", {})
    component_failures = state.get("component_failures", [])
    line_items = state.get("line_items", [])

    cat_rules = policy_data.get("category_rules", {})
    is_network = policy_data.get("is_network_hospital", False)

    # Separate hard rejections vs partial issues
    hard_rejections = [i for i in policy_issues if any(
        kw in i for kw in ["WAITING_PERIOD", "EXCLUDED_CONDITION", "PER_CLAIM_EXCEEDED",
                            "ANNUAL_LIMIT_EXCEEDED", "PRE_AUTH_REQUIRED", "not found", "not covered"]
    )]

    # Dental/vision may have line-item exclusions but still be PARTIAL
    line_level_exclusions = []
    if state.get("policy_data", {}).get("exclusions", {}).get("reasons"):
        for r in state["policy_data"]["exclusions"]["reasons"]:
            if "Line item" in r:
                line_level_exclusions.append(r)

    # Decision logic
    if fraud_manual_review:
        decision = ClaimDecision.MANUAL_REVIEW
        approved_amount = None
        message = (
            f"This claim has been flagged for manual review due to unusual patterns. "
            f"Signals: {'; '.join(fraud_signals)}"
        )
        financial = {}
        lid = []

    elif hard_rejections:
        decision = ClaimDecision.REJECTED
        approved_amount = 0
        message = "Claim rejected. Reasons: " + " | ".join(hard_rejections)
        financial = {}
        lid = []

    elif not cat_rules:
        decision = ClaimDecision.REJECTED
        approved_amount = 0
        message = f"Claim category '{claim.claim_category}' is not covered under this policy."
        financial = {}
        lid = []

    else:
        # Calculate financials
        calc = calculate_approved_amount(
            claimed_amount=claim.claimed_amount,
            cat_rules=cat_rules,
            is_network=is_network,
            line_items=line_items,
            claim_category=claim.claim_category.upper(),
            policy=policy
        )

        approved_amount = calc["approved_amount"]
        financial = calc["breakdown"]
        lid = calc["line_item_decisions"]

        if calc["has_partial"]:
            decision = ClaimDecision.PARTIAL
            message = (
                f"Claim partially approved. Some line items were excluded. "
                f"Approved: ₹{approved_amount:,.0f} of ₹{claim.claimed_amount:,.0f} claimed."
            )
        elif approved_amount < claim.claimed_amount:
            decision = ClaimDecision.APPROVED
            message = (
                f"Claim approved. Amount adjusted after policy deductions. "
                f"Approved: ₹{approved_amount:,.0f}."
            )
        else:
            decision = ClaimDecision.APPROVED
            message = f"Claim approved. Approved amount: ₹{approved_amount:,.0f}."

    # Confidence score
    base_confidence = 0.95
    if component_failures:
        base_confidence -= 0.25 * len(component_failures)
    if fraud_signals:
        base_confidence -= 0.1
    if (state.get("parse_confidence") or 1.0) < 0.7:
        base_confidence -= 0.1
    confidence = max(0.3, min(1.0, base_confidence))

    manual_review_recommended = bool(component_failures) or fraud_manual_review

    trace.append(TraceStep(
        agent="DecisionEngine",
        status="PASS",
        details=f"Decision: {decision}. Approved: ₹{approved_amount or 0:,.0f}. Confidence: {confidence:.2f}",
        data={
            "decision": decision,
            "approved_amount": approved_amount,
            "financial_breakdown": financial,
            "confidence": confidence,
            "component_failures_impact": len(component_failures) > 0
        }
    ))

    return {
        **state,
        "decision": decision,
        "approved_amount": approved_amount,
        "message": message,
        "confidence_score": round(confidence, 2),
        "line_item_decisions": lid,
        "financial_breakdown": financial,
        "manual_review_recommended": manual_review_recommended,
        "trace": trace,
    }
