/**
 * src/hooks.js
 * --------------
 * One hook per backend concept, each returning {data, loading, error}.
 * All share the same tiny polling pattern (fetch now, then every
 * intervalMs) via usePolling() below, so every page gets live-refreshing
 * data without repeating the same useEffect boilerplate.
 */

import { useEffect, useRef, useState } from "react";
import {
  fetchZones, fetchFloodRiskSnapshot, fetchWeather, fetchNowcast, fetchNowcastAll,
  fetchAlerts, fetchDrains, fetchExplanation, fetchWeatherAtLocation, fetchRouteGeoJSON,
} from "./api";

function usePolling(fetchFn, deps, intervalMs, enabled = true) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(Boolean(enabled));
  const [error, setError] = useState(null);
  const cancelledRef = useRef(false);

  useEffect(() => {
    cancelledRef.current = false;

    if (!enabled) {
      setLoading(false);
      setError(null);
      return undefined;
    }

    setLoading(true);

    const load = () => {
      fetchFn()
        .then((res) => {
          if (cancelledRef.current) return;
          setData(res.data);
          setError(null);
        })
        .catch((err) => {
          if (!cancelledRef.current) setError(err.message || "Request failed");
        })
        .finally(() => {
          if (!cancelledRef.current) setLoading(false);
        });
    };

    load();
    const interval = intervalMs ? setInterval(load, intervalMs) : null;

    return () => {
      cancelledRef.current = true;
      if (interval) clearInterval(interval);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, enabled]);

  return { data, loading, error };
}

export function useZones() {
  const { data, loading, error } = usePolling(fetchZones, [], null);
  return { zones: data || [], loading, error };
}

export function useFloodRiskSnapshot(intervalMs = 60000) {
  const { data, loading, error } = usePolling(fetchFloodRiskSnapshot, [], intervalMs);
  return { snapshot: data || [], loading, error };
}

export function useWeather(zoneId, intervalMs = 60000) {
  const enabled = Number.isInteger(zoneId) && zoneId > 0;
  const { data, loading, error } = usePolling(
    () => fetchWeather(zoneId),
    [zoneId],
    enabled ? intervalMs : null,
    enabled,
  );
  return { weather: data, loading, error };
}

export function useNowcast(zoneId, intervalMs = 60000) {
  const enabled = Number.isInteger(zoneId) && zoneId > 0;
  const { data, loading, error } = usePolling(
    () => fetchNowcast(zoneId),
    [zoneId],
    enabled ? intervalMs : null,
    enabled,
  );
  return { nowcast: data, loading, error };
}

export function useNowcastAll(intervalMs = 60000) {
  const { data, loading, error } = usePolling(fetchNowcastAll, [], intervalMs);
  return { nowcasts: data || [], loading, error };
}

export function useAlerts(zoneId, intervalMs = 60000) {
  const { data, loading, error } = usePolling(() => fetchAlerts(zoneId), [zoneId], intervalMs);
  return { alerts: data || [], loading, error };
}

export function useDrains(zoneId, intervalMs = 60000) {
  const { data, loading, error } = usePolling(() => fetchDrains(zoneId), [zoneId], intervalMs);
  return { drains: data || [], loading, error };
}

export function useExplanation(zoneId, intervalMs = 60000) {
  const enabled = Number.isInteger(zoneId) && zoneId > 0;
  const { data, loading, error } = usePolling(
    () => fetchExplanation(zoneId),
    [zoneId],
    enabled ? intervalMs : null,
    enabled,
  );
  return { explanation: data, loading, error };
}


export function useLocationWeather(location, intervalMs = 60000) {
  const enabled = Boolean(location && Number.isFinite(location.lat) && Number.isFinite(location.lng));
  const { data, loading, error } = usePolling(
    () => fetchWeatherAtLocation(location.lat, location.lng),
    [location?.lat, location?.lng],
    enabled ? intervalMs : null,
    enabled,
  );
  return { weather: data, loading, error };
}

export function useRouteGeoJSON(offsetMinutes = 0, intervalMs = 60000) {
  const { data, loading, error } = usePolling(() => fetchRouteGeoJSON(offsetMinutes), [offsetMinutes], intervalMs);
  return { roads: data || null, loading, error };
}
