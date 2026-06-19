import streamlit as st
import json
import requests
from pathlib import Path

API_URL = "http://localhost:8000"

st.set_page_config(page_title="Plum Claims Processing", page_icon="🏥", layout="wide")

st.title("🏥 Plum Health Insurance Claims Processing")
st.caption("Multi-agent AI pipeline for intelligent claim decisions")

# Load test cases
@st.cache_data
def load_test_cases():
    p = Path("data/test_cases.json")
    if p.exists():
        with open(p) as f:
            return json.load(f)["test_cases"]
    return []

test_cases = load_test_cases()

# Sidebar — quick load test case
with st.sidebar:
    st.header("⚡ Quick Test")
    tc_options = {f"{tc['case_id']}: {tc['case_name']}": tc for tc in test_cases}
    selected_tc = st.selectbox("Load a test case", ["-- Manual Entry --"] + list(tc_options.keys()))

    if selected_tc != "-- Manual Entry --":
        tc = tc_options[selected_tc]
        st.info(tc.get("description", ""))
        expected = tc.get("expected", {})
        if expected.get("decision"):
            st.success(f"Expected: **{expected['decision']}**" +
                      (f" | ₹{expected.get('approved_amount', '')} " if expected.get('approved_amount') else ""))

tab1, tab2 = st.tabs(["Submit Claim", "View Result"])

with tab1:
    col1, col2 = st.columns(2)

    # Pre-fill from test case
    prefill = {}
    if selected_tc != "-- Manual Entry --":
        tc_input = tc_options[selected_tc]["input"]
        prefill = tc_input

    with col1:
        st.subheader("Claim Details")
        member_id = st.text_input("Member ID", value=prefill.get("member_id", "EMP001"))
        policy_id = st.text_input("Policy ID", value=prefill.get("policy_id", "PLUM_GHI_2024"))
        claim_category = st.selectbox(
            "Claim Category",
            ["CONSULTATION", "DIAGNOSTIC", "PHARMACY", "DENTAL", "VISION", "ALTERNATIVE_MEDICINE"],
            index=["CONSULTATION", "DIAGNOSTIC", "PHARMACY", "DENTAL", "VISION", "ALTERNATIVE_MEDICINE"].index(
                prefill.get("claim_category", "CONSULTATION")
            ) if prefill.get("claim_category") in ["CONSULTATION", "DIAGNOSTIC", "PHARMACY", "DENTAL", "VISION", "ALTERNATIVE_MEDICINE"] else 0
        )
        treatment_date = st.text_input("Treatment Date (YYYY-MM-DD)", value=prefill.get("treatment_date", "2024-11-01"))
        claimed_amount = st.number_input("Claimed Amount (₹)", value=float(prefill.get("claimed_amount", 1500)), min_value=0.0)
        hospital_name = st.text_input("Hospital Name (optional)", value=prefill.get("hospital_name", ""))
        ytd_amount = st.number_input("YTD Claims Amount (₹)", value=float(prefill.get("ytd_claims_amount", 0)))
        simulate_failure = st.checkbox("Simulate Component Failure (TC011)", value=prefill.get("simulate_component_failure", False))

    with col2:
        st.subheader("Documents")
        if prefill.get("documents"):
            docs_json = json.dumps(prefill["documents"], indent=2)
        else:
            docs_json = json.dumps([
                {"file_id": "F001", "file_name": "prescription.jpg", "actual_type": "PRESCRIPTION",
                 "content": {"doctor_name": "Dr. Example", "patient_name": "Test Patient", "diagnosis": "Viral Fever"}},
                {"file_id": "F002", "file_name": "bill.jpg", "actual_type": "HOSPITAL_BILL",
                 "content": {"patient_name": "Test Patient", "total": 1500,
                              "line_items": [{"description": "Consultation Fee", "amount": 1500}]}}
            ], indent=2)

        docs_input = st.text_area("Documents (JSON)", value=docs_json, height=300)

        st.subheader("Claims History (optional)")
        history_default = json.dumps(prefill.get("claims_history", []), indent=2)
        history_input = st.text_area("Claims History (JSON)", value=history_default, height=100)

    if st.button("🚀 Process Claim", type="primary", use_container_width=True):
        try:
            documents = json.loads(docs_input)
            history = json.loads(history_input) if history_input.strip() else []

            payload = {
                "member_id": member_id,
                "policy_id": policy_id,
                "claim_category": claim_category,
                "treatment_date": treatment_date,
                "claimed_amount": claimed_amount,
                "hospital_name": hospital_name or None,
                "ytd_claims_amount": ytd_amount,
                "documents": documents,
                "claims_history": history,
                "simulate_component_failure": simulate_failure
            }

            with st.spinner("Processing claim through AI pipeline..."):
                resp = requests.post(f"{API_URL}/claims/process", json=payload, timeout=60)

            if resp.status_code == 200:
                result = resp.json()
                st.session_state["last_result"] = result
                st.success("Claim processed! View results in the 'View Result' tab.")
            else:
                st.error(f"API Error {resp.status_code}: {resp.text}")

        except json.JSONDecodeError as e:
            st.error(f"Invalid JSON in documents/history: {e}")
        except requests.exceptions.ConnectionError:
            st.error("Cannot connect to API. Make sure FastAPI is running on port 8000.")
        except Exception as e:
            st.error(f"Error: {e}")

