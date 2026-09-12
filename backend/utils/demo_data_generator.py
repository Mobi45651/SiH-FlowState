"""
utils/demo_data_generator.py
------------------------------
Every piece of synthetic data in the project is generated HERE and nowhere
else, so a judge asking "where does this number come from?" always has one
answer. Uses a fixed random seed so the demo dataset is reproducible run to
run (important for consistent SIH demos and for grading ML results).

Zone names and coordinates are Gurugram monitoring points chosen for the SIH
prototype. Coordinates are approximate points, not official municipal flood
boundaries. Physical attributes per zone (elevation, slope, impervious
surface) are demo-estimated values, NOT surveyed data -- a real deployment
would pull these from an actual DEM/GIS survey. Drain names, readings, and
flood events remain synthetic.

Connects to:
- database/seed.py -> calls these functions and writes the results to the DB
- ml/train.py      -> may reuse generate_flood_events() for training labels
                       if no real historical dataset is supplied
"""

import random
from datetime import datetime, timedelta, timezone

from utils.time_utils import utc_now

random.seed(42)  # reproducible demo data across every run

FREQUENCY_LEVELS = ["LOW", "MEDIUM", "HIGH"]

# Gurugram monitoring zones with approximate coordinates. Frequency labels are
# prototype/demo estimates, not official municipal flood classifications.
GURUGRAM_ZONES = [
    # (name, lat, lng, historical_flood_frequency)
    # Coordinates are approximate monitoring points for the SIH prototype;
    # they are not official municipal flood-zone boundaries.
    ("Gurugram City Centre", 28.4595, 77.0266, "HIGH"),
    ("Sector 15", 28.4597, 77.0520, "HIGH"),
    ("Sector 29", 28.4676, 77.0645, "HIGH"),
    ("Sector 31", 28.4486, 77.0550, "MEDIUM"),
    ("Sector 40", 28.4470, 77.0400, "MEDIUM"),
    ("Sector 44", 28.4424, 77.0515, "MEDIUM"),
    ("Sector 46", 28.4300, 77.0660, "HIGH"),
    ("Sector 52", 28.4476, 77.0905, "MEDIUM"),
    ("Sector 56", 28.4239, 77.1025, "HIGH"),
    ("Sector 57", 28.4146, 77.0912, "MEDIUM"),
    ("Sector 62", 28.4148, 77.1392, "MEDIUM"),
    ("DLF Cyber City", 28.4947, 77.0895, "HIGH"),
    ("Palam Vihar", 28.5152, 77.0780, "MEDIUM"),
    ("Golf Course Road", 28.4389, 77.1020, "MEDIUM"),
    ("Badshahpur", 28.4089, 77.0412, "HIGH"),
    ("Manesar", 28.3558, 76.9360, "MEDIUM"),
]



def generate_zones():
    """Return a list of dicts matching the Zone model's constructor fields."""
    zones = []
    for i, (name, lat, lng, fixed_frequency) in enumerate(GURUGRAM_ZONES, start=1):
        frequency = fixed_frequency or random.choices(FREQUENCY_LEVELS, weights=[0.5, 0.3, 0.2])[0]
        zones.append({
            "zone_code": f"Z{i:03d}",
            "name": name,
            "latitude": lat,
            "longitude": lng,
            "elevation_m": round(random.uniform(200, 260), 1),  # Gurugram sits ~213-250m above sea level
            "slope_percent": round(random.uniform(0.2, 4.0), 2),  # generally low-slope urban terrain
            "impervious_surface_percent": round(random.uniform(35, 92), 1),
            "area_km2": round(random.uniform(0.8, 6.5), 2),
            "historical_flood_frequency": frequency,
        })
    return zones


def generate_drains(zone_dicts):
    """3-6 drains per zone, scattered within ~1.5km of that zone's own
    coordinates (each Gurugram zone is geographically distinct, unlike the
    old single-city-block placeholder, so drains must jitter around their
    OWN zone's lat/lng, not a shared city-wide point)."""
    drains = []
    for zone in zone_dicts:
        zone_code = zone["zone_code"]
        drain_count = random.randint(3, 6)
        for d in range(1, drain_count + 1):
            drains.append({
                "drain_code": f"{zone_code}-D{d:02d}",
                "zone_code": zone_code,  # resolved to zone_id in seed.py
                "latitude": zone["latitude"] + random.uniform(-0.012, 0.012),
                "longitude": zone["longitude"] + random.uniform(-0.012, 0.012),
                "normal_capacity_m3s": round(random.uniform(1.5, 6.0), 2),
                "condition": random.choices(
                    ["GOOD", "FAIR", "POOR"], weights=[0.6, 0.3, 0.1]
                )[0],
                "last_inspection_date": (
                    datetime.now(timezone.utc).date() - timedelta(days=random.randint(10, 400))
                ),
                "status": "NORMAL",
            })
    return drains


