"""
flood_engine/runoff.py
-------------------------
Implements a simplified Rational Method runoff calculation:

    Q = 0.278 * C * I * A

Units:
- Q: peak runoff rate, m^3/s
- C: dimensionless runoff coefficient (0-1), derived here from a zone's
     impervious_surface_percent
- I: rainfall intensity, mm/hr
- A: catchment (zone) area, km^2
- 0.278 is the standard SI unit-conversion constant for this form of the
  Rational Method (equivalent to C*I*A/360 when A is expressed in hectares
  instead of km^2)

Assumptions & limitations (read this before trusting the numbers):
- The Rational Method assumes STEADY, UNIFORM rainfall across the whole
  catchment, and a catchment small enough that time-of-concentration
  effects are negligible. It's a standard first-pass estimate for small
  urban catchments -- it is NOT a hydrodynamic model. There is no flow
  routing, no infiltration curve, no storage/attenuation.
- C is estimated purely from impervious_surface_percent, blended between
  two fixed reference coefficients (IMPERVIOUS_C / PERVIOUS_C below). Real
  C values vary with soil type, antecedent moisture, and slope; this is a
  reasonable planning-level approximation, not a calibrated value.
- I is taken directly from a zone's stored rainfall_mm for the relevant
  timestep, which this project treats as already representing mm/hr
  (ingestion pulls hourly Open-Meteo data, so one record = one hour).

Connects to:
- flood_engine/drainage.py     -> effective drainage capacity is compared
                                   against this module's runoff_m3s output
- flood_engine/accumulation.py -> consumes runoff_m3s (via drainage.py) to
                                   compute excess flow
- flood_engine/risk.py (Phase 6)      -> combines this with the ML output
- ml/feature_engineering.py (Phase 6) -> reuses compute_runoff_coefficient
"""

IMPERVIOUS_C = 0.90  # typical runoff coefficient for paved/built-up surface
PERVIOUS_C = 0.20    # typical runoff coefficient for green/permeable surface
SI_CONVERSION_CONSTANT = 0.278  # converts C * I(mm/hr) * A(km^2) into m^3/s


def compute_runoff_coefficient(impervious_surface_percent: float) -> float:
    """Blends IMPERVIOUS_C and PERVIOUS_C by the zone's impervious share.
    Clamped to [0, 100] defensively, since this is fed by stored zone data
    rather than a live sensor that could be trusted to always be in range.
    """
    pct = max(0.0, min(100.0, impervious_surface_percent))
    impervious_fraction = pct / 100.0
    pervious_fraction = 1 - impervious_fraction
    return round(impervious_fraction * IMPERVIOUS_C + pervious_fraction * PERVIOUS_C, 4)


def compute_runoff(rainfall_intensity_mm_per_hr: float, area_km2: float,
                    impervious_surface_percent: float) -> dict:
    """Returns a dict (not just a bare number) so callers -- including the
    Explainable AI feature in Phase 6 -- always have the intermediate C and
    I values available to show their work, not just the final Q."""
    if rainfall_intensity_mm_per_hr < 0:
        raise ValueError("rainfall_intensity_mm_per_hr cannot be negative.")
    if area_km2 <= 0:
        raise ValueError("area_km2 must be positive.")

    coefficient = compute_runoff_coefficient(impervious_surface_percent)
    runoff_m3s = round(
        SI_CONVERSION_CONSTANT * coefficient * rainfall_intensity_mm_per_hr * area_km2, 4
    )

    return {
        "runoff_m3s": runoff_m3s,
        "runoff_coefficient": coefficient,
        "rainfall_intensity_mm_per_hr": rainfall_intensity_mm_per_hr,
        "area_km2": area_km2,
        "method": "rational_method",
    }


def compute_cumulative_rainfall(rainfall_values_mm: list) -> float:
    """Sums a list of hourly (or sub-hourly) rainfall_mm values, ignoring
    Nones. Used both by the flood engine for multi-hour context and by
    ml/feature_engineering.py for the rainfall_3h / rainfall_6h features."""
    return round(sum(v for v in rainfall_values_mm if v is not None), 2)
