"""
Automated test runner for all 12 Plum test cases.
Run: python tests/run_all_tests.py
"""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from models.schemas import ClaimSubmission, Document, ClaimsHistoryItem
from graph.claims_graph import process_claim


def load_test_cases():
    with open("data/test_cases.json") as f:
        return json.load(f)["test_cases"]


def build_claim_from_tc(tc: dict) -> ClaimSubmission:
    inp = tc["input"]
    docs = [Document(**d) for d in inp.get("documents", [])]
    history = [ClaimsHistoryItem(**h) for h in inp.get("claims_history", [])]
    return ClaimSubmission(
        member_id=inp["member_id"],
        policy_id=inp["policy_id"],
        claim_category=inp["claim_category"],
        treatment_date=inp["treatment_date"],
        claimed_amount=inp["claimed_amount"],
        hospital_name=inp.get("hospital_name"),
        ytd_claims_amount=inp.get("ytd_claims_amount", 0),
        claims_history=history,
        documents=docs,
        simulate_component_failure=inp.get("simulate_component_failure", False),
    )


def check_result(tc: dict, result) -> dict:
    expected = tc["expected"]
    passed = True
    notes = []

    expected_decision = expected.get("decision")
    if expected_decision:
        if result.decision != expected_decision:
            passed = False
            notes.append(f"Decision mismatch: expected {expected_decision}, got {result.decision}")
        else:
            notes.append(f"✅ Decision: {result.decision}")

    expected_amount = expected.get("approved_amount")
    if expected_amount is not None:
        if result.approved_amount != expected_amount:
            passed = False
            notes.append(f"Amount mismatch: expected ₹{expected_amount}, got ₹{result.approved_amount}")
        else:
            notes.append(f"✅ Amount: ₹{result.approved_amount}")

    # For TC001-TC003 — no decision expected, check early stop
    system_musts = expected.get("system_must", [])
    if expected_decision is None and result.decision in (None, "PENDING_DOCUMENTS"):
        notes.append("✅ System stopped before making claim decision (correct)")
    elif expected_decision is None and result.decision not in (None, "PENDING_DOCUMENTS"):
        passed = False
        notes.append(f"❌ System should have stopped but produced decision: {result.decision}")

    # Rejection reasons
    expected_rejections = expected.get("rejection_reasons", [])
    if expected_rejections:
        for rej in expected_rejections:
            if rej in (result.rejection_reasons or []):
                notes.append(f"✅ Rejection reason present: {rej}")
            else:
                passed = False
                notes.append(f"❌ Missing rejection reason: {rej}")

    # Confidence score
    conf_str = expected.get("confidence_score", "")
    if conf_str and result.confidence_score is not None:
        if "above" in conf_str:
            threshold = float(conf_str.split("above")[1].strip())
            if result.confidence_score >= threshold:
                notes.append(f"✅ Confidence {result.confidence_score:.2f} >= {threshold}")
            else:
                passed = False
                notes.append(f"❌ Confidence {result.confidence_score:.2f} < {threshold}")

    # TC011 specific — component failure handling
    if tc["case_id"] == "TC011":
        if result.component_failures:
            notes.append(f"✅ Component failure recorded: {result.component_failures}")
        else:
            notes.append("⚠️ No component failure recorded")
        if result.manual_review_recommended:
            notes.append("✅ Manual review recommended due to component failure")

    return {"passed": passed, "notes": notes}


def run_all():
    test_cases = load_test_cases()
    results_summary = []
    passed_count = 0

    print("\n" + "="*60)
    print("PLUM CLAIMS SYSTEM — TEST RUNNER")
    print("="*60)

    for tc in test_cases:
        print(f"\n▶ {tc['case_id']}: {tc['case_name']}")
        print(f"  {tc['description']}")

        try:
            claim = build_claim_from_tc(tc)
            result = process_claim(claim)
            check = check_result(tc, result)

            status = "✅ PASS" if check["passed"] else "❌ FAIL"
            print(f"  Result: {status}")
            for note in check["notes"]:
                print(f"    {note}")
            print(f"  Decision: {result.decision} | Amount: ₹{result.approved_amount or 0:,.0f} | Confidence: {result.confidence_score or 'N/A'}")
            print(f"  Message: {result.message[:120]}...")

            if check["passed"]:
                passed_count += 1

            results_summary.append({
                "case_id": tc["case_id"],
                "case_name": tc["case_name"],
                "passed": check["passed"],
                "decision": str(result.decision),
                "approved_amount": result.approved_amount,
                "confidence": result.confidence_score,
                "message": result.message,
                "notes": check["notes"],
                "trace_steps": len(result.trace),
            })

        except Exception as e:
            import traceback
            print(f"  💥 EXCEPTION: {e}")
            traceback.print_exc()
            results_summary.append({
                "case_id": tc["case_id"],
                "case_name": tc["case_name"],
                "passed": False,
                "error": str(e),
            })

    print("\n" + "="*60)
    print(f"SUMMARY: {passed_count}/{len(test_cases)} test cases passed")
    print("="*60)

    # Save eval report data
    with open("eval_results.json", "w") as f:
        json.dump(results_summary, f, indent=2)
    print("\nFull results saved to eval_results.json")

    return results_summary


if __name__ == "__main__":
    run_all()
