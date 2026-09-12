/**
 * src/api.js
 * ------------
 * The ONLY file that calls the Flask backend. Every page imports from
 * here instead of hardcoding fetch() calls, so there's one place to
 * change the base URL, one place to see every endpoint this frontend
 * depends on, and one error-handling convention.
 *
 * Configure the backend URL once, at app startup (see main.jsx):
 *   import { configureApi } from './api'
 *   configureApi('http://localhost:5000/api')
 */

let API_BASE_URL = "http://localhost:5000/api";

export function configureApi(baseUrl) {
  API_BASE_URL = baseUrl.replace(/\/$/, "");
}

async function getJson(path) {
  const response = await fetch(`${API_BASE_URL}${path}`);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.error || `GET ${path} failed with status ${response.status}`);
  }
  return response.json();
}

async function postJson(path, payload) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.error || `POST ${path} failed with status ${response.status}`);
  }
  return response.json();
}


// --- Authentication ---
export const loginUser = (email, password) =>
  postJson("/auth/login", { email, password });

// --- Zones ---
export const fetchZones = () => getJson("/zones");
export const fetchZone = (zoneId) => getJson(`/zones/${zoneId}`);

// --- Weather (Phase 3) ---
export const fetchWeather = (zoneId) => getJson(`/weather?zone_id=${zoneId}&refresh=1&ingest=1`);
export const fetchWeatherAtLocation = (lat, lng) =>
  getJson(`/weather/location?lat=${encodeURIComponent(lat)}&lng=${encodeURIComponent(lng)}&refresh=1`);

// --- Current risk snapshot (Phase 5) ---
export const fetchFloodRiskSnapshot = () => getJson("/flood-risk");
export const fetchFloodRiskForZone = (zoneId) => getJson(`/flood-risk/${zoneId}`);

// --- 0-3hr, 7-step nowcast (Phase 5) ---
export const fetchNowcastAll = () => getJson("/nowcast");
export const fetchNowcast = (zoneId) => getJson(`/nowcast/${zoneId}`);

// --- Explainable AI (Phase 6) ---
export const fetchExplanation = (zoneId) => getJson(`/explain/${zoneId}`);

// --- Drains (Phase 7) ---
export const fetchDrains = (zoneId) => getJson(zoneId ? `/drains?zone_id=${zoneId}` : "/drains");
export const fetchDrain = (drainId) => getJson(`/drains/${drainId}`);
export const simulateDrainBlockage = (drainId, blockagePercent) =>
  postJson(`/drains/${drainId}/simulate-blockage`, { blockage_percent: blockagePercent });

// --- Safe route (Phase 8) ---
export const fetchRouteSegments = (zoneId) => getJson(zoneId ? `/routes?zone_id=${zoneId}` : "/routes");
export const fetchSafeRoute = (fromLat, fromLng, toLat, toLng, fromLabel, toLabel) =>
  postJson("/routes/safe", {
    from_lat: fromLat, from_lng: fromLng, to_lat: toLat, to_lng: toLng,
    from_label: fromLabel, to_label: toLabel,
  });

// --- Alerts (Phase 11) ---
export const fetchAlerts = (zoneId) => getJson(zoneId ? `/alerts?zone_id=${zoneId}` : "/alerts");

// --- What-if simulation (Phase 11) ---
export const runSimulation = (zoneId, rainfallMmPerHour, durationHours, drainageBlockagePercent) =>
  postJson("/simulation", {
    zone_id: zoneId,
    rainfall_mm_per_hour: rainfallMmPerHour,
    duration_hours: durationHours,
    drainage_blockage_percent: drainageBlockagePercent,
  });

// Street-level road risk layer. This keeps the existing UI intact while
// replacing zone-only map circles with actual road-segment data.
export const fetchRouteGeoJSON = (offsetMinutes = 0) => getJson(`/routes/geojson?offset_minutes=${offsetMinutes}`);
