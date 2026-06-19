"""
Agent 1: Document Verifier
Input: ClaimSubmission
Output: verification result with specific error messages
Errors: WRONG_DOC_TYPE, UNREADABLE_DOC, PATIENT_MISMATCH, MISSING_DOC
"""
from typing import Dict, Any
from models.schemas import ClaimSubmission, TraceStep


REQUIRED_DOCS = {
    "CONSULTATION": {"required": ["PRESCRIPTION", "HOSPITAL_BILL"], "optional": ["LAB_REPORT"]},
    "DIAGNOSTIC": {"required": ["PRESCRIPTION", "LAB_REPORT", "HOSPITAL_BILL"], "optional": []},
    "PHARMACY": {"required": ["PRESCRIPTION", "PHARMACY_BILL"], "optional": []},
    "DENTAL": {"required": ["HOSPITAL_BILL"], "optional": ["PRESCRIPTION", "DENTAL_REPORT"]},
    "VISION": {"required": ["PRESCRIPTION", "HOSPITAL_BILL"], "optional": []},
    "ALTERNATIVE_MEDICINE": {"required": ["PRESCRIPTION", "HOSPITAL_BILL"], "optional": []},
}


def run_document_verifier(state: Dict[str, Any]) -> Dict[str, Any]:
    claim: ClaimSubmission = state["claim"]
    trace = state.get("trace", [])
    errors = []

    docs = claim.documents
    category = claim.claim_category.upper()
    rules = REQUIRED_DOCS.get(category, {"required": [], "optional": []})
    required = rules["required"]

    uploaded_types = [d.actual_type.upper() for d in docs]

    # Check 1: Missing required documents
    for req in required:
        if req not in uploaded_types:
            errors.append({
                "type": "MISSING_DOC",
                "message": f"Missing required document: {req.replace('_', ' ').title()}. "
                           f"For a {category.title()} claim, you must upload: {', '.join(r.replace('_',' ').title() for r in required)}."
            })

    # Check 2: Wrong document type (uploaded something not required)
    if not errors:
        for doc in docs:
            doc_type = doc.actual_type.upper()
            all_allowed = required + rules["optional"]
            if doc_type not in all_allowed:
                errors.append({
                    "type": "WRONG_DOC_TYPE",
                    "message": f"You uploaded a '{doc_type.replace('_',' ').title()}' (file: {doc.file_name or doc.file_id}), "
                               f"but this is not accepted for a {category.title()} claim. "
                               f"Required documents are: {', '.join(r.replace('_',' ').title() for r in required)}."
                })

    # Check 3: Unreadable documents
    for doc in docs:
        quality = (doc.quality or "GOOD").upper()
        if quality == "UNREADABLE":
            errors.append({
                "type": "UNREADABLE_DOC",
                "message": f"The document '{doc.file_name or doc.file_id}' ({doc.actual_type.replace('_',' ').title()}) "
                           f"could not be read — it appears blurry or unclear. "
                           f"Please re-upload a clearer photo or scan of this document."
            })

    # Check 4: Patient name mismatch across documents
    if not errors:
        patient_names = {}
        for doc in docs:
            name = None
            if doc.patient_name_on_doc:
                name = doc.patient_name_on_doc
            elif doc.content and doc.content.get("patient_name"):
                name = doc.content["patient_name"]
            if name:
                patient_names[doc.file_id] = {"name": name, "doc_type": doc.actual_type, "file": doc.file_name or doc.file_id}

        if len(patient_names) >= 2:
            names_list = list(patient_names.values())
            unique_names = set(n["name"].lower().strip() for n in names_list)
            if len(unique_names) > 1:
                name_details = ", ".join(
                    f"{v['doc_type'].replace('_',' ').title()} shows '{v['name']}'" 
                    for v in names_list
                )
                errors.append({
                    "type": "PATIENT_MISMATCH",
                    "message": f"Documents appear to belong to different patients: {name_details}. "
                               f"All documents in a single claim must be for the same patient."
                })

    passed = len(errors) == 0

    trace.append(TraceStep(
        agent="DocumentVerifier",
        status="PASS" if passed else "FAIL",
        details="All document checks passed." if passed else f"{len(errors)} document issue(s) found.",
        data={"errors": errors, "uploaded_types": uploaded_types, "required": required}
    ))

    return {
        **state,
        "doc_verification_passed": passed,
        "doc_errors": errors,
        "trace": trace,
    }
