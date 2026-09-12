"""
tests/test_ml.py
-------------------
None of this needs Flask or the database -- feature_engineering.py,
train.py, predict.py, and explain.py are all pure Python + pandas/sklearn.
Uses pytest's built-in tmp_path/monkeypatch fixtures to redirect the model
file paths so these tests never touch (or depend on) the real trained
model in ml/saved_models/.

Run with: pytest backend/tests/test_ml.py -v
"""

import pandas as pd
import pytest

from ml.feature_engineering import (
    FEATURE_COLUMNS,
    build_feature_vector,
    feature_vector_to_row,
    encode_historical_frequency,
)
from ml.explain import build_explanation, FACTOR_DEFINITIONS


def make_feature_vector(**overrides):
    base = dict(
        rainfall_30min=5, rainfall_1h=5, rainfall_3h=10, rainfall_6h=15,
        rainfall_intensity=6, cumulative_rainfall=15,
        runoff=1.0, drainage_capacity=5.0, drainage_utilization=20,
        blockage_percentage=10, elevation=250, slope=3,
        impervious_surface=60, historical_flood_frequency="LOW",
    )
    base.update(overrides)
    return build_feature_vector(**base)


def test_encode_historical_frequency():
    assert encode_historical_frequency("LOW") == 0
    assert encode_historical_frequency("Medium") == 1
    assert encode_historical_frequency("HIGH") == 2
    assert encode_historical_frequency("") == 0
    assert encode_historical_frequency("unknown") == 0


def test_build_feature_vector_encodes_string_frequency():
    fv = make_feature_vector(historical_flood_frequency="HIGH")
    assert fv["historical_flood_frequency"] == 2


def test_feature_vector_to_row_matches_column_order():
    fv = make_feature_vector()
    row = feature_vector_to_row(fv)
    assert len(row) == len(FEATURE_COLUMNS)
    assert row == [fv[c] for c in FEATURE_COLUMNS]


def test_feature_vector_to_row_rejects_missing_columns():
    fv = make_feature_vector()
    del fv["elevation"]
    with pytest.raises(ValueError):
        feature_vector_to_row(fv)


def test_generate_synthetic_training_dataset_shape():
    from utils.demo_data_generator import generate_synthetic_training_dataset
    df = generate_synthetic_training_dataset(n_samples=100)
    assert len(df) == 100
    assert set(FEATURE_COLUMNS + ["flooded"]).issubset(df.columns)
    assert set(df["flooded"].unique()).issubset({0, 1})


def test_train_and_predict_roundtrip(tmp_path, monkeypatch):
    """Trains a small model into a temp directory and confirms predict.py
    can load and use it -- without touching the real ml/saved_models/."""
    from ml import train as train_module
    from ml import predict as predict_module

    tmp_model_dir = tmp_path / "saved_models"
    tmp_model_dir.mkdir()
    monkeypatch.setattr(train_module, "MODEL_DIR", tmp_model_dir)
    monkeypatch.setattr(train_module, "MODEL_PATH", tmp_model_dir / "flood_rf_model.pkl")
    monkeypatch.setattr(train_module, "METADATA_PATH", tmp_model_dir / "model_metadata.json")
    monkeypatch.setattr(predict_module, "MODEL_PATH", tmp_model_dir / "flood_rf_model.pkl")
    monkeypatch.setattr(predict_module, "METADATA_PATH", tmp_model_dir / "model_metadata.json")

    from utils.demo_data_generator import generate_synthetic_training_dataset
    small_csv = tmp_path / "tiny_dataset.csv"
    generate_synthetic_training_dataset(n_samples=200).to_csv(small_csv, index=False)

    metadata = train_module.train_model(csv_path=str(small_csv))
    assert metadata["is_synthetic_dataset"] is True
    assert metadata["sample_count"] == 200
    assert 0.0 <= metadata["test_accuracy"] <= 1.0

    predict_module.reset_cache_for_testing()
    assert predict_module.is_model_available() is True

    low_risk = make_feature_vector(
        rainfall_intensity=2, drainage_utilization=10, blockage_percentage=5,
        elevation=340, historical_flood_frequency="LOW",
    )
    high_risk = make_feature_vector(
        rainfall_intensity=75, drainage_utilization=250, blockage_percentage=70,
        elevation=160, historical_flood_frequency="HIGH",
    )
    low_prob = predict_module.predict_flood_probability(low_risk)
    high_prob = predict_module.predict_flood_probability(high_risk)

    assert 0.0 <= low_prob <= 1.0
    assert 0.0 <= high_prob <= 1.0
    assert high_prob > low_prob

    importances = predict_module.get_feature_importances()
    assert set(importances.keys()) == set(FEATURE_COLUMNS)
    assert abs(sum(importances.values()) - 1.0) < 0.05  # RF importances sum to ~1.0


def test_predict_returns_none_without_trained_model(tmp_path, monkeypatch):
    from ml import predict as predict_module

    monkeypatch.setattr(predict_module, "MODEL_PATH", tmp_path / "does_not_exist.pkl")
    monkeypatch.setattr(predict_module, "METADATA_PATH", tmp_path / "does_not_exist.json")
    predict_module.reset_cache_for_testing()

    assert predict_module.is_model_available() is False
    assert predict_module.predict_flood_probability(make_feature_vector()) is None
    assert predict_module.get_feature_importances() is None


def test_explanation_covers_every_factor():
    fv = make_feature_vector()
    explanation = build_explanation(fv, flood_probability=0.3, risk_category="MODERATE", feature_importances=None)

    factors = {b["factor"] for b in explanation["breakdown"]}
    assert factors == set(FACTOR_DEFINITIONS.keys())
    assert "equally" in explanation["disclaimer"] or "No trained ML model" in explanation["disclaimer"]


def test_explanation_ranks_by_severity_and_importance():
    fv = make_feature_vector(rainfall_intensity=70, rainfall_1h=70, drainage_utilization=10, blockage_percentage=5)
    importances = {c: 1.0 / len(FEATURE_COLUMNS) for c in FEATURE_COLUMNS}
    explanation = build_explanation(fv, flood_probability=0.6, risk_category="HIGH", feature_importances=importances)

    assert explanation["breakdown"][0]["factor"] == "Rainfall"
    scores = [b["rank_score"] for b in explanation["breakdown"]]
    assert scores == sorted(scores, reverse=True)


def test_explanation_text_for_low_risk_names_no_dominant_factor():
    fv = make_feature_vector(rainfall_intensity=2, drainage_utilization=5, blockage_percentage=0, elevation=340)
    explanation = build_explanation(fv, flood_probability=0.05, risk_category="LOW", feature_importances=None)
    assert "low" in explanation["explanation_text"].lower()
