"""
Agent 3: Policy Checker
Input: parsed documents + claim submission + policy
Output: policy validation result — member valid, waiting period, exclusions, limits, pre-auth
"""
from typing import Dict, Any, List
from models.schemas import ClaimSubmission, TraceStep
from models.policy_loader import (
    get_member, get_category_rules, check_waiting_period,
    check_exclusions, is_network_hospital
)


def extract_diagnosis(parsed_docs: List[Dict]) -> str:
    for doc in parsed_docs:
        parsed = doc.get("parsed", {})
        if parsed.get("diagnosis"):
            return parsed["diagnosis"]
    return ""


def extract_line_items(parsed_docs: List[Dict]) -> List[Dict]:
    for doc in parsed_docs:
        if doc["doc_type"] in ("HOSPITAL_BILL", "PHARMACY_BILL", "DENTAL_BILL"):
            items = doc.get("parsed", {}).get("line_items", [])
            if items:
                return items
    return []


def run_policy_checker(state: Dict[str, Any]) -> Dict[str, Any]:
    claim: ClaimSubmission = state["claim"]
    policy = state["policy"]
    parsed_docs = state.get("parsed_documents", [])
    trace = state.get("trace", [])
    issues = []
    policy_data = {}

    # 1. Member validation
    member = get_member(policy, claim.member_id)
    if not member:
        issues.append(f"Member '{claim.member_id}' not found in policy roster.")
        trace.append(TraceStep(
            agent="PolicyChecker",
            status="FAIL",
            details=f"Member {claim.member_id} not found.",
            data={"issues": issues}
        ))
        return {**state, "policy_issues": issues, "policy_data": policy_data, "policy_passed": False, "trace": trace}

    policy_data["member"] = member

    # 2. Category coverage
    category = claim.claim_category.upper()
    cat_rules = get_category_rules(policy, category)
    if not cat_rules:
        issues.append(f"Claim category '{category}' is not covered under this policy.")
    elif not cat_rules.get("covered", False):
        issues.append(f"Category '{category}' is not active in this policy.")
    else:
        policy_data["category_rules"] = cat_rules

    # 3. Waiting period check
    diagnosis = extract_diagnosis(parsed_docs)
    waiting_result = check_waiting_period(policy, member, diagnosis, claim.treatment_date)
    policy_data["waiting_period"] = waiting_result
    if not waiting_result["passed"]:
        issues.append(
            f"WAITING_PERIOD: {waiting_result['reason']}. "
            f"Eligible from: {waiting_result['eligible_date']}."
        )

    # 4. Exclusions check
    line_items = extract_line_items(parsed_docs)
    exclusion_result = check_exclusions(policy, diagnosis, category, line_items)
    policy_data["exclusions"] = exclusion_result
    if exclusion_result["excluded"]:
        for r in exclusion_result["reasons"]:
            issues.append(f"EXCLUDED_CONDITION: {r}")

    # 5. Pre-authorization check
    pre_auth_required_for = policy.get("pre_authorization", {}).get("required_for", [])
    needs_pre_auth = False

    # Check line items and diagnosis for high-value imaging
    all_text = diagnosis.lower()
    for item in line_items:
        all_text += " " + item.get("description", "").lower()

    high_value_imaging = ["mri", "ct scan", "pet scan"]
    if any(kw in all_text for kw in high_value_imaging) and claim.claimed_amount > 10000:
        needs_pre_auth = True
        issues.append(
            f"PRE_AUTH_REQUIRED: This claim requires pre-authorization "
            f"(MRI/CT/PET scan above ₹10,000). No pre-authorization was provided."
        )
    policy_data["pre_auth_required"] = needs_pre_auth

    # 6. Per-claim limit check — skip for DENTAL/VISION since exclusions may reduce amount first
    per_claim_limit = policy.get("coverage", {}).get("per_claim_limit", None)
    sub_limit = cat_rules.get("sub_limit", float("inf")) if cat_rules else float("inf")

    if per_claim_limit and category not in ("DENTAL", "VISION") and claim.claimed_amount > per_claim_limit:
        issues.append(
            f"PER_CLAIM_EXCEEDED: Claimed amount ₹{claim.claimed_amount:,.0f} exceeds "
            f"per-claim limit of ₹{per_claim_limit:,.0f}."
        )
    policy_data["per_claim_limit"] = per_claim_limit
    policy_data["sub_limit"] = sub_limit

    # 7. Network hospital
    hospital_name = claim.hospital_name
    if not hospital_name:
        for doc in parsed_docs:
            h = doc.get("parsed", {}).get("hospital_name")
            if h:
                hospital_name = h
                break
    network = is_network_hospital(policy, hospital_name or "")
    policy_data["is_network_hospital"] = network
    policy_data["hospital_name"] = hospital_name

    # 8. Annual OPD limit check
    annual_limit = policy.get("coverage", {}).get("annual_opd_limit", float("inf"))
    ytd = claim.ytd_claims_amount or 0
    remaining = annual_limit - ytd
    policy_data["annual_limit"] = annual_limit
    policy_data["ytd_used"] = ytd
    policy_data["remaining_limit"] = remaining

    if ytd + claim.claimed_amount > annual_limit:
        issues.append(
            f"ANNUAL_LIMIT_EXCEEDED: YTD claims ₹{ytd:,.0f} + this claim ₹{claim.claimed_amount:,.0f} "
            f"exceeds annual OPD limit of ₹{annual_limit:,.0f}."
        )

    passed = len(issues) == 0

    trace.append(TraceStep(
        agent="PolicyChecker",
        status="PASS" if passed else "FAIL",
        details="All policy checks passed." if passed else f"{len(issues)} policy issue(s) found.",
        data={"issues": issues, "policy_data": {k: v for k, v in policy_data.items() if k != "member"}}
    ))

    return {
        **state,
        "policy_issues": issues,
        "policy_data": policy_data,
        "policy_passed": passed,
        "diagnosis": diagnosis,
        "line_items": line_items,
        "trace": trace,
    }
