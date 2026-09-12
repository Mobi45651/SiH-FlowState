"""
ml/explain.py
----------------
Turns a feature vector + prediction into the "why" behind a flood-risk
number: a per-factor severity breakdown (for the frontend's bar chart) and
a plain-language sentence.

HONESTY NOTE (read before changing the weighting logic): Random Forest
feature_importances_ describes how much a feature mattered ACROSS ALL
TRAINING DATA on average -- it is not a per-prediction causal attribution.
A feature can have high global importance but be irrelevant to one
specific prediction (e.g. rainfall matters a lot overall, but if it's 0mm
right now, it isn't driving THIS prediction). This module addresses that
by combining two independent things:
  - "severity_percent": how bad THIS factor's CURRENT value is (0-100%),
    independent of the model
  - "model_importance": how much the trained model weighs that factor
    globally (0.0-1.0, sums to ~1.0 across all factors)
and ranks factors by severity x importance, so the factors surfaced first
are both currently bad AND something the model actually relies on. This
is still an approximation, not a rigorous per-prediction attribution
method (like SHAP) -- the disclaimer in the output says so explicitly.

Connects to:
- ml/predict.py -> supplies get_feature_importances() (or None pre-training)
- ml/feature_engineering.py -> the feature vector this operates on
- routes/explain_routes.py -> exposes this over GET /api/explain/<zone_id>
"""

# Maps a display label to the underlying feature column(s) and a function
# that scores how severe the CURRENT value of that factor is, 0.0-1.0.
FACTOR_DEFINITIONS = {
    "Rainfall": {
        "columns": ["rainfall_30min", "rainfall_1h", "rainfall_3h", "rainfall_6h", "rainfall_intensity", "cumulative_rainfall"],
        # 60mm/hr treated as a "severe" reference intensity.
        "severity_fn": lambda fv: min(max(fv.get("rainfall_intensity", 0), fv.get("rainfall_1h", 0)) / 60.0, 1.0),
    },
    "Drainage Load": {
        "columns": ["drainage_utilization"],
        # >100% utilization is already bad; 150%+ treated as maximally severe.
        "severity_fn": lambda fv: min(fv.get("drainage_utilization", 0) / 150.0, 1.0),
    },
    "Blockage": {
        "columns": ["blockage_percentage"],
        "severity_fn": lambda fv: min(fv.get("blockage_percentage", 0) / 100.0, 1.0),
    },
    "Elevation": {
        "columns": ["elevation"],
        # LOWER elevation = higher risk. 350m treated as "safe", 150m as "severe".
        "severity_fn": lambda fv: min(max(350 - fv.get("elevation", 350), 0) / 200.0, 1.0),
    },
    "Slope": {
        "columns": ["slope"],
        # LOWER slope = worse drainage. 5%+ treated as "safe", 0% as "severe".
        "severity_fn": lambda fv: min(max(5.0 - fv.get("slope", 5.0), 0) / 5.0, 1.0),
    },
    "Impervious Surface": {
        "columns": ["impervious_surface"],
        "severity_fn": lambda fv: min(fv.get("impervious_surface", 0) / 100.0, 1.0),
    },
    "History": {
        "columns": ["historical_flood_frequency"],
        "severity_fn": lambda fv: min(fv.get("historical_flood_frequency", 0) / 2.0, 1.0),
    },
}


def build_explanation(feature_vector: dict, flood_probability: float, risk_category: str, feature_importances: dict | None) -> dict:
    """Returns a dict with a ranked `breakdown` list (one entry per
    factor), a plain-language `explanation_text`, and a `disclaimer` that
    is always present -- callers should always surface it next to the
    breakdown, not just on request."""
    equal_weight = round(1.0 / len(FACTOR_DEFINITIONS), 4)

    breakdown = []
    for label, definition in FACTOR_DEFINITIONS.items():
        severity = definition["severity_fn"](feature_vector)
        if feature_importances:
            importance = sum(feature_importances.get(c, 0.0) for c in definition["columns"])
        else:
            importance = equal_weight

        breakdown.append({
            "factor": label,
            "severity_percent": round(severity * 100, 1),
            "model_importance": round(importance, 4),
            "rank_score": round(severity * importance, 4),
        })

    breakdown.sort(key=lambda item: -item["rank_score"])

    top_factors = [b["factor"] for b in breakdown if b["severity_percent"] >= 40][:3]

    if risk_category in ("HIGH", "SEVERE") and top_factors:
        if len(top_factors) == 1:
            factor_phrase = top_factors[0]
        else:
            factor_phrase = ", ".join(top_factors[:-1]) + " and " + top_factors[-1]
        explanation_text = (
            f"Flood risk is {risk_category.lower()} mainly because of {factor_phrase}."
        )
    elif risk_category in ("HIGH", "SEVERE"):
        explanation_text = (
            f"Flood risk is {risk_category.lower()}, driven by a combination of moderately "
            f"elevated factors rather than one dominant cause."
        )
    else:
        explanation_text = f"Flood risk is {risk_category.lower()} -- no single factor is currently severe."

    disclaimer = (
        "This breakdown combines Random Forest feature importance (how much the model "
        "relies on each factor overall) with the current value of each factor. It is an "
        "approximation, not a precise causal explanation of why flooding will or won't occur."
        if feature_importances else
        "No trained ML model was available when this was generated, so factors are weighted "
        "equally rather than by learned feature importance -- run `python -m ml.train` for a "
        "more informative breakdown."
    )

    return {
        "flood_probability": flood_probability,
        "risk_category": risk_category,
        "breakdown": breakdown,
        "explanation_text": explanation_text,
        "disclaimer": disclaimer,
    }