with tab2:
    result = st.session_state.get("last_result")

    if not result:
        st.info("Process a claim first to see results here.")
    else:
        # Decision header
        decision = result.get("decision", "UNKNOWN")
        decision_colors = {
            "APPROVED": "🟢",
            "PARTIAL": "🟡",
            "REJECTED": "🔴",
            "MANUAL_REVIEW": "🔵",
            "PENDING_DOCUMENTS": "🟠"
        }
        icon = decision_colors.get(decision, "⚪")

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Decision", f"{icon} {decision}")
        col2.metric("Claimed", f"₹{result.get('claimed_amount', 0):,.0f}")
        col3.metric("Approved", f"₹{result.get('approved_amount') or 0:,.0f}")
        col4.metric("Confidence", f"{result.get('confidence_score') or 0:.0%}" if result.get('confidence_score') else "N/A")

        st.info(f"**{result.get('message', '')}**")

        if result.get("claim_id"):
            st.caption(f"Claim ID: {result['claim_id']} | Member: {result['member_id']}")

        # Alerts
        if result.get("component_failures"):
            st.warning(f"⚠️ Component failures: {', '.join(result['component_failures'])}. Manual review recommended.")

        if result.get("fraud_signals"):
            st.error("🚨 Fraud signals detected:")
            for sig in result["fraud_signals"]:
                st.write(f"• {sig}")

        # Financial breakdown
        if result.get("financial_breakdown"):
            st.subheader("💰 Financial Breakdown")
            fb = result["financial_breakdown"]
            breakdown_rows = []
            if "base_amount" in fb:
                breakdown_rows.append(("Base Amount", f"₹{fb['base_amount']:,.2f}"))
            if "sub_limit_applied" in fb:
                breakdown_rows.append(("Sub-limit Cap Applied", f"₹{fb['sub_limit_applied']:,.2f}"))
            if "network_discount_percent" in fb:
                breakdown_rows.append((f"Network Discount ({fb['network_discount_percent']}%)",
                                        f"-₹{fb['network_discount_amount']:,.2f}"))
            if "after_network_discount" in fb:
                breakdown_rows.append(("After Network Discount", f"₹{fb['after_network_discount']:,.2f}"))
            if "copay_percent" in fb:
                breakdown_rows.append((f"Co-pay ({fb['copay_percent']}%)", f"-₹{fb['copay_amount']:,.2f}"))
            if "final_approved_amount" in fb:
                breakdown_rows.append(("**Final Approved Amount**", f"**₹{fb['final_approved_amount']:,.2f}**"))

            for label, value in breakdown_rows:
                col1, col2 = st.columns([3, 1])
                col1.write(label)
                col2.write(value)

        # Line item decisions
        if result.get("line_item_decisions"):
            st.subheader("📋 Line Item Decisions")
            for item in result["line_item_decisions"]:
                status_icon = "✅" if item["status"] == "APPROVED" else "❌"
                st.write(f"{status_icon} **{item['description']}** — ₹{item['amount']:,.0f} — {item.get('reason', '')}")

        # Audit trace
        st.subheader("🔍 Full Audit Trace")
        for step in result.get("trace", []):
            status_icons = {"PASS": "✅", "FAIL": "❌", "WARNING": "⚠️", "SKIPPED": "⏭️"}
            icon = status_icons.get(step.get("status", ""), "•")
            with st.expander(f"{icon} {step.get('agent', '')} — {step.get('details', '')}"):
                if step.get("data"):
                    st.json(step["data"])

        # Raw JSON
        with st.expander("📄 Raw JSON Response"):
            st.json(result)
