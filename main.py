from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from models.schemas import ClaimSubmission, ClaimResult
from graph.claims_graph import process_claim
import traceback

app = FastAPI(
    title="Plum Claims Processing API",
    description="Multi-agent health insurance claims processing system",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"status": "ok", "service": "Plum Claims Processing System"}


@app.post("/claims/process", response_model=ClaimResult)
def process_claim_endpoint(claim: ClaimSubmission):
    try:
        result = process_claim(claim)
        return result
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Pipeline error: {str(e)}")


@app.get("/health")
def health():
    return {"status": "healthy"}
