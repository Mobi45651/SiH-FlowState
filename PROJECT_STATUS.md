# Project Status

## Backend — COMPLETE through Phase 11
All 11 phases implemented and wired together. See earlier phase summaries
in chat for details. Includes a real trained ML model
(`backend/ml/saved_models/flood_rf_model.pkl`) and 16 Gurugram monitoring zones.

**If you seeded the database before this update, delete
`flood_nowcasting.db` and re-run `init-db`/`seed-db`** — two real bugs
were found and fixed along the way:
1. A timezone bug where nowcast rainfall lookups silently returned 0
   regardless of actual forecast data (fixed via `utils/time_utils.py`).
2. A missing required field in seed data (`DrainReading.estimated_capacity_m3s`)
   that made `seed-db` fail with an IntegrityError on every run.

## Frontend — WIRED TO LIVE DATA

Your original FlowState UI is preserved in design (same Tailwind classes,
same layout, same dark navy/cyan theme) but every page now pulls from the
real backend instead of mock arrays:

| File | What it does |
|---|---|
| `src/api.js` | Every backend call, in one place |
| `src/riskMapping.js` | Translates backend LOW/MODERATE/HIGH/SEVERE to frontend Low/Moderate/High/Critical |
| `src/hooks.js` | Polling data-fetch hooks (useZones, useFloodRiskSnapshot, useNowcast, useAlerts, useDrains, useExplanation, etc.) |
| `src/App.jsx` | Rewritten -- every page wired to real data (see below) |
| `src/App.original.jsx` | Your original file, kept untouched for reference/diffing |

**Per-page status:**
- **Dashboard** -- real risk distribution, real alerts preview, live weather for the selected zone
- **Flood Map** -- real 15 zones, real per-zone 7-step nowcast timeline (each zone now animates its OWN forecast, not a uniform fake bump like the original mock)
- **Forecast** -- real nowcast chart + NEW: the Phase 6 explainability breakdown (factor bars + plain-language reason), which wasn't in your original design at all
- **Safe Route** -- real 2-route comparison (normal vs. flood-safe) from `/api/routes/safe`, zone dropdowns instead of free-text (no geocoding exists)
- **Alert** -- real alerts from `/api/alerts`
- **Simulation** -- real `/api/simulation` calls against the actual flood engine; added a drainage-blockage slider (the spec calls for 3 controls: rainfall, duration, blockage -- original only had 2)
- **Drainage** -- newly wired into the nav (existed in your code but was unreachable) -- real drain list, real status counts
- **Analytics** -- newly wired into the nav -- risk distribution pie chart is real; the historical-incidents chart and model performance metrics are clearly labeled "Illustrative example" since no backend endpoint provides real historical trend data yet

**Location picker to Zone picker:** your original app modeled a 6-city
picker (Gurugram) with fake weather
per city. The backend only models one city's worth of zones, so this
became a 16-zone picker within Gurugram instead. This is the one real
design change -- flagging it clearly rather than silently swapping it.

## To run it

```bash
cd backend
python -m venv venv
# Windows: venv\Scripts\activate    Mac/Linux: source venv/bin/activate
pip install -r requirements.txt
copy .env.example .env    (Mac/Linux: cp .env.example .env)
flask --app app init-db
flask --app app seed-db
python app.py

# new terminal
cd frontend
npm install
npm run dev
```

## Modules used (see chat for the full annotated list)

Backend: Flask, Flask-Cors, Flask-SQLAlchemy, SQLAlchemy, python-dotenv,
requests, pandas, numpy, scikit-learn, joblib, pytest.

Frontend: react, react-dom, react-leaflet, leaflet, recharts,
lucide-react, vite, @vitejs/plugin-react, tailwindcss,
@tailwindcss/vite.
