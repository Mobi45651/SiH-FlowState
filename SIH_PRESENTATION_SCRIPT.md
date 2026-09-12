# FlowState — SIH 2026 Presentation & Demo Script

## 1. One-line pitch

**FlowState is an urban flood nowcasting and decision-support prototype that combines live weather forecasts, a physics-based runoff/drainage model, machine learning, flood-risk mapping, alerts, and risk-aware routing.**

## 2. What is live vs simulated?

| Component | Prototype status | How to explain it |
|---|---|---|
| Weather forecast | LIVE | Pulled from Open-Meteo for each monitored zone |
| Weather refresh | LIVE/CACHED | Backend caches weather briefly to avoid unnecessary API calls |
| Rainfall used by nowcast | LIVE FORECAST | Open-Meteo hourly precipitation |
| Runoff calculation | COMPUTED | Physics-based Rational Method |
| Drain capacity | DEMO DATABASE | Prototype infrastructure values |
| Drain blockage | SIMULATED / HEURISTIC | No IoT drain sensors are connected |
| Flood ML model | SYNTHETIC-TRAINED | Random Forest trained on generated demonstration data |
| Final flood risk | COMPUTED | Physics/risk engine blended with ML probability |
| Alerts | COMPUTED | Generated from current risk/drain conditions |
| Safe route | PROTOTYPE | Uses risk-aware zone avoidance; may fall back to estimated routing |
| Gurugram locations | REAL APPROXIMATE LOCATIONS | Coordinates represent real approximate Gurugram monitoring points; physical attributes are demo estimates |

**Never describe the synthetic ML model as being trained on real flood records.**

---

# 3. 6-minute live demo script

## 00:00–00:40 — Problem

Say:

> "Urban flooding is not caused by rainfall alone. The same rainfall can have very different impacts depending on runoff, drainage capacity, blockage, terrain and land cover. FlowState tries to connect those factors into one decision-support pipeline."

Show the Dashboard.

---

## 00:40–01:20 — Live weather

Select a Gurugram monitoring zone from the zone picker.

Point to:

- Temperature
- Humidity
- Wind
- Rainfall
- Current risk

Say:

> "The weather layer is connected to Open-Meteo. The backend fetches hourly forecast data for the selected zone and exposes it to the React dashboard."

If the badge says **Live · Open-Meteo**, this is live API data.

If it says **Live · cached**, it is still data originating from Open-Meteo but served from the short backend cache.

If it says **Demo fallback**, explain:

> "The application has a clearly labelled fallback for an API/network failure so the demonstration does not collapse. We never present fallback data as live."

---

## 01:20–02:10 — Flood Map

Open **Flood Map**.

Say:

> "Instead of showing rainfall alone, the map visualizes the flood-risk state of monitored zones. Each zone is linked to the backend nowcast."

Demonstrate:

- Risk zones
- Zone markers
- Rainfall layer
- Drainage layer
- Timeline
- Satellite/Live map controls

Move the page up and down briefly to demonstrate that the map remains below the navigation.

---

## 02:10–03:00 — 0–3 hour nowcast

Open **Forecast**.

Say:

> "The system generates a seven-step nowcast from now to three hours. At each timestep, rainfall drives runoff, runoff is compared with effective drainage capacity, water accumulation is carried forward, and the risk engine produces the current risk."

Show:

```text
NOW → +30m → +60m → +90m → +120m → +150m → +180m
```

Then open the explanation section.

Say:

> "The explainability layer shows the factors contributing to the current risk instead of giving the judge a black-box number."

---

## 03:00–04:00 — Drain blockage simulation

Open **Drainage** or **Simulation**.

For Simulation:

1. Choose a zone.
2. Set rainfall to around 80–100 mm/hr.
3. Set duration to 1–2 hours.
4. Set drainage blockage to around 50–70%.
5. Run simulation.

Say:

> "This is our what-if decision-support capability. A responder can ask: what happens if rainfall intensifies and drainage capacity is reduced by blockage?"

Show the BEFORE and AFTER values.

Emphasize:

> "The simulation runs the same flood-engine calculation rather than displaying a pre-written animation."

---

## 04:00–04:50 — Alerts

Open **Alert Center**.

Say:

> "The alert service converts the computed risk state into actionable warnings. This is designed to move the interface from 'what is happening?' to 'what should we do?'"

Show a few alerts.

---

## 04:50–05:30 — Safe Route

Open **Safe Route**.

Choose two monitored zones.

Click **Find safe route**.

Say:

> "The routing layer compares a normal route with a flood-aware alternative and avoids zones whose predicted risk is too high."

Be transparent:

> "For this prototype, the routing fallback is an estimate when a live routing API key is not configured. A production version would connect this to a proper road graph and live municipal routing data."

---

## 05:30–06:00 — Architecture + close

Show the architecture slide.

Say:

> "The important part is that this is not a collection of disconnected screens. The flow is weather to rainfall, rainfall to runoff, runoff to drainage stress, drainage and blockage to water accumulation, then nowcast, explainable risk, alerts and routing."

Finish:

> "Our prototype demonstrates the complete decision pipeline today. The next production steps are real municipal drainage GIS, IoT water-level and flow sensors, DEM-based inundation mapping, radar or satellite rainfall, and real historical flood records for model training."

---

# 4. If a judge asks difficult questions

### "Is your ML model trained on real flood data?"

Answer:

> "Not yet. The current SIH prototype uses a synthetic training dataset so we can demonstrate the complete ML pipeline honestly. We explicitly do not present its synthetic-data accuracy as real-world forecasting accuracy. The production roadmap is to retrain it using verified historical flood observations."

### "Is the weather real?"

Answer:

> "Yes, the weather forecast integration uses Open-Meteo. The UI identifies whether the response is live, cached, or a demo fallback."

### "Are the drain blockages real?"

Answer:

> "No. We do not claim to have IoT sensors. Blockage is currently a heuristic/demo input. In deployment, this would be replaced or calibrated using flow, water-level and inspection data."

### "Why Gurugram?"

Answer:

> "Gurugram is a strong urban flood-management use case with dense sectors, rapid development, drainage stress, and recurring monsoon waterlogging concerns. The architecture remains city-agnostic, so the same system can be extended to other cities."

### "Can this predict floods accurately?"

Answer:

> "This prototype demonstrates the forecasting architecture, not validated operational accuracy. The current ML model uses synthetic data, so we would require real historical events and rigorous validation before operational deployment."

### "What is novel compared with a weather app?"

Answer:

> "A weather app tells you rainfall. FlowState connects rainfall with land characteristics, runoff, drainage capacity, blockage, accumulated water and predicted risk, then turns that into alerts and safer routing."

---

# 5. Demo safety checklist

Before the SIH presentation:

- Start Flask backend.
- Confirm `/api/health`.
- Confirm frontend loads.
- Confirm at least one weather request succeeds.
- Check that the header shows **Live · Open-Meteo** or **Live · cached**.
- Open Flood Map and wait for zone markers.
- Test one simulation before judges arrive.
- Test Safe Route once.
- Keep the browser console closed during the presentation.
- Keep a backup screenshot/video of the main dashboard in case the internet/API is temporarily unavailable.


## Login Demo

If the judges ask to see authentication, use the built-in SIH demo admin account:
- Email: `admin@admin.com`
- Password: `Admin@123`
- Role shown after login: `Admin`

This is a presentation/demo authentication flow; it is not claimed as production-grade identity management.
