# SIH26085 — Urban Flood Nowcasting System (FlowState)

An urban flood nowcasting and decision-support platform that couples
real-time rainfall forecasting with a physics-based runoff/drainage
model and a machine learning layer, so it demonstrates the full pipeline:

```
WEATHER DATA → RAINFALL → RUNOFF → DRAINAGE → BLOCKAGE → WATER ACCUMULATION
   → 0-3HR NOWCAST → EXPLAINABLE AI → RISK MAP → SAFE ROUTE → ALERT → DECISION
```

This is a **prototype built for the Smart India Hackathon**, not a
validated operational flood forecasting system — see [Limitations](#limitations)
for exactly what that means.

---

## 1. Project Overview

FlowState answers four questions for a given zone: **WHERE** will
flooding happen, **WHEN**, **WHY**, and **WHAT** should citizens/authorities
do about it. It's not a weather app — every screen traces back to the
rain → runoff → drainage → risk pipeline above.

## 2. Problem Statement (SIH26085)

Urban flooding in Indian cities is driven by the interaction between
rainfall intensity and drainage network capacity — a heavy storm on a
well-drained area may cause no flooding, while a moderate storm on a
blocked or undersized drainage network can flood streets within minutes.
Most public flood information (weather apps) shows rainfall alone,
without coupling it to the drainage side of the equation. This system
demonstrates that coupling explicitly.

## 3. Architecture

```
React Frontend (Vite + react-leaflet)
        │  REST (JSON)
Flask Backend
  ├─ routes/        (thin HTTP layer)
  ├─ flood_engine/  (runoff, drainage, accumulation, risk, blockage, routing — pure functions)
  ├─ ml/            (feature engineering, training, prediction, explainability)
  ├─ services/      (weather ingestion, nowcast orchestration, alerts, simulation)
  └─ models/        (SQLAlchemy ORM — 13 tables)
        │
   SQLite (flood_nowcasting.db)
```
## 4. Technology Stack

**Backend:** Python 3.10+, Flask, Flask-CORS, SQLAlchemy, SQLite, pandas,
NumPy, scikit-learn (Random Forest), requests, joblib.

**Frontend:** React 19, Vite, react-leaflet v5
(Leaflet.js + OpenStreetMap tiles),  lucide-react.

**External APIs:** Open-Meteo (weather, no key required), OpenRouteService
(optional — routing falls back to an honest estimate without a key).

## 5. Folder Structure

```
sih26085-flood-nowcasting/
├── backend/
│   ├── app.py, config.py, extensions.py, requirements.txt, Procfile
│   ├── models/        13 SQLAlchemy models
│   ├── routes/        11 blueprints (one per API concern)
│   ├── services/      weather, rainfall pipeline, nowcast engine,
│   │                   blockage detector, routing, simulation, alerts
│   ├── flood_engine/  runoff, drainage, accumulation, risk, blockage, routing
│   ├── ml/            feature_engineering, train, predict, explain, saved_models/
│   ├── utils/         cache, validators, time_utils, demo_data_generator
│   ├── database/      init_db, seed
│   └── tests/         one file per phase, ~50 tests total
├── frontend/
│   └── src/           api.js, riskMapping.js, hooks.js, App.jsx
├── data/demo/         synthetic_flood_history.csv (ML training data)
└── PROJECT_STATUS.md  build history, bugs found/fixed, what's illustrative vs. real
```

## 6. Installation

Prerequisites: Python 3.10+, Node.js 18+, Git.



## 7. Environment Setup

```bash
cd backend
python -m venv venv
# Windows PowerShell: .\\venv\\Scripts\\Activate.ps1
# Mac/Linux:    source venv/bin/activate
pip install -r requirements.txt
copy .env.example .env      # Mac/Linux: cp .env.example .env
```
No API keys are required for the demo — Open-Meteo needs none, and
routing falls back to an honest estimate without `ROUTING_API_KEY`.

## 8. Database Setup

```bash
flask --app app init-db
flask --app app seed-db
```
This creates 16 Gurugram monitoring zones, ~60 drains, 48 hours of rainfall
history, demo flood events, and road segments. The trained ML model is
already included at `ml/saved_models/flood_rf_model.pkl` — retrain with
`flask --app app train-model` only if you want to regenerate it.

## 9. Running the Backend

```bash
python app.py
```
Visit `http://localhost:5000/api/health` — expect
`{"data": {"status": "ok", "database": "ok"}}`.

Useful CLI commands: `run-pipeline` (pull live weather), `detect-blockages`
(estimate drain blockage), `generate-alerts` (refresh the alerts table).

## 10.1 SIH Demo Admin Login

The prototype includes a demo admin account for the presentation login flow:

- Email: `admin@admin.com`
- Password: `Admin@123`
- Role: `admin`

Run `flask --app app init-db` once after extracting the project. The command creates the database tables and the demo admin account if it does not already exist. The same account is also ensured by `seed-db`.

> This is a **demo credential**, not a production authentication system. Change `ADMIN_EMAIL` and `ADMIN_PASSWORD` in `backend/.env` for any deployment outside the SIH demo.

## 10. Running the Frontend

```bash
cd frontend
npm install
npm run dev
```
Visit the URL Vite prints (usually `http://localhost:5173`).

## 11. API Documentation

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/health` | Liveness + DB check |
| GET | `/api/weather?zone_id=` | Live/cached weather for a zone |
| GET | `/api/rainfall?zone_id=` | Stored rainfall records |
| GET | `/api/zones`, `/api/zones/<id>` | Zone metadata |
| GET | `/api/drains`, `/api/drains/<id>` | Drain metadata + latest reading |
| POST | `/api/drains/<id>/simulate-blockage` | Demo blockage slider |
| GET | `/api/flood-risk`, `/api/flood-risk/<zone_id>` | Current risk snapshot |
| GET | `/api/nowcast`, `/api/nowcast/<zone_id>` | 0-3hr, 7-step forecast |
| GET | `/api/explain/<zone_id>` | Explainability breakdown |
| GET | `/api/routes`, POST `/api/routes/safe` | Road segments / safe routing |
| GET | `/api/alerts` | Active alerts (regenerated on each call) |
| POST | `/api/simulation` | What-if scenario |

Every response follows `{"data": ..., "meta": {"source": ..., "generated_at": ...}}`.

## 12. Flood Calculation Methodology

## 12. Flood Calculation Methodology

Rational Method: `Q = 0.278 × C × I × A` (runoff m³/s, where `C` is the
predefined runoff coefficient for the monitoring zone, `I` is rainfall
mm/hr, and `A` is area km²).
Drainage: `effective_capacity = normal_capacity × (1 − blockage%)`.
Water depth accumulates stepwise across the 7 nowcast timesteps, rising
when runoff exceeds capacity and receding otherwise. Full derivation and
stated assumptions are in `flood_engine/runoff.py`, `drainage.py`,
`accumulation.py`.

## 13. ML Methodology

RandomForestClassifier (200 trees, max depth 10) trained on 2000
synthetic samples (`data/demo/synthetic_flood_history.csv`) generated
from a hand-built scoring rule plus noise — **not real historical flood
data**. Test accuracy reflects how well the model recovers that synthetic
rule, not real-world skill (see `ml/train.py`'s saved metadata). Its
prediction is blended with the rule-based physical score, never used
alone (`flood_engine/risk.py`).

## 14. Explainable AI

`ml/explain.py` combines each factor's current severity with the
trained model's global feature importance, ranks the seven factors
(Rainfall, Drainage Load, Blockage, Elevation, Slope,History)
, and generates a plain-language explanation — always paired
with a disclaimer that this is an approximation, not causal proof.

## 15. Drain Blockage Detection

No real sensors exist in this prototype. `flood_engine/blockage.py`
estimates blockage from drain condition (GOOD/FAIR/POOR), days since
last inspection, and an optional flow-deficit signal — explicitly a
coarse heuristic, documented as such in the code.

## 16. Safe Routing

`services/routing_service.py` tries OpenRouteService only if
`ROUTING_API_KEY` is set; otherwise it honestly estimates road distance
(straight-line × 1.3 detour factor) and checks which real zones the
path passes near, detouring around any at HIGH/SEVERE risk. Never
pretends to have real turn-by-turn road geometry it doesn't have.

## 17. Simulation

`POST /api/simulation` runs the actual flood engine (not a separate toy
formula) against user-supplied rainfall/duration/blockage, and returns
it alongside the zone's real current prediction for a BEFORE/AFTER
comparison.

## 18. Testing

```bash
pytest backend/tests/ -v
```
~50 tests across every phase. Pure-function modules (flood_engine/*,
ml/feature_engineering.py, ml/explain.py) need no database and were
verified directly in the build sandbox; DB-dependent tests use an
in-memory SQLite fixture (`tests/conftest.py`).

## 19. Limitations

- ML model is trained on **synthetic** data — do not present its
  accuracy figure as real-world validated performance.
- No real IoT drain sensors — blockage is estimated, not measured.
- Rainfall comes only from Open-Meteo forecast data — no real
  rain-gauge network, so "observed" rainfall doesn't exist in this build.
- Safe routing has no real road-network graph — distance/time are
  honest estimates, not turn-by-turn navigation.
- Single-city zone model (currently 16 Gurugram monitoring points) — no
  multi-city support.
- Analytics page's historical-incident trend and ML performance metrics
  are illustrative placeholders (no backend endpoint for real historical
  data yet).

## 20. Windows Quick Setup

From the project root in PowerShell:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\\SIH_SETUP_WINDOWS.ps1
```

The script creates the backend virtual environment, installs the Python dependencies, creates `.env` if needed, initializes the database, and seeds the demo data.

For Python 3.14, the requirements use versions with Python 3.14 compatibility. Pandas 2.3.3 is the first pandas release documented as generally compatible with Python 3.14.

## 21. SIH Presentation

See `SIH_PRESENTATION_SCRIPT.md` for the 6-minute judge-facing demo flow, live-vs-simulated data explanation, and common judge questions.

See `LIVE_DATA_GUIDE.md` for how to verify whether weather is live, cached, or demo fallback.

## 22. Future Improvements

Real municipal drainage GIS data; actual IoT flow/water-level sensors;
a Digital Elevation Model (DEM) for real inundation-extent mapping;
weather radar / satellite rainfall in addition to Open-Meteo; real
historical flood records for ML training; PostgreSQL/PostGIS migration
(the schema is already designed for this); a proper road-network graph
for real routing; WebSocket push instead of polling for live updates.

## Street-level Gurugram upgrade
The original frontend design is preserved. The map now can render street-level GeoJSON from `/api/routes/geojson`, and Safe Route uses Dijkstra on the `RouteSegment` graph. For real Gurugram roads, from `backend` run:

```powershell
python scripts/import_osm.py
```

The importer uses OpenStreetMap/Overpass and stores consecutive road-node pairs. After import, restart Flask and refresh the frontend. If the Overpass service is unavailable, the existing demo road data remains available.

## Latest stability fix

The current package includes a SQLite concurrency fix: read endpoints are cache-first, alert regeneration is explicit, SQLite uses WAL + busy timeout, and write-heavy flood operations are serialized in-process. See `SQLITE_LOCK_FIX.md`.