def generate_initial_drain_readings(drain_dicts):
    """One baseline (non-simulated) reading per drain, mild randomness.
    Takes full drain dicts (not just codes) because estimated_capacity_m3s
    is a required (NOT NULL) column on DrainReading and must be computed
    from each drain's own normal_capacity_m3s -- using the same formula
    flood_engine/drainage.py uses everywhere else, so this seed data is
    internally consistent with the rest of the engine."""
    from flood_engine.drainage import compute_effective_capacity

    readings = []
    now = utc_now()
    for drain in drain_dicts:
        blockage = round(random.uniform(0, 15), 1)  # healthy baseline
        readings.append({
            "drain_code": drain["drain_code"],
            "timestamp": now,
            "current_flow_m3s": round(random.uniform(0.5, 2.5), 2),
            "blockage_percent": blockage,
            "estimated_capacity_m3s": compute_effective_capacity(drain["normal_capacity_m3s"], blockage),
            "blockage_probability": round(blockage / 100 * random.uniform(0.8, 1.1), 2),
            "status": "NORMAL",
            "is_simulated": False,
        })
    return readings


def generate_rainfall_history(zone_codes, hours_back=48):
    """Hourly OBSERVED rainfall for the past `hours_back` hours per zone."""
    records = []
    now = utc_now().replace(minute=0, second=0, microsecond=0)
    for zone_code in zone_codes:
        # Each zone gets a mostly-dry history with 1-2 rain bursts, so the
        # demo dataset isn't unrealistically rainy every single hour.
        burst_hours = set(random.sample(range(hours_back), k=random.randint(2, 5)))
        for h in range(hours_back):
            ts = now - timedelta(hours=hours_back - h)
            rainfall = round(random.uniform(8, 45), 1) if h in burst_hours else round(random.uniform(0, 1.5), 1)
            records.append({
                "zone_code": zone_code,
                "timestamp": ts,
                "rainfall_mm": rainfall,
                "source": "observed",
            })
    return records


def generate_flood_events(zone_code, frequency_level):
    """0-5 demo historical events depending on the zone's frequency label."""
    count_by_level = {"LOW": (0, 1), "MEDIUM": (1, 3), "HIGH": (3, 5)}
    lo, hi = count_by_level.get(frequency_level, (0, 1))
    count = random.randint(lo, hi)
    events = []
    for _ in range(count):
        severity = random.choices(
            ["LOW", "MODERATE", "HIGH", "SEVERE"], weights=[0.3, 0.35, 0.25, 0.1]
        )[0]
        events.append({
            "zone_code": zone_code,
            "event_date": datetime.now(timezone.utc).date() - timedelta(days=random.randint(30, 1500)),
            "severity": severity,
            "water_depth_cm": round(random.uniform(5, 60), 1),
            "description": f"Synthetic demo flood event ({severity.title()}) for {zone_code}.",
            "source": "demo",
        })
    return events


def generate_demo_hourly_weather(hours_ahead=48):
    """Synthetic hourly forecast shaped like a parsed Open-Meteo response,
    used ONLY when the real API call fails and the caller explicitly opts
    into a demo fallback (see services/weather_service.py). Every record
    the caller builds from this must be tagged source="demo" downstream --
    this function does not set that field itself, on purpose, so it can
    never be forgotten by accident at the call site."""
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    burst_hours = set(random.sample(range(hours_ahead), k=random.randint(2, 4)))
    records = []
    for h in range(hours_ahead):
        ts = now + timedelta(hours=h)
        precip = round(random.uniform(10, 40), 1) if h in burst_hours else round(random.uniform(0, 1.0), 1)
        records.append({
            "time": ts.isoformat(),
            "precipitation_mm": precip,
            "precipitation_probability": min(95, round(precip * 2 + random.uniform(0, 10), 1)),
            "temperature_c": round(random.uniform(22, 34), 1),
            "humidity_percent": round(random.uniform(55, 95), 1),
            "wind_kmh": round(random.uniform(3, 25), 1),
            "pressure_hpa": round(random.uniform(1000, 1015), 1),
        })
    return records


