# Live Data Verification

## Weather

FlowState uses Open-Meteo as its external weather provider.

The backend endpoint is:

`GET /api/weather?zone_id=<id>`

The response contains a `weather.source` field:

- `live` = freshly fetched from Open-Meteo
- `cache` = originally fetched from Open-Meteo and currently served from the backend cache
- `demo` = synthetic fallback because the live API call failed

The frontend now displays this status beside the selected-zone weather.

## Flood prediction

The nowcast is computed by the backend. It uses the stored hourly precipitation forecast and the zone/drain data. The ML probability is blended with the rule/physics-based risk engine.

## Important prototype limitation

The Random Forest model is trained on the project's synthetic training dataset. It is a demonstration model and must not be presented as a clinically/operationally validated flood prediction model.

Drain blockage is also simulated/heuristic because the prototype has no physical IoT drain sensors.

## Quick test

Backend:

```powershell
Invoke-RestMethod "http://localhost:5000/api/weather?zone_id=1" | ConvertTo-Json -Depth 10
```

Look for:

```json
"source": "live"
```

or:

```json
"source": "cache"
```

A response with:

```json
"source": "demo"
```

means the live weather call failed and the clearly labelled fallback was used.

## Python 3.14

The final package updates pandas/NumPy/scikit-learn pins so the project can stay on Python 3.14 instead of requiring Python 3.12. Pandas 2.3.3 is documented as generally compatible with Python 3.14.

## Live rainfall and routing (updated)

The dashboard weather request now forces a fresh Open-Meteo request on its polling cycle and ingests the selected zone's hourly rainfall into SQLite. The UI uses Open-Meteo's `current.precipitation` for the current rainfall display and the hourly forecast for the nowcast. Open-Meteo documents current precipitation as a model-based current condition and hourly precipitation as the preceding-hour total.

The Safe Route page now has a working FlowState risk-aware comparison and an **Open route in Google Maps** action. The Google Maps action launches Google Maps Directions using the selected origin and destination. Google Maps URLs do not require an API key. The Google route is Google's own road/traffic route; it does not automatically inherit FlowState's flood-risk avoidance logic.

For an embedded Google route inside FlowState, enable Google Maps Platform Routes API/Maps JavaScript API and provide a restricted API key and billing account. The current prototype deliberately keeps this optional and uses a keyless Google Maps Directions URL for the SIH demo.
