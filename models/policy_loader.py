import json
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime, timedelta


def load_policy(policy_path: str = "data/policy_terms.json") -> Dict[str, Any]:
    path = Path(policy_path)
    if not path.exists():
        path = Path(__file__).parent.parent / "data" / "policy_terms.json"
    with open(path) as f:
        return json.load(f)


def get_member(policy: Dict, member_id: str) -> Optional[Dict]:
    for m in policy.get("members", []):
        if m["member_id"] == member_id:
            return m
    return None


def get_category_rules(policy: Dict, category: str) -> Optional[Dict]:
    return policy.get("opd_categories", {}).get(category.lower(), None)


def is_network_hospital(policy: Dict, hospital_name: str) -> bool:
    if not hospital_name:
        return False
    network = [h.lower() for h in policy.get("network_hospitals", [])]
    return any(h in hospital_name.lower() for h in network)


def check_waiting_period(policy: Dict, member: Dict, diagnosis: str, treatment_date: str) -> Dict:
    """Returns {'passed': bool, 'reason': str, 'eligible_date': str}"""
    join_date = datetime.strptime(member["join_date"], "%Y-%m-%d")
    treat_date = datetime.strptime(treatment_date, "%Y-%m-%d")
    waiting = policy.get("waiting_periods", {})

    # Initial waiting period
    initial_days = waiting.get("initial_waiting_period_days", 30)
    initial_eligible = join_date + timedelta(days=initial_days)
    if treat_date < initial_eligible:
        return {
            "passed": False,
            "reason": f"Initial waiting period of {initial_days} days not completed",
            "eligible_date": initial_eligible.strftime("%Y-%m-%d")
        }

    # Condition-specific waiting periods
    diagnosis_lower = diagnosis.lower() if diagnosis else ""
    specific = waiting.get("specific_conditions", {})

    condition_map = {
        "diabetes": ["diabetes", "t2dm", "type 2 diabetes", "type2 diabetes"],
        "hypertension": ["hypertension", "htn", "high blood pressure"],
        "thyroid_disorders": ["thyroid", "hypothyroidism", "hyperthyroidism"],
        "joint_replacement": ["joint replacement"],
        "maternity": ["maternity", "pregnancy", "delivery"],
        "mental_health": ["mental health", "depression", "anxiety", "psychiatric"],
        "obesity_treatment": ["obesity", "bariatric", "weight loss", "bmi"],
        "hernia": ["hernia repair", "hernioplasty", "herniorrhaphy"],
        "cataract": ["cataract"],
    }

    for condition_key, keywords in condition_map.items():
        if any(kw in diagnosis_lower for kw in keywords):
            days = specific.get(condition_key, 0)
            if days > 0:
                eligible = join_date + timedelta(days=days)
                if treat_date < eligible:
                    return {
                        "passed": False,
                        "reason": f"Waiting period of {days} days for {condition_key.replace('_', ' ')} not completed. Member joined {member['join_date']}.",
                        "eligible_date": eligible.strftime("%Y-%m-%d")
                    }

    return {"passed": True, "reason": "Waiting period cleared", "eligible_date": None}


def check_exclusions(policy: Dict, diagnosis: str, claim_category: str, line_items: list) -> Dict:
    """Returns {'excluded': bool, 'reasons': list}"""
    reasons = []
    diagnosis_lower = (diagnosis or "").lower()
    exclusions = policy.get("exclusions", {})

    # Global exclusions
    exclusion_keywords = {
        "obesity": ["obesity", "bariatric", "weight loss program"],
        "cosmetic": ["cosmetic", "aesthetic", "whitening", "bleaching", "veneer", "lasik"],
        "experimental": ["experimental"],
        "infertility": ["infertility", "ivf", "assisted reproduction"],
        "substance abuse": ["substance abuse", "alcohol", "drug abuse"],
    }

    for excl_type, keywords in exclusion_keywords.items():
        if any(kw in diagnosis_lower for kw in keywords):
            reasons.append(f"Diagnosis falls under excluded condition: {excl_type}")

    # NOTE: Line-item level dental/vision exclusions are handled in DecisionEngine (PARTIAL)
    # Do NOT add them here as hard rejections — they result in PARTIAL approval, not REJECTED

    return {"excluded": len(reasons) > 0, "reasons": reasons}
