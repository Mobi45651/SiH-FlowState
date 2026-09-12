"""
ml/predict.py
----------------
Loads the trained Random Forest (once, lazily, cached in-process) and
exposes prediction + feature-importance functions.

CRITICAL DESIGN RULE: nothing in this file ever raises or crashes the app
because a model hasn't been trained yet. Every public function returns
None on a missing/unreadable model instead. This is what lets
flood_engine/risk.py's blend_with_ml_prediction(rule_based_prob, ml_prob)
degrade gracefully to rule-based-only scoring -- exactly as designed back
in Phase 4, now actually wired up.

Connects to:
- ml/feature_engineering.py  -> FEATURE_COLUMNS, feature_vector_to_row()
- ml/train.py                -> produces exactly the files loaded here
- services/nowcast_engine.py -> calls predict_flood_probability() per step
- routes/explain_routes.py   -> calls get_feature_importances()
"""

import json
import logging
from pathlib import Path

import joblib

from ml.feature_engineering import FEATURE_COLUMNS, feature_vector_to_row

logger = logging.getLogger(__name__)

MODEL_DIR = Path(__file__).resolve().parent / "saved_models"
MODEL_PATH = MODEL_DIR / "flood_rf_model.pkl"
METADATA_PATH = MODEL_DIR / "model_metadata.json"

_model_cache = None
_metadata_cache = None
_load_attempted = False


def _load_model():
    global _model_cache, _metadata_cache, _load_attempted
    if _load_attempted:
        return _model_cache
    _load_attempted = True

    if not MODEL_PATH.exists():
        logger.warning(
            "No trained model at %s -- run `python -m ml.train` first. "
            "Predictions will fall back to rule-based scoring only.", MODEL_PATH
        )
        return None

    try:
        _model_cache = joblib.load(MODEL_PATH)
        if METADATA_PATH.exists():
            with open(METADATA_PATH) as f:
                _metadata_cache = json.load(f)
        logger.info("Loaded flood-risk Random Forest model from %s", MODEL_PATH)
    except Exception as exc:  # noqa: BLE001 -- any load failure must degrade, not crash
        logger.error("Failed to load flood-risk model (%s) -- falling back to rule-based scoring.", exc)
        _model_cache = None

    return _model_cache


def is_model_available() -> bool:
    return _load_model() is not None


def get_model_metadata() -> dict | None:
    _load_model()
    return _metadata_cache


def predict_flood_probability(feature_vector: dict) -> float | None:
    """feature_vector must contain every key in FEATURE_COLUMNS (build one
    with ml.feature_engineering.build_feature_vector()). Returns None if no
    trained model is available -- callers must treat None as "use
    rule-based score only", never as a probability of 0.0."""
    model = _load_model()
    if model is None:
        return None

    row = feature_vector_to_row(feature_vector)
    # Wrapped in a DataFrame with FEATURE_COLUMNS as column names (matching
    # how the model was trained in ml/train.py) so scikit-learn doesn't
    # emit a "X does not have valid feature names" warning on every call.
    import pandas as pd
    X = pd.DataFrame([row], columns=FEATURE_COLUMNS)
    # predict_proba returns [[P(class=0="not flooded"), P(class=1="flooded")]]
    probability = model.predict_proba(X)[0][1]
    return round(float(probability), 4)


def get_feature_importances() -> dict | None:
    """Global (not per-prediction) feature importances from the trained
    model. ml/explain.py combines this with the CURRENT feature values to
    build a per-prediction breakdown -- see that file for why importance
    alone isn't the same as "why this specific prediction came out this
    way"."""
    model = _load_model()
    if model is None:
        return None
    return {col: round(float(imp), 4) for col, imp in zip(FEATURE_COLUMNS, model.feature_importances_)}


def reset_cache_for_testing() -> None:
    """Test-only: forces the next call to reload from disk. Used after a
    test trains a fresh model into a temp MODEL_PATH."""
    global _model_cache, _metadata_cache, _load_attempted
    _model_cache = None
    _metadata_cache = None
    _load_attempted = False
