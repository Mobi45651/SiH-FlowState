"""
ml/train.py
-------------
Trains a RandomForestClassifier to predict flood_probability (via
predict_proba) from the columns in ml/feature_engineering.FEATURE_COLUMNS,
against a binary "flooded" label.

Usage:
    python -m ml.train                              # synthetic demo dataset
                                                      # (generated + saved to
                                                      # data/demo/synthetic_flood_history.csv
                                                      # on first run)
    python -m ml.train --csv path/to/real_data.csv --real
                                                      # train on a real,
                                                      # non-synthetic dataset

IMPORTANT: the default dataset is 100% synthetic (see
utils/demo_data_generator.generate_synthetic_training_dataset). Test
accuracy on it reflects how well the model recovers the synthetic
generating rule, NOT real-world flood prediction skill. This is recorded
plainly in the saved metadata so nobody downstream mistakes it for a
validated model.

Connects to:
- ml/feature_engineering.py -> FEATURE_COLUMNS defines the training columns
- utils/demo_data_generator.py -> supplies the synthetic dataset
- ml/predict.py -> loads exactly what this script saves
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report
import joblib

from ml.feature_engineering import FEATURE_COLUMNS

ML_DIR = Path(__file__).resolve().parent
MODEL_DIR = ML_DIR / "saved_models"
MODEL_PATH = MODEL_DIR / "flood_rf_model.pkl"
METADATA_PATH = MODEL_DIR / "model_metadata.json"

# backend/ml/train.py -> parents[2] is the project root (sih26085-flood-nowcasting)
PROJECT_ROOT = ML_DIR.parents[1]
DEMO_CSV_PATH = PROJECT_ROOT / "data" / "demo" / "synthetic_flood_history.csv"


def load_or_generate_dataset(csv_path: Path, is_real: bool) -> tuple:
    """Returns (dataframe, is_synthetic). If csv_path is the default demo
    path and doesn't exist yet, generates and saves it first."""
    if csv_path.exists():
        return pd.read_csv(csv_path), not is_real

    if csv_path != DEMO_CSV_PATH:
        raise FileNotFoundError(f"No dataset found at {csv_path}")

    from utils.demo_data_generator import generate_synthetic_training_dataset
    df = generate_synthetic_training_dataset()
    DEMO_CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(DEMO_CSV_PATH, index=False)
    print(f"Generated synthetic training dataset -> {DEMO_CSV_PATH} ({len(df)} rows)")
    return df, True


def train_model(csv_path: str | None = None, is_real: bool = False) -> dict:
    path = Path(csv_path) if csv_path else DEMO_CSV_PATH
    df, is_synthetic = load_or_generate_dataset(path, is_real)

    required_columns = FEATURE_COLUMNS + ["flooded"]
    missing = [c for c in required_columns if c not in df.columns]
    if missing:
        raise ValueError(f"Dataset at {path} is missing required columns: {missing}")

    X = df[FEATURE_COLUMNS]
    y = df["flooded"]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y if y.nunique() > 1 else None
    )

    model = RandomForestClassifier(
        n_estimators=200, max_depth=10, random_state=42, class_weight="balanced"
    )
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    accuracy = accuracy_score(y_test, y_pred)
    report = classification_report(y_test, y_pred, output_dict=True, zero_division=0)
    importances = {
        col: round(float(imp), 4) for col, imp in zip(FEATURE_COLUMNS, model.feature_importances_)
    }

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, MODEL_PATH)

    metadata = {
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "feature_columns": FEATURE_COLUMNS,
        "is_synthetic_dataset": is_synthetic,
        "dataset_path": str(path),
        "sample_count": int(len(df)),
        "test_accuracy": round(float(accuracy), 4),
        "classification_report": report,
        "feature_importances": importances,
        "notes": (
            "Trained on a SYNTHETIC demo dataset (data/demo/synthetic_flood_history.csv). "
            "The accuracy figure above reflects how well this model recovers the synthetic "
            "generating rule, NOT real-world flood prediction accuracy. Do not present this "
            "as a validated flood model in a real deployment -- replace the dataset with real "
            "historical flood records and retrain first."
            if is_synthetic else
            "Trained on a user-supplied dataset marked as real (non-synthetic) data."
        ),
    }
    with open(METADATA_PATH, "w") as f:
        json.dump(metadata, f, indent=2)

    print(f"\nTrained on {'SYNTHETIC' if is_synthetic else 'REAL'} data: {len(df)} samples")
    print(f"Test accuracy: {accuracy:.3f}")
    print("\nFeature importances (highest first):")
    for name, imp in sorted(importances.items(), key=lambda kv: -kv[1]):
        print(f"  {name:28s} {imp}")
    print(f"\nModel saved to:    {MODEL_PATH}")
    print(f"Metadata saved to: {METADATA_PATH}")

    return metadata


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train the flood-risk Random Forest model.")
    parser.add_argument(
        "--csv", type=str, default=None,
        help="Path to a training CSV with FEATURE_COLUMNS + 'flooded'. Defaults to the synthetic demo dataset.",
    )
    parser.add_argument(
        "--real", action="store_true",
        help="Mark the supplied --csv as real (non-synthetic) data in the saved metadata.",
    )
    args = parser.parse_args()
    train_model(csv_path=args.csv, is_real=args.real)
