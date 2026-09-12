"""
utils/time_utils.py
----------------------
SQLite (via SQLAlchemy's default DateTime column type) does NOT preserve
timezone info: a timezone-AWARE datetime written to a DateTime column
comes back NAIVE on the next read -- in the same process or a different
one. Comparing or dict-keying a freshly computed aware datetime (e.g.
datetime.now(timezone.utc)) against a value read back from the database
does not raise an error -- it just silently returns False/no-match, even
when both represent the exact same moment.

This bit us for real: nowcast_engine.py compared a fresh aware "now"
against WeatherForecast rows read back from SQLite (naive), so every
rainfall lookup silently missed and fell back to its 0.0mm default --
making the nowcast produce identical output regardless of actual rainfall.

RULE: every datetime that will be written to, read from, or compared
against a database DateTime column must be NAIVE, treated as implicitly
UTC. Use utc_now() below instead of datetime.now(timezone.utc), and
to_naive_utc() to strip tzinfo from any other aware datetime (e.g. from
pandas, or from Open-Meteo's parsed timestamps), before it touches the
database in any way.

Datetimes used ONLY for a JSON response's "generated_at" field (never
written to or compared against the DB) are unaffected by this and can
keep using datetime.now(timezone.utc) directly.
"""

from datetime import datetime, timezone


def utc_now() -> datetime:
    """Current UTC time as a NAIVE datetime (no tzinfo). Use this instead
    of datetime.now(timezone.utc) for any value that will be written to,
    compared against, or used as a dict-lookup key alongside a value read
    from the database."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_naive_utc(value: datetime) -> datetime:
    """Strips tzinfo from an aware datetime (converting to UTC first if it
    was in another zone) so it's safe to store in / compare against a
    SQLite DateTime column. A value that's already naive is returned
    unchanged (assumed already UTC)."""
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value
