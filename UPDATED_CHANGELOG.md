# FlowState — Updated without redesigning the frontend

## Design-preservation rule
The existing React frontend, CSS, navigation, colours, cards, login flow and page layout were preserved. Only data/API wiring was extended where necessary to expose street-level road risk and the improved routing result.

## Backend updates
- Open-Meteo requests use Asia/Kolkata timestamps.
- Street-level GeoJSON endpoint: `GET /api/routes/geojson`.
- Route risk is synchronised from the current zone nowcast.
- Dijkstra shortest-path routing over `RouteSegment` endpoints.
- Safe mode removes HIGH/SEVERE segments.
- Balanced mode penalises flood risk.
- If no safe connected route exists, the API explicitly returns `UNSAFE` instead of fabricating a safe detour.
- Optional OpenRouteService remains available for base routing when `ROUTING_API_KEY` is configured.
- Added OSM/Overpass importer at `backend/scripts/import_osm.py` for replacing demo road segments with real Gurugram roads.

## Frontend update
No visual redesign. The existing map now additionally consumes `/api/routes/geojson` and draws road segments using the same risk colour system already used by the UI.

## Data honesty
The bundled database remains a demo/prototype dataset. Run the OSM importer and ingest real historical flood observations before claiming municipal-grade street-level accuracy.


## Weather coordinate accuracy update
- Open-Meteo requests now use `cell_selection=nearest` by default.
- Added requested/provider coordinate and elevation metadata.
- Added current timestamp, model, and cell-selection metadata.
- Added structured weather logging for requested coordinate vs provider grid cell.
- Added `fix-gurugram-coordinates` CLI command for repairing an older SQLite DB without deleting project data.
- No artificial temperature offset is applied.
