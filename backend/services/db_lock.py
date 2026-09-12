"""Process-local serialization for SQLite write-heavy flood calculations.

The hackathon app uses SQLite. Flask can serve multiple requests concurrently,
so long-running delete/insert/commit operations must not overlap. This lock is
shared by nowcast, rainfall ingestion and alert generation within the Flask
process. SQLite WAL + busy_timeout in config.py handles reader/writer overlap.
For production multi-worker deployments, use PostgreSQL or another server DB.
"""
from threading import RLock

DB_WRITE_LOCK = RLock()
