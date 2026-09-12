"""
models/base.py
---------------
TimestampMixin is inherited by every model in this package so all tables get
a consistent "created_at" column without repeating the column definition
twelve times. Kept in its own file so models/__init__.py can import it once
and every model file can `from models.base import TimestampMixin`.
"""

from extensions import db
from utils.time_utils import utc_now


class TimestampMixin:
    # utc_now() returns a NAIVE datetime on purpose -- see utils/time_utils.py.
    # SQLite strips tzinfo on write/read regardless, so storing an aware
    # datetime here would just create a mismatch with values read back later.
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

