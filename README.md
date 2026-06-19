# Plum Claims Processing System

A multi-agent AI pipeline for automated health insurance claims processing. Built for the Plum AI Engineer assignment.

## Architecture

```
Claim Submission (FastAPI)
         │
         ▼
[Agent 1] Document Verifier     ─── stops early with specific errors if docs are wrong/missing
         │
         ▼
[Agent 2] Document Parser       ─── extracts structured data using Google Gemini
         │
         ▼
[Agent 3] Policy Checker        ─── validates member, waiting periods, exclusions, limits, pre-auth
         │
         ▼
[Agent 4] Fraud Detector        ─── flags same-day patterns, high-value claims, monthly volume
         │
         ▼
[Agent 5] Decision Engine       ─── APPROVED / PARTIAL / REJECTED / MANUAL_REVIEW + financials
         │
         ▼
[Agent 6] Trace Builder         ─── full audit trail assembled
```

Orchestrated with **LangGraph**. Each agent is a pure function with defined input/output contracts.

## Setup

```bash
# 1. Clone the repo
git clone https://github.com/jenz-barb/plum-claims
cd plum-claims

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set your Gemini API key
export GEMINI_API_KEY=your_key_here
# Windows: set GEMINI_API_KEY=your_key_here

# 5. Start the FastAPI backend
uvicorn main:app --reload --port 8000

# 6. Start the Streamlit UI (new terminal)
streamlit run ui/app.py

# 7. Run all 12 test cases
python tests/run_all_tests.py
```

## Test Cases Coverage

| TC | Test | Expected |
|----|------|----------|
| TC001 | Wrong document type uploaded | PENDING_DOCUMENTS (early stop) |
| TC002 | Unreadable document | PENDING_DOCUMENTS (early stop) |
| TC003 | Documents belong to different patients | PENDING_DOCUMENTS (early stop) |
| TC004 | Clean consultation — full approval | APPROVED ₹1,350 |
| TC005 | Waiting period — diabetes | REJECTED |
| TC006 | Dental partial — cosmetic exclusion | PARTIAL ₹8,000 |
| TC007 | MRI without pre-authorization | REJECTED |
| TC008 | Per-claim limit exceeded | REJECTED |
| TC009 | Fraud — multiple same-day claims | MANUAL_REVIEW |
| TC010 | Network hospital discount + co-pay | APPROVED ₹3,240 |
| TC011 | Component failure graceful degradation | APPROVED (low confidence) |
| TC012 | Excluded treatment (bariatric) | REJECTED |

## Key Design Decisions

- **Network discount applied BEFORE co-pay** (TC010): ₹4,500 × 80% = ₹3,600 → ₹3,600 × 90% = ₹3,240
- **Early exit on document issues** (TC001-TC003): pipeline stops before any claim decision, returns specific actionable error message
- **Graceful degradation** (TC011): component failure is caught, logged in trace, confidence reduced, pipeline continues
- **Line-item level decisions** (TC006): each bill line is individually approved or rejected with reason

## Tech Stack

- **Orchestration**: LangGraph
- **AI**: Google Gemini 1.5 Flash
- **Backend**: FastAPI
- **UI**: Streamlit
- **Data validation**: Pydantic v2

## API

`POST /claims/process` — submit a claim and receive a full decision with trace

See FastAPI docs at `http://localhost:8000/docs`
