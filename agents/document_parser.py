"""
Agent 2: Document Parser
Input: documents from claim
Output: structured extracted data — diagnosis, amounts, patient info, doctor info
Uses Gemini to parse document content. Falls back gracefully on failure.
"""
import os
import json
import google.generativeai as genai
from typing import Dict, Any, List
from models.schemas import ClaimSubmission, TraceStep

genai.configure(api_key=os.environ.get("GEMINI_API_KEY", ""))
model = genai.GenerativeModel("gemini-1.5-flash")


def parse_document_with_gemini(doc_content: Dict, doc_type: str) -> Dict:
    prompt = f"""You are a medical document parser for an Indian health insurance system.
Extract structured information from this {doc_type} document content.

Document content: {json.dumps(doc_content)}

Return ONLY valid JSON with these fields (use null for missing fields):
{{
  "patient_name": "string or null",
  "doctor_name": "string or null", 
  "doctor_registration": "string or null",
  "diagnosis": "string or null",
  "treatment": "string or null",
  "date": "string or null",
  "hospital_name": "string or null",
  "medicines": ["list of strings"],
  "line_items": [{{"description": "string", "amount": number}}],
  "total_amount": number or null,
  "confidence": number between 0 and 1
}}

Return ONLY the JSON object, no markdown, no explanation."""

    try:
        response = model.generate_content(prompt)
        text = response.text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text.strip())
    except Exception as e:
        return {
            "patient_name": None,
            "doctor_name": None,
            "doctor_registration": None,
            "diagnosis": None,
            "treatment": None,
            "date": None,
            "hospital_name": None,
            "medicines": [],
            "line_items": [],
            "total_amount": None,
            "confidence": 0.3,
            "parse_error": str(e)
        }


def run_document_parser(state: Dict[str, Any]) -> Dict[str, Any]:
    claim: ClaimSubmission = state["claim"]
    trace = state.get("trace", [])
    simulate_failure = claim.simulate_component_failure
    component_failures = state.get("component_failures", [])

    if simulate_failure and "DocumentParser" not in str(component_failures):
        # Simulate partial failure — use raw content directly
        component_failures.append("DocumentParser")
        trace.append(TraceStep(
            agent="DocumentParser",
            status="SKIPPED",
            details="Component failure simulated. Using raw document content without AI parsing.",
            data={"simulated_failure": True}
        ))
        # Use raw content as fallback
        parsed_docs = []
        for doc in claim.documents:
            parsed_docs.append({
                "file_id": doc.file_id,
                "doc_type": doc.actual_type,
                "parsed": doc.content or {},
                "confidence": 0.5,
                "fallback": True
            })
        return {**state, "parsed_documents": parsed_docs, "component_failures": component_failures, "trace": trace}

    parsed_docs = []
    parse_errors = []

    for doc in claim.documents:
        if doc.content:
            # Content already structured — use directly, skip Gemini (faster + no API cost)
            parsed_docs.append({
                "file_id": doc.file_id,
                "doc_type": doc.actual_type,
                "parsed": doc.content,
                "confidence": 0.90
            })
        else:
            # No content — flag as unparseable (real scenario with actual files)
            parse_errors.append(doc.file_id)
            parsed_docs.append({
                "file_id": doc.file_id,
                "doc_type": doc.actual_type,
                "parsed": {},
                "confidence": 0.0,
                "error": "No content provided for parsing"
            })

    avg_confidence = (
        sum(d.get("confidence", 0) for d in parsed_docs) / len(parsed_docs)
        if parsed_docs else 0
    )

    trace.append(TraceStep(
        agent="DocumentParser",
        status="PASS" if not parse_errors else "WARNING",
        details=f"Parsed {len(parsed_docs)} document(s). Avg confidence: {avg_confidence:.2f}",
        data={"parsed_count": len(parsed_docs), "errors": parse_errors}
    ))

    return {
        **state,
        "parsed_documents": parsed_docs,
        "parse_confidence": avg_confidence,
        "component_failures": component_failures,
        "trace": trace,
    }
