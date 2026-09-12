# SQLite lock fix — new backend

## Root cause
The old dashboard flow could cause GET requests to generate alerts and rebuild the `flood_predictions` table. When the location dropdown fired several requests close together, two requests could attempt SQLite writes at the same time. The traceback ended at `DELETE FROM flood_predictions` with `sqlite3.OperationalError: database is locked`.

## New rule
Normal dashboard GET endpoints are read-only:

- `GET /api/weather` — weather read; DB ingestion only if explicitly requested with `ingest=1`.
- `GET /api/nowcast` — cached/read-only or in-memory recomputation.
- `GET /api/flood-risk` — read-only.
- `GET /api/alerts` — read-only.
- `GET /api/routes` and `GET /api/routes/geojson` — read-only.

Explicit write operations are separated:

- `POST /api/nowcast/refresh`
- `POST /api/alerts/refresh`
- rainfall pipeline/CLI jobs
- simulation/blockage operations

## SQLite protection
- WAL journal mode
- 30-second SQLite busy timeout
- process-local `RLock` around write-heavy operations
- Flask debug reloader disabled by default
- failed requests roll back the SQLAlchemy session

For a production multi-worker deployment, PostgreSQL/PostGIS is still recommended.
