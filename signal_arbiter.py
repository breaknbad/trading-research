"""
signal_arbiter.py - Weighted voting system for conflicting trade factors.
"""

import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import SUPABASE_URL, SUPABASE_HEADERS, BOT_ID

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
WEIGHTS_FILE = os.path.join(CACHE_DIR, "factor_weights.json")

MIN_WEIGHT = 0.3
MAX_WEIGHT = 2.0
DEFAULT_WEIGHT = 1.0
WEIGHT_STEP = 0.1


def _load_weights():
    os.makedirs(CACHE_DIR, exist_ok=True)
    if os.path.exists(WEIGHTS_FILE):
        try:
            with open(WEIGHTS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_weights(weights):
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(WEIGHTS_FILE, "w") as f:
        json.dump(weights, f, indent=2)


def arbitrate(factor_scores):
    """
    Weighted voting on a list of factor scores.

    Args:
        factor_scores: list of dicts, each with at least:
            - factor_id: str
            - score: float (0-10 scale)
            - label: str (optional, for display)

    Returns: {net_score: float, decision: str, dissenting_factors: list, details: list}
    """
    weights = _load_weights()

    if not factor_scores:
        return {"net_score": 5.0, "decision": "NEUTRAL", "dissenting_factors": [], "details": []}

    weighted_sum = 0.0
    total_weight = 0.0
    details = []

    for f in factor_scores:
        fid = f.get("factor_id", "unknown")
        score = float(f.get("score", 5.0))
        w = weights.get(fid, DEFAULT_WEIGHT)
        weighted_sum += score * w
        total_weight += w
        details.append({"factor_id": fid, "score": score, "weight": round(w, 2), "weighted": round(score * w, 2)})

    net_score = round(weighted_sum / total_weight, 2) if total_weight > 0 else 5.0

    if net_score > 6.0:
        decision = "BUY"
    elif net_score < 4.0:
        decision = "AVOID"
    else:
        decision = "NEUTRAL"

    # Dissenting = factors that disagree with the decision
    dissenting = []
    for d in details:
        if decision == "BUY" and d["score"] < 4.0:
            dissenting.append(d["factor_id"])
        elif decision == "AVOID" and d["score"] > 6.0:
            dissenting.append(d["factor_id"])

    return {
        "net_score": net_score,
        "decision": decision,
        "dissenting_factors": dissenting,
        "details": details,
    }


def update_weights(factor_id, was_correct):
    """
    Adjust a factor's confidence weight based on whether it was correct.

    Args:
        factor_id: str
        was_correct: bool - True increases weight, False decreases
    """
    weights = _load_weights()
    current = weights.get(factor_id, DEFAULT_WEIGHT)

    if was_correct:
        new_weight = min(current + WEIGHT_STEP, MAX_WEIGHT)
    else:
        new_weight = max(current - WEIGHT_STEP, MIN_WEIGHT)

    weights[factor_id] = round(new_weight, 2)
    _save_weights(weights)

    return {"factor_id": factor_id, "old_weight": round(current, 2), "new_weight": round(new_weight, 2)}


def get_weights():
    """Return current factor weights."""
    return _load_weights()


if __name__ == "__main__":
    sample = [
        {"factor_id": "momentum", "score": 7.5},
        {"factor_id": "value", "score": 3.2},
        {"factor_id": "quality", "score": 6.8},
        {"factor_id": "sentiment", "score": 8.0},
    ]
    print(json.dumps(arbitrate(sample), indent=2))
