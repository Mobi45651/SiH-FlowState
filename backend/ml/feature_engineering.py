"""
ml/feature_engineering.py
----------------------------
Defines FEATURE_COLUMNS -- the exact ordered list of features the Random
Forest is trained on. Both train.py and predict.py import this list rather
than hardcoding column names themselves, so the training schema and the
serving schema can never silently drift apart (a classic, hard-to-debug ML
bug this file exists specifically to prevent).

FEATURE DEFINITIONS:
- rainfall_30min      : rainfall rate (mm/hr) for the current/nearest half-
                         hour bucket. LIMITATION: Open-Meteo is hourly-
                         resolution, so this reuses the enclosing hour's
                         rate rather than a true 30-min reading.
- rainfall_1h/3h/6h    : total forecast rainfall (mm) over the NEXT 1/3/6
                         hours from this timestep. LIMITATION: these look
                         FORWARD (anticipated rainfall), not backward at
                         trailing observed rainfall, because this prototype
                         has no real rain-gauge feed -- only Open-Meteo
                         forecast data is available (see rainfall_pipeline.py).
                         A production system would add real trailing/
                         observed windows too.
- rainfall_intensity   : the single highest hourly rate (mm/hr) forecast in
                         the next 3 hours -- a proxy for "peak burst",
                         distinct from the cumulative totals above.
- cumulative_rainfall  : total forecast rainfall (mm) over the next 6
                         hours. In this prototype this is numerically the
                         same window as rainfall_6h (documented limitation
                         above); kept as a separate named feature because a
                         future version with real trailing/observed data
                         would make the two genuinely different.
- runoff               : Rational Method runoff (m3/s) at this timestep,
                         from flood_engine/runoff.py.
- drainage_capacity    : total effective (blockage-adjusted) drainage
                         capacity (m3/s) for the zone at this timestep.
- drainage_utilization : runoff / drainage_capacity, as a percentage.
- blockage_percentage  : average blockage % across the zone's drains.
- elevation            : zone elevation, metres.
- slope                : zone slope, percent.
- impervious_surface   : zone impervious surface, percent.
- historical_flood_frequency : zone's labeled history, encoded LOW=0,
                         MEDIUM=1, HIGH=2 (see encode_historical_frequency).

Connects to:
- ml/train.py, ml/predict.py    -> both import FEATURE_COLUMNS
- services/nowcast_engine.py    -> builds a feature vector per timestep
- utils/demo_data_generator.py  -> generate_synthetic_training_dataset()
                                    produces rows with these exact columns
"""

FEATURE_COLUMNS = [
    "rainfall_30min",
    "rainfall_1h",
    "rainfall_3h",
    "rainfall_6h",
    "rainfall_intensity",
    "cumulative_rainfall",
    "runoff",
    "drainage_capacity",
    "drainage_utilization",
    "blockage_percentage",
    "elevation",
    "slope",
    "impervious_surface",
    "historical_flood_frequency",
]

FREQUENCY_ENCODING = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}


def encode_historical_frequency(label: str) -> int:
    """Maps the zone's LOW/MEDIUM/HIGH label to a numeric feature. Unknown
    or missing labels default to 0 (LOW) rather than raising, so a zone
    with an unexpected label never crashes a prediction -- it's simply
    treated as having no known flood history."""
    if not label:
        return 0
    return FREQUENCY_ENCODING.get(label.upper(), 0)


def build_feature_vector(
    rainfall_30min: float,
    rainfall_1h: float,
    rainfall_3h: float,
    rainfall_6h: float,
    rainfall_intensity: float,
    cumulative_rainfall: float,
    runoff: float,
    drainage_capacity: float,
    drainage_utilization: float,
    blockage_percentage: float,
    elevation: float,
    slope: float,
    impervious_surface: float,
    historical_flood_frequency,
) -> dict:
    """Assembles a feature dict with exactly the keys in FEATURE_COLUMNS.
    historical_flood_frequency may be passed as a string ("LOW"/"MEDIUM"/
    "HIGH") or already as an int -- strings are encoded automatically."""
    frequency = (
        encode_historical_frequency(historical_flood_frequency)
        if isinstance(historical_flood_frequency, str)
        else historical_flood_frequency
    )
    vector = {
        "rainfall_30min": rainfall_30min,
        "rainfall_1h": rainfall_1h,
        "rainfall_3h": rainfall_3h,
        "rainfall_6h": rainfall_6h,
        "rainfall_intensity": rainfall_intensity,
        "cumulative_rainfall": cumulative_rainfall,
        "runoff": runoff,
        "drainage_capacity": drainage_capacity,
        "drainage_utilization": drainage_utilization,
        "blockage_percentage": blockage_percentage,
        "elevation": elevation,
        "slope": slope,
        "impervious_surface": impervious_surface,
        "historical_flood_frequency": frequency,
    }
    return vector


def feature_vector_to_row(vector: dict) -> list:
    """Converts a feature dict to a plain list IN FEATURE_COLUMNS ORDER --
    this is what actually gets passed to the model, so column order is
    always explicit and never dependent on dict insertion order."""
    missing = [c for c in FEATURE_COLUMNS if c not in vector]
    if missing:
        raise ValueError(f"feature_vector is missing required columns: {missing}")
    return [vector[c] for c in FEATURE_COLUMNS]