def generate_route_segments(zones):
    """A handful of named road segments per zone, risk tied to the zone's
    historical frequency so the safe-route planner has something meaningful
    to route around even before live predictions exist."""
    risk_by_frequency = {"LOW": "LOW", "MEDIUM": "MODERATE", "HIGH": "HIGH"}
    segments = []
    for zone in zones:
        seg_count = random.randint(2, 4)
        for s in range(1, seg_count + 1):
            lat1 = zone["latitude"] + random.uniform(-0.01, 0.01)
            lng1 = zone["longitude"] + random.uniform(-0.01, 0.01)
            lat2 = zone["latitude"] + random.uniform(-0.01, 0.01)
            lng2 = zone["longitude"] + random.uniform(-0.01, 0.01)
            risk = risk_by_frequency.get(zone["historical_flood_frequency"], "LOW")
            segments.append({
                "road_name": f"{zone['name']} Road {s}",
                "zone_code": zone["zone_code"],
                "start_lat": lat1, "start_lng": lng1,
                "end_lat": lat2, "end_lng": lng2,
                "risk_category": risk,
                "distance_km": round(random.uniform(0.5, 3.0), 2),
                "is_flood_prone": risk in ("HIGH", "SEVERE"),
            })
    return segments


def generate_synthetic_training_dataset(n_samples: int = 2000):
    """Generates a SYNTHETIC labeled dataset for ml/train.py, with the exact
    columns ml/feature_engineering.FEATURE_COLUMNS plus a binary "flooded"
    label. Uses the same seeded RNG as every other demo value in this file
    (reproducible run to run).

    The label is generated from a hand-built scoring rule PLUS Gaussian
    noise, then sampled as a Bernoulli draw -- this makes it a genuinely
    learnable-but-imperfect pattern for the Random Forest, not a trivial
    lookup. It is NOT derived from real flood outcomes. Training accuracy
    on this dataset measures how well the model recovers the synthetic
    generating rule, NOT real-world predictive accuracy -- ml/train.py
    labels this explicitly in the saved model's metadata.

    Returns a pandas DataFrame. Import pandas lazily inside the function so
    modules that only need the DB-seeding generators above don't require
    pandas to be installed.
    """
    import numpy as np
    import pandas as pd
    from ml.feature_engineering import FEATURE_COLUMNS

    rng = np.random.default_rng(42)  # separate, explicit seed from the `random` module above

    rows = []
    for _ in range(n_samples):
        rainfall_1h = float(rng.uniform(0, 80))
        rainfall_3h = rainfall_1h + float(rng.uniform(0, 60))
        rainfall_6h = rainfall_3h + float(rng.uniform(0, 40))
        rainfall_intensity = rainfall_1h + float(rng.uniform(0, 20))
        cumulative_rainfall = rainfall_6h  # same window, see feature_engineering.py note
        rainfall_30min = rainfall_1h  # hourly-resolution reuse, see feature_engineering.py note

        drainage_capacity = float(rng.uniform(1.0, 12.0))
        blockage_percentage = float(rng.uniform(0, 80))
        effective_capacity = drainage_capacity * (1 - blockage_percentage / 100)
        # runoff loosely tracks rainfall_intensity with noise, capped >= 0
        runoff = max(0.0, rainfall_intensity * float(rng.uniform(0.02, 0.06)))
        drainage_utilization = min(300.0, (runoff / effective_capacity * 100) if effective_capacity > 0 else 300.0)

        elevation = float(rng.uniform(150, 350))
        slope = float(rng.uniform(0.5, 10.0))
        impervious_surface = float(rng.uniform(30, 95))
        historical_flood_frequency = int(rng.integers(0, 3))  # 0/1/2 already encoded

        score = (
            0.35 * min(drainage_utilization / 150, 1.0)
            + 0.25 * min(rainfall_intensity / 80, 1.0)
            + 0.15 * (blockage_percentage / 100)
            + 0.10 * max((350 - elevation) / 200, 0)
            + 0.10 * (historical_flood_frequency / 2)
            + 0.05 * (impervious_surface / 100)
            - 0.05 * min(slope / 10, 1.0)
        )
        score += float(rng.normal(0, 0.08))
        probability = min(max(score, 0.0), 1.0)
        flooded = int(rng.binomial(1, probability))

        rows.append({
            "rainfall_30min": round(rainfall_30min, 2),
            "rainfall_1h": round(rainfall_1h, 2),
            "rainfall_3h": round(rainfall_3h, 2),
            "rainfall_6h": round(rainfall_6h, 2),
            "rainfall_intensity": round(rainfall_intensity, 2),
            "cumulative_rainfall": round(cumulative_rainfall, 2),
            "runoff": round(runoff, 4),
            "drainage_capacity": round(effective_capacity, 4),
            "drainage_utilization": round(drainage_utilization, 2),
            "blockage_percentage": round(blockage_percentage, 2),
            "elevation": round(elevation, 1),
            "slope": round(slope, 2),
            "impervious_surface": round(impervious_surface, 1),
            "historical_flood_frequency": historical_flood_frequency,
            "flooded": flooded,
        })

    df = pd.DataFrame(rows, columns=FEATURE_COLUMNS + ["flooded"])
    return df
