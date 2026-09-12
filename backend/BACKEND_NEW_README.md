# FlowState — New Backend (SQLite Lock Safe)

This backend is designed to replace the old backend for the existing FlowState frontend.

## Main fixes

- `GET /api/alerts` is read-only.
- `GET /api/nowcast` and `GET /api/flood-risk` never delete/insert prediction rows.
- Missing/stale nowcast data is computed in memory instead of writing during GET requests.
- Database writes are serialized with a process-local `RLock`.
- SQLite uses WAL mode and a 30-second busy timeout.
- Flask debug/reloader is OFF by default to avoid duplicate development processes.
- Weather uses Open-Meteo `current.temperature_2m` for the current temperature and exposes `apparent_temperature_c` as feels-like.
- Weather responses expose provider grid coordinates so location accuracy can be diagnosed.

## Start on Windows

```powershell
cd C:\SIHackend
.\venv\Scripts\activate
python app.py
```

Or double-click `START_BACKEND_WINDOWS.bat`.

## If using the existing database

Copy this backend's `flood_nowcasting.db` into the backend folder you run. Do not run two Flask/Python servers against the same SQLite file.

## Explicit write operations

- `POST /api/nowcast/refresh` — refresh rainfall + predictions
- `POST /api/alerts/refresh` — regenerate alerts
- `POST /api/simulation` — what-if simulation
- `POST /api/drains/<id>/simulate-blockage` — simulation/demo write

Normal dashboard GET requests are read-only.
