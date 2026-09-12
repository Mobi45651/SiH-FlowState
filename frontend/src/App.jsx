import { useEffect, useMemo, useState } from "react";
import {
  Activity, AlertTriangle, Bell, CheckCircle2, ChevronDown,
  CloudLightning, CloudRain, Droplets, Home, Info, Layers3, LocateFixed,
  Map, Menu, Navigation, Route, Search, ShieldAlert, SlidersHorizontal,
  Thermometer, Waves, Wind, X, User, LogIn, UserPlus, Satellite, Radio,
  Maximize2, Minimize2, Play, Pause, MapPin, Clock3, CloudSun,
} from "lucide-react";
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Line, LineChart,
  Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { MapContainer, Marker, Popup, TileLayer, Circle, Polyline, useMap } from "react-leaflet";
import L from "leaflet";
import flowstateLogo from "./assets/flowstate-logo.png";

import { riskColors, toFrontendRisk, toFrontendDrainStatus, drainStatusBadgeTone } from "./riskMapping";
import {
  useZones, useFloodRiskSnapshot, useWeather, useNowcast, useNowcastAll,
  useAlerts, useDrains, useExplanation, useLocationWeather, useRouteGeoJSON,
} from "./hooks";
import { fetchSafeRoute, runSimulation as apiRunSimulation, loginUser } from "./api";

// --- Primary presentation navigation. Analytics is intentionally omitted
// from the judge-facing navigation because its historical/model metrics are
// illustrative rather than backed by a live analytics endpoint. ---
const nav = [
  ["Dashboard", Home], ["Flood Map", Map], ["Forecast", CloudRain],
  ["Safe Route", Route], ["Alert", Bell], ["Simulation", SlidersHorizontal],
  ["Drainage", Waves],
  ["About / FAQ", Info], ["Help / Action", ShieldAlert],
];

const DEFAULT_CENTER = [28.4595, 77.0266];

// ============================================================
// Small shared UI primitives (unchanged from the original design)
// ============================================================

function Icon({ name, size = 18 }) {
  const I = {
    Activity, AlertTriangle, Bell, CheckCircle2, CloudRain, CloudLightning, CloudSun,
    Droplets, Home, Info, Layers3, LocateFixed, Map, Menu, Navigation, Route, Search, ShieldAlert,
    SlidersHorizontal, Thermometer, Waves, Wind, X, User, LogIn, UserPlus, Satellite, Radio,
    Maximize2, Minimize2, Play, Pause, MapPin, Clock3,
  }[name] || Activity;
  return <I size={size} />;
}

function Badge({ children, tone = "blue" }) {
  const tones = {
    blue: "bg-sky-400/10 text-sky-300 border-sky-400/20",
    green: "bg-emerald-400/10 text-emerald-300 border-emerald-400/20",
    yellow: "bg-yellow-400/10 text-yellow-300 border-yellow-400/20",
    orange: "bg-orange-400/10 text-orange-300 border-orange-400/20",
    red: "bg-red-400/10 text-red-300 border-red-400/20",
  };
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-semibold ${tones[tone]}`}>
      {children}
    </span>
  );
}

function Card({ children, className = "" }) {
  return <div className={`rounded-2xl border border-slate-700/60 bg-[#0a2031]/95 ${className}`}>{children}</div>;
}

function SectionTitle({ title, subtitle, action }) {
  return (
    <div className="mb-4 flex items-end justify-between gap-4">
      <div>
        <h2 className="text-lg font-semibold">{title}</h2>
        {subtitle && <p className="mt-1 text-sm text-slate-400">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

function RiskDot({ risk }) {
  return (
    <span
      className="inline-block h-2.5 w-2.5 rounded-full"
      style={{ background: riskColors[risk], boxShadow: `0 0 12px ${riskColors[risk]}88` }}
    />
  );
}

function RiskBadge({ risk }) {
  const tone = risk === "Critical" ? "red" : risk === "High" ? "orange" : risk === "Moderate" ? "yellow" : "green";
  return (
    <Badge tone={tone}>
      <RiskDot risk={risk} />
      {risk}
    </Badge>
  );
}

function LoadingNote({ children = "Loading live data\…" }) {
  return <p className="flex items-center gap-2 text-xs text-slate-500"><span className="h-1.5 w-1.5 animate-pulse rounded-full bg-sky-400" />{children}</p>;
}

function ErrorNote({ message }) {
  return (
    <p className="flex items-center gap-2 rounded-lg border border-red-400/20 bg-red-400/5 px-3 py-2 text-xs text-red-300">
      <AlertTriangle size={13} /> {message}
    </p>
  );
}

// ============================================================
// Weather view-model -- combines a real Zone + its current risk snapshot
// + (optionally) live Open-Meteo detail into the shape every page expects.
// ============================================================

function weatherTheme(weather) {
  if (weather.icon === "storm") return "from-[#08192a] via-[#102a3b] to-[#201a2d]";
  if (weather.icon === "rain") return "from-[#071a2b] via-[#0b2a3c] to-[#10243a]";
  if (weather.icon === "cloud") return "from-[#081a29] via-[#123247] to-[#102334]";
  return "from-[#0b1b2a] via-[#18364a] to-[#172b38]";
}

function WeatherIcon({ weather, size = 20 }) {
  const name = weather.icon === "storm" ? "CloudLightning" : weather.icon === "rain" ? "CloudRain" : weather.icon === "cloud" ? "CloudSun" : "CloudSun";
  return <Icon name={name} size={size} />;
}

function localRiskFromWeather(weatherResp) {
  const current = weatherResp?.weather?.current || {};
  const rain = Number(current.precipitation);
  const probability = Number(weatherResp?.weather?.hourly?.[0]?.precipitation_probability);
  const rainMm = Number.isFinite(rain) ? rain : 0;
  const prob = Number.isFinite(probability) ? probability : 0;
  // This is a transparent WEATHER-BASED screening for an arbitrary GPS
  // location. Full flood risk still needs local terrain/drainage data.
  if (rainMm >= 25 || (rainMm >= 15 && prob >= 70)) return "Critical";
  if (rainMm >= 10 || (rainMm >= 7 && prob >= 60)) return "High";
  if (rainMm >= 2 || (rainMm >= 1 && prob >= 50)) return "Moderate";
  return "Low";
}

function buildWeatherView(zone, riskEntry, weatherResp, locationWeatherResp = null) {
  // When no monitored zone is selected, use the browser's actual GPS
  // coordinates. This prevents a seeded demo zone from becoming the
  // default source for the user's weather.
  if (!zone) {
    if (!locationWeatherResp?.weather) {
      return {
        zoneId: null, city: "Your Location", condition: "Loading…", temp: "--", humidity: "--", wind: "--",
        rainfall: 0, rainfallSource: "loading", risk: "Low", icon: "clear",
        note: "Getting live weather for your current location…", source: null,
        sourceLabel: "Location weather loading", isLocation: true,
      };
    }
    const current = locationWeatherResp.weather.current || {};
    const rainValue = Number(current.precipitation);
    const rainfall = Number.isFinite(rainValue) ? Math.round(rainValue * 10) / 10 : 0;
    const risk = localRiskFromWeather(locationWeatherResp);
    const icon = rainfall > 15 ? "storm" : rainfall > 2 ? "rain" : rainfall > 0 ? "cloud" : "clear";
    const condition = icon === "storm" ? "Heavy Rain" : icon === "rain" ? "Rain" : icon === "cloud" ? "Cloudy" : "Clear";
    const source = locationWeatherResp.weather.source || null;
    const sourceLabel = source === "live" ? "Live · Open-Meteo" : source === "cache" ? "Live · cached" : "Demo fallback";
    const note = risk === "Critical"
      ? "Heavy rainfall detected at your location. Treat this as a weather-based flood screening and follow local emergency guidance."
      : risk === "High"
      ? "Rainfall is elevated at your location. Monitor local flooding and drainage conditions."
      : risk === "Moderate"
      ? "Moderate rain conditions detected at your location; continue monitoring."
      : "Current weather at your location indicates low rainfall-based flood pressure.";
    return {
      zoneId: null,
      city: "Your Location",
      condition,
      temp: Number.isFinite(Number(current.temperature_2m)) ? Math.round(Number(current.temperature_2m)) : "--",
      humidity: Number.isFinite(Number(current.relative_humidity_2m)) ? Math.round(Number(current.relative_humidity_2m)) : "--",
      wind: Number.isFinite(Number(current.wind_speed_10m)) ? Math.round(Number(current.wind_speed_10m)) : "--",
      rainfall,
      rainfallSource: "live-current",
      risk,
      icon,
      note,
      source,
      sourceLabel,
      isLocation: true,
      location: locationWeatherResp.location,
    };
  }

  const currentWeather = weatherResp?.weather?.current || {};
  const liveRain = Number.isFinite(Number(currentWeather.precipitation))
    ? Number(currentWeather.precipitation)
    : null;
  const rainfall = liveRain !== null
    ? Math.round(liveRain * 10) / 10
    : (riskEntry ? Math.round(riskEntry.rainfall_mm) : 0);
  const risk = riskEntry ? toFrontendRisk(riskEntry.risk_category) : "Low";
  const icon = rainfall > 60 ? "storm" : rainfall > 15 ? "rain" : rainfall > 0 ? "cloud" : "clear";
  const condition = icon === "storm" ? "Heavy Rain" : icon === "rain" ? "Rain" : icon === "cloud" ? "Cloudy" : "Clear";
  // IMPORTANT: use Open-Meteo's CURRENT observations for the live card.
  // The hourly array is reserved for the forecast graph; hourly[0] is not
  // guaranteed to represent the current local time.
  const current = weatherResp?.weather?.current || {};
  const weatherSource = weatherResp?.weather?.source || null;
  const sourceLabel = weatherSource === "live"
    ? "Live · Open-Meteo"
    : weatherSource === "cache"
    ? "Live · cached"
    : weatherSource === "demo"
    ? "Demo fallback"
    : "Weather loading";
  const note = risk === "Critical"
    ? "Flood risk is severe in this zone — monitor closely and avoid low-lying roads."
    : risk === "High"
    ? "Rainfall is elevated and drainage is under strain in this zone."
    : risk === "Moderate"
    ? "Conditions are being monitored; risk is moderate."
    : "Conditions are stable with low flood probability.";
  return {
    zoneId: zone.id,
    city: zone.name,
    condition,
    temp: Number.isFinite(Number(current.temperature_2m))
      ? Math.round(Number(current.temperature_2m))
      : "--",
    humidity: Number.isFinite(Number(current.relative_humidity_2m))
      ? Math.round(Number(current.relative_humidity_2m))
      : "--",
    wind: Number.isFinite(Number(current.wind_speed_10m))
      ? Math.round(Number(current.wind_speed_10m))
      : "--",
    rainfall,
    rainfallSource: liveRain !== null ? "live-current" : "nowcast",
    risk,
    icon,
    note,
    source: weatherSource,
    sourceLabel,
    isLocation: false,
  };
}

// ============================================================
// Dashboard
// ============================================================

function Dashboard({ go, weather, snapshot, selectedZoneId }) {
  const distribution = useMemo(() => {
    const counts = { Critical: 0, High: 0, Moderate: 0, Low: 0 };
    snapshot.forEach((s) => { counts[toFrontendRisk(s.risk_category)] += 1; });
    return counts;
  }, [snapshot]);
  const maxCount = Math.max(1, ...Object.values(distribution));

  return (
    <div className="space-y-6">
      <div className="grid gap-5 xl:grid-cols-[1.7fr_0.72fr]">
        <Card className="overflow-hidden">
          <div className="flex items-center justify-between border-b border-slate-700/60 px-5 py-4">
            <div>
              <h2 className="font-semibold">Live Flood Map</h2>
              <p className="mt-1 text-xs text-slate-500">{weather.city} · current risk visualization</p>
            </div>
            <button onClick={() => go("Flood Map")} className="rounded-lg border border-slate-700 px-3 py-2 text-xs text-slate-300 hover:border-sky-400/30 hover:text-sky-300">
              Open map →
            </button>
          </div>
          <div className="h-[470px]"><FloodMap compact showTimeline={false} selectedZoneId={selectedZoneId} /></div>
        </Card>

        <Card className="p-6">
          <div className="flex items-start justify-between">
            <div>
              <div className="flex items-center gap-2 text-xs font-semibold tracking-wide text-slate-500">
                <span className="h-2 w-2 animate-pulse rounded-full bg-red-400" /> FLOOD RISK STATUS
              </div>
              <div className="mt-3 text-5xl font-black tracking-tight md:text-6xl" style={{ color: riskColors[weather.risk] }}>
                {weather.risk.toUpperCase()}
              </div>
            </div>
            <div className="rounded-xl bg-orange-400/10 p-3 text-orange-400"><ShieldAlert size={28} /></div>
          </div>
          <p className="mt-3 text-sm leading-6 text-slate-300">{weather.note}</p>
          <div className="mt-5 space-y-3">
            <Metric label="Rainfall" value={`${weather.rainfall} mm/hr`} />
            <Metric label={weather.isLocation ? "Location source" : "Zones monitored"} value={weather.isLocation ? "GPS" : String(snapshot.length || "--")} />
            <Metric label={weather.isLocation ? "Flood zones" : "Critical zones now"} value={weather.isLocation ? "Local screening" : String(distribution.Critical)} />
          </div>
        </Card>
      </div>

      <div className="grid gap-5 xl:grid-cols-2">
        <Card className="p-6">
          <SectionTitle title={weather.isLocation ? "Local Risk Screening" : "Flood Risk Overview"} subtitle={weather.isLocation ? "Rainfall-based screening at your current GPS location" : "Current risk distribution across monitored zones"} />
          <div className="grid grid-cols-2 gap-3">
            {[["Critical", "red"], ["High", "orange"], ["Moderate", "yellow"], ["Low", "green"]].map(([label, tone]) => (
              <div key={label} className="rounded-xl border border-slate-700/50 bg-[#0d293c] p-4">
                <div className={tone === "red" ? "text-sm text-red-300" : tone === "orange" ? "text-sm text-orange-300" : tone === "yellow" ? "text-sm text-yellow-300" : "text-sm text-emerald-300"}>
                  {label}
                </div>
                <div className="mt-1 text-2xl font-bold">{distribution[label]}</div>
                <div className="mt-3 h-1.5 rounded-full bg-slate-800">
                  <div
                    className={`h-full rounded-full ${tone === "red" ? "bg-red-400" : tone === "orange" ? "bg-orange-400" : tone === "yellow" ? "bg-yellow-400" : "bg-emerald-400"}`}
                    style={{ width: `${Math.round((distribution[label] / maxCount) * 100)}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </Card>

        <Card className="p-6">
          <SectionTitle title="Live Conditions" subtitle={`Observed conditions in ${weather.city}`} action={<Badge tone="green">Live</Badge>} />
          <div className="grid grid-cols-2 gap-3">
            <Weather icon={<WeatherIcon weather={weather} />} label="Weather" value={weather.condition} detail="Current" />
            <Weather icon={<Thermometer size={18} />} label="Temperature" value={`${weather.temp}\u00b0C`} detail="Observed" />
            <Weather icon={<Droplets size={18} />} label="Humidity" value={`${weather.humidity}%`} detail="Current" />
            <Weather icon={<Wind size={18} />} label="Wind Speed" value={`${weather.wind} km/h`} detail="Current wind" />
          </div>
        </Card>
      </div>

      <div className="grid gap-5 xl:grid-cols-2">
        <AlertsPreview go={go} />
        <Actions weather={weather} />
      </div>

      <div className="flex items-center justify-between border-t border-slate-700/60 pt-4 text-xs text-slate-500">
        <span className="flex items-center gap-2"><Clock3 size={14} className="text-sky-400" /> Live backend data</span>
        <span>FlowState · {weather.city} live monitoring</span>
      </div>
    </div>
  );
}

function Metric({ label, value }) {
  return <div><p className="text-xs text-slate-500">{label}</p><p className="mt-1 text-sm font-semibold">{value}</p></div>;
}

function Weather({ icon, label, value, detail }) {
  return (
    <div className="rounded-xl border border-slate-700/50 bg-[#0d293c] p-4">
      <div className="mb-3 grid h-9 w-9 place-items-center rounded-lg bg-sky-400/10 text-sky-400">{icon}</div>
      <div className="text-xl font-bold capitalize">{value}</div>
      <div className="mt-1 text-sm text-slate-300">{label}</div>
      <div className="mt-1 text-xs text-slate-500">{detail}</div>
    </div>
  );
}

function AlertsPreview({ go }) {
  const { alerts, loading, error } = useAlerts(null, 60000);
  const top = alerts.slice(0, 3);
  return (
    <Card className="p-6">
      <SectionTitle title="Recent Alerts" action={<button onClick={() => go("Alert")} className="text-sm text-sky-400">View all →</button>} />
      {loading && !alerts.length && <LoadingNote>Loading alerts\…</LoadingNote>}
      {error && <ErrorNote message={error} />}
      <div className="space-y-3">
        {top.map((a) => {
          const risk = toFrontendRisk(a.severity);
          return (
            <div key={a.id} className="flex gap-3 rounded-xl border border-slate-700/50 bg-[#0d293c] p-4">
              <RiskDot risk={risk} />
              <div>
                <div className="flex flex-wrap items-center gap-2 text-sm font-semibold">
                  {a.alert_type.replace(/_/g, " ")}
                  <Badge tone={risk === "Critical" ? "red" : risk === "High" ? "orange" : risk === "Moderate" ? "yellow" : "green"}>{a.severity}</Badge>
                </div>
                <div className="mt-1 text-xs text-slate-500">{a.message}</div>
              </div>
            </div>
          );
        })}
        {!loading && !top.length && <p className="text-sm text-slate-500">No active alerts right now.</p>}
      </div>
    </Card>
  );
}

function Actions({ weather }) {
  const actions = [];
  if (weather.risk === "Critical" || weather.risk === "High") {
    actions.push([`Avoid ${weather.city}`, `Flood probability elevated \u2014 ${weather.risk} risk`, "red"]);
    actions.push(["Check Safe Route", "Get a route that avoids high-risk zones", "orange"]);
  }
  actions.push(["Review drainage status", "See which drains are under strain", "yellow"]);
  actions.push(["Open Alert Center", "See every active alert across all zones", "blue"]);

  return (
    <Card className="p-6">
      <SectionTitle title="Recommended Actions" subtitle="Based on current live conditions" />
      <div className="space-y-3">
        {actions.map(([title, detail], i) => (
          <div key={title} className="flex items-center gap-4 rounded-xl border border-slate-700/50 bg-[#0d293c] p-4">
            <span className="text-xs font-bold text-sky-400">0{i + 1}</span>
            <div><div className="text-sm font-semibold">{title}</div><div className="mt-1 text-xs text-slate-500">{detail}</div></div>
          </div>
        ))}
      </div>
    </Card>
  );
}

// ============================================================
// Flood Map -- now driven entirely by real zones + real nowcasts
// ============================================================

function MapControls({ onLocate }) {
  const map = useMap();
  return (
    <div className="absolute right-4 top-4 z-[500] flex flex-col overflow-hidden rounded-xl border border-slate-700/80 bg-[#071a29]/95 shadow-xl">
      <button onClick={() => map.zoomIn()} className="grid h-10 w-10 place-items-center border-b border-slate-700/70 text-lg hover:bg-sky-400/10 hover:text-sky-300">+</button>
      <button onClick={() => map.zoomOut()} className="grid h-10 w-10 place-items-center border-b border-slate-700/70 text-lg hover:bg-sky-400/10 hover:text-sky-300">-</button>
      <button onClick={onLocate} className="grid h-10 w-10 place-items-center hover:bg-sky-400/10 hover:text-sky-300"><LocateFixed size={16} /></button>
    </div>
  );
}

function MapViewport({ request, center, zoom = 12, animate = true }) {
  const map = useMap();

  useEffect(() => {
    if (!center || center.length !== 2) return;
    map.setView(center, map.getZoom(), { animate: false });
    const timer = window.setTimeout(() => map.invalidateSize(), 80);
    return () => window.clearTimeout(timer);
  }, [map, center?.[0], center?.[1]]);

  useEffect(() => {
    if (!request || !center || center.length !== 2) return;
    map.setView(center, zoom, { animate });
    const timer = window.setTimeout(() => map.invalidateSize(), 250);
    return () => window.clearTimeout(timer);
  }, [request, map, center, zoom, animate]);

  return null;
}

function UserLocationOverlay({ location, accuracy = 0 }) {
  if (!location) return null;
  return (
    <>
      <Circle
        center={location}
        radius={Math.max(accuracy || 0, 40)}
        pathOptions={{ color: "#38bdf8", fillColor: "#38bdf8", fillOpacity: 0.08, weight: 1 }}
      />
      <Marker
        position={location}
        icon={L.divIcon({
          className: "",
          html: `<div style="width:18px;height:18px;border-radius:50%;background:#38bdf8;border:3px solid white;box-shadow:0 0 0 5px rgba(56,189,248,.22),0 0 18px rgba(56,189,248,.65)"></div>`,
          iconSize: [18, 18],
          iconAnchor: [9, 9],
        })}
      >
        <Popup><b>Your location</b><div style={{ marginTop: 4 }}>Map centered on your current device location.</div></Popup>
      </Marker>
    </>
  );
}

function FloodMap({ compact = false, mapStyle = "street", liveRequest = 0, showTimeline = true, selectedZoneId = null }) {
  const { zones } = useZones();
  const { nowcasts } = useNowcastAll(60000);
  const [activeLayers, setActiveLayers] = useState({ risk: true, rainfall: false, drainage: false });
  const [layersOpen, setLayersOpen] = useState(true);
  const [timeIndex, setTimeIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [timelineOpen, setTimelineOpen] = useState(true);
  const [userLocation, setUserLocation] = useState(null);
  const [locationAccuracy, setLocationAccuracy] = useState(0);
  const [locationError, setLocationError] = useState(null);
  const [locationRequested, setLocationRequested] = useState(false);

  const zoneCenter = useMemo(() => (
    zones.length
      ? [
          zones.reduce((s, z) => s + z.latitude, 0) / zones.length,
          zones.reduce((s, z) => s + z.longitude, 0) / zones.length,
        ]
      : DEFAULT_CENTER
  ), [zones]);

  const selectedZone = zones.find((z) => z.id === selectedZoneId) || null;
  const selectedZoneCenter = selectedZone
    ? [Number(selectedZone.latitude), Number(selectedZone.longitude)]
    : null;

  // A selected dropdown zone always takes priority over GPS for the map.
  // If no zone is selected, fall back to the user's GPS location, then the
  // center of the monitored zone network.
  const center = selectedZoneCenter || userLocation || zoneCenter;

  const requestUserLocation = () => {
    if (!navigator.geolocation) {
      setLocationError("Geolocation is not supported by this browser.");
      return;
    }
    setLocationRequested(true);
    setLocationError(null);
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setUserLocation([position.coords.latitude, position.coords.longitude]);
        setLocationAccuracy(position.coords.accuracy || 0);
        setLocationRequested(false);
      },
      (error) => {
        setLocationRequested(false);
        setLocationError(
          error.code === 1
            ? "Location permission was denied. Allow location access to center the map on you."
            : "Unable to determine your location. Showing the monitored-zone area instead."
        );
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 30000 }
    );
  };

  useEffect(() => {
    // Ask once when the map opens. The browser will show its normal permission prompt.
    requestUserLocation();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const timeline = (nowcasts[0]?.forecast || []).map((step) => ({
    offset: step.offset_minutes,
    time: step.time,
    label: step.offset_minutes === 0 ? "Now" : `+${step.offset_minutes}m`,
  }));
  const stepCount = Math.max(1, timeline.length);
  const currentOffset = timeline[timeIndex]?.offset ?? 0;
  const { roads } = useRouteGeoJSON(currentOffset, 60000);

  useEffect(() => {
    if (!playing) return;
    const id = setInterval(() => setTimeIndex((i) => {
      if (i >= stepCount - 1) { setPlaying(false); return i; }
      return i + 1;
    }), 1800);
    return () => clearInterval(id);
  }, [playing, stepCount]);

  const toggleLayer = (k) => setActiveLayers((v) => ({ ...v, [k]: !v[k] }));
  const tileUrl = mapStyle === "satellite"
    ? "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
    : "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png";

  const stepFor = (zone) => {
    const forecast = nowcasts.find((n) => n.zone_id === zone.id)?.forecast;
    return forecast ? forecast[Math.min(timeIndex, forecast.length - 1)] : null;
  };
  const current = timeline[timeIndex] || { time: "--", label: "Now" };

  return (
    <div className="relative h-full w-full">
      <MapContainer className="flowstate-map" center={center} zoom={compact ? 11 : 12} scrollWheelZoom zoomControl={false}>
        <TileLayer attribution={mapStyle === "satellite" ? "Tiles \u00a9 Esri" : "&copy; OpenStreetMap contributors"} url={tileUrl} />
        <MapViewport
          request={selectedZoneId ? `${selectedZoneId}-${liveRequest}` : liveRequest}
          center={center}
          zoom={selectedZone ? 14 : (userLocation ? 14 : (compact ? 11 : 12))}
          animate={Boolean(selectedZone || userLocation)}
        />
        <UserLocationOverlay location={userLocation} accuracy={locationAccuracy} />
        {activeLayers.risk && roads?.features?.map((feature) => {
          const p = feature.properties || {};
          const risk = toFrontendRisk(p.risk_category || p.risk || "LOW");
          const coords = (feature.geometry?.coordinates || []).map(([lng, lat]) => [lat, lng]);
          if (coords.length < 2) return null;
          return (
            <Polyline key={`road-${p.id}`} positions={coords} pathOptions={{ color: riskColors[risk], weight: 5, opacity: 0.92 }}>
              <Popup>
                <b>{p.road_name || "Road segment"}</b>
                <div style={{ marginTop: 5 }}>{risk} risk</div>
                <div>Length: {p.distance_km ?? "--"} km</div>
                <div>{p.is_flood_prone ? "Avoid during high/severe risk" : "Currently passable"}</div>
              </Popup>
            </Polyline>
          );
        })}
        {zones.map((z) => {
          const step = stepFor(z);
          const risk = toFrontendRisk(step?.risk_category || "LOW");
          const probability = step ? Math.round(step.flood_probability * 100) : 0;
          const depth = step ? step.water_depth_cm : 0;
          const intensity = Math.min(0.36, 0.12 + (probability / 100) * 0.22);
          return (
            <div key={z.id}>
              {activeLayers.risk && (
                <Circle center={[z.latitude, z.longitude]} radius={1300} pathOptions={{ color: riskColors[risk], fillColor: riskColors[risk], fillOpacity: intensity, weight: 2 }} />
              )}
              {activeLayers.rainfall && (
                <Circle center={[z.latitude, z.longitude]} radius={800 + (step?.rainfall_mm || 0) * 20} pathOptions={{ color: "#38bdf8", fillColor: "#38bdf8", fillOpacity: 0.08, weight: 1, dashArray: "4 5" }} />
              )}
              <Marker
                position={[z.latitude, z.longitude]}
                icon={L.divIcon({
                  className: "",
                  html: `<div style="width:14px;height:14px;border-radius:50%;background:${riskColors[risk]};border:2px solid white;box-shadow:0 0 12px ${riskColors[risk]}88"></div>`,
                  iconSize: [14, 14], iconAnchor: [7, 7],
                })}
              >
                <Popup>
                  <b>{z.name}</b>
                  <div style={{ marginTop: 5 }}>{risk} risk · {probability}% probability</div>
                  <div>Predicted depth: {depth} cm</div>
                  <div style={{ marginTop: 5, color: "#38bdf8" }}>Forecast: {current.time}</div>
                </Popup>
              </Marker>
            </div>
          );
        })}
        {activeLayers.drainage && zones.length > 1 && (
          <Polyline positions={zones.map((z) => [z.latitude, z.longitude])} pathOptions={{ color: "#a78bfa", weight: 4, opacity: 0.9 }} />
        )}
        <MapControls onLocate={requestUserLocation} />
      </MapContainer>

      {locationRequested && (
        <div className="absolute right-16 top-4 z-[500] rounded-lg border border-sky-400/20 bg-[#071a29]/95 px-3 py-2 text-[11px] text-sky-200 shadow-xl">
          Finding your location…
        </div>
      )}
      {locationError && (
        <button
          onClick={requestUserLocation}
          className="absolute right-16 top-4 z-[500] max-w-xs rounded-lg border border-amber-400/20 bg-[#071a29]/95 px-3 py-2 text-left text-[11px] text-amber-200 shadow-xl"
          title="Try location again"
        >
          {locationError}
        </button>
      )}

      <div className="absolute left-4 top-4 z-[500]">
        <button onClick={() => setLayersOpen((v) => !v)} className="flex items-center gap-2 rounded-xl border border-slate-700/80 bg-[#071a29]/95 px-4 py-3 text-xs font-semibold shadow-xl hover:text-sky-300">
          <Layers3 size={16} className="text-sky-400" />Layers <span className="text-slate-500">{layersOpen ? "\u25b2" : "\u25bc"}</span>
        </button>
        {layersOpen && (
          <div className="mt-2 w-56 rounded-xl border border-slate-700/80 bg-[#071a29]/95 p-4 shadow-xl">
            <div className="mb-3 text-[10px] font-semibold tracking-wider text-slate-500">MAP OVERLAYS</div>
            {[["risk", "Flood risk zones"], ["rainfall", "Rainfall intensity"], ["drainage", "Drainage network"]].map(([key, label]) => (
              <button key={key} onClick={() => toggleLayer(key)} className="mb-1 flex w-full items-center gap-3 rounded-lg px-2.5 py-2.5 text-xs text-slate-300 hover:bg-white/5">
                <span className={`grid h-4 w-4 place-items-center rounded border ${activeLayers[key] ? "border-sky-400 bg-sky-400 text-[#061421]" : "border-slate-600"}`}>
                  {activeLayers[key] && <CheckCircle2 size={11} />}
                </span>
                {label}
              </button>
            ))}
          </div>
        )}
      </div>

      {showTimeline && !timelineOpen && (
        <button onClick={() => setTimelineOpen(true)} className="absolute bottom-3 right-3 z-[500] flex items-center gap-2 rounded-xl border border-slate-700/80 bg-[#071a29]/96 px-3 py-2 text-xs font-semibold text-slate-300 shadow-xl hover:text-sky-300">
          <Maximize2 size={14} /> Show timeline
        </button>
      )}

      {showTimeline && timelineOpen && timeline.length > 0 && (
        <div className={`absolute bottom-3 left-3 right-3 z-[500] rounded-xl border border-slate-700/80 bg-[#071a29]/96 shadow-2xl backdrop-blur ${compact ? "p-3" : "p-4"}`}>
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2 text-xs font-semibold"><Activity size={14} className="text-sky-400" />FLOOD PREDICTION TIMELINE</div>
          </div>
          <div className="flex items-center gap-3">
            <button onClick={() => setPlaying((v) => !v)} className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-sky-500 text-white">
              {playing ? <Pause size={14} /> : <Play size={14} />}
            </button>
            <input aria-label="Prediction timeline" type="range" min="0" max={stepCount - 1} value={timeIndex} onChange={(e) => { setPlaying(false); setTimeIndex(+e.target.value); }} className="w-full accent-sky-400" />
            <button onClick={() => setTimelineOpen(false)} className="grid h-8 w-8 shrink-0 place-items-center rounded-lg border border-slate-700 text-slate-300" title="Minimize timeline" aria-label="Minimize timeline">
              <Minimize2 size={14} />
            </button>
          </div>
          <div className="mt-1 flex justify-between text-[9px] text-slate-500">
            {timeline.map((t, i) => (
              <button key={t.label} onClick={() => { setPlaying(false); setTimeIndex(i); }} className={i === timeIndex ? "font-semibold text-sky-300" : ""}>
                {t.label}<br /><span>{t.time}</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ============================================================
// Flood Map page
// ============================================================

function MapPage({ weather, selectedZoneId }) {
  const [style, setStyle] = useState("street");
  const [liveRequest, setLiveRequest] = useState(0);
  return (
    <div className="space-y-5">
      <SectionTitle
        title="Flood Map"
        subtitle="Interactive flood intelligence across all monitored zones"
        action={(
          <div className="flex gap-2">
            <button onClick={() => setStyle("satellite")} className={`flex items-center gap-2 rounded-lg border px-3 py-2 text-xs ${style === "satellite" ? "border-sky-400/40 bg-sky-400/10 text-sky-300" : "border-slate-700 bg-[#0a2031] text-slate-300"}`}>
              <Satellite size={14} />Satellite
            </button>
            <button onClick={() => { setStyle("street"); setLiveRequest((x) => x + 1); }} className={`flex items-center gap-2 rounded-lg border px-3 py-2 text-xs ${style === "street" ? "border-sky-400/40 bg-sky-400/10 text-sky-300" : "border-slate-700 bg-[#0a2031] text-slate-300"}`}>
              <Radio size={14} />Live
            </button>
          </div>
        )}
      />
      <Card className="h-[calc(100vh-255px)] min-h-[620px] overflow-hidden"><FloodMap mapStyle={style} liveRequest={liveRequest} selectedZoneId={selectedZoneId} /></Card>
      <div className="grid gap-4 md:grid-cols-3">
        <Card className="p-5">
          <div className="text-xs tracking-wider text-slate-500">SELECTED ZONE RISK</div>
          <div className="mt-2 text-3xl font-black" style={{ color: riskColors[weather.risk] }}>{weather.risk}</div>
          <p className="mt-2 text-xs text-slate-400">{weather.city}</p>
        </Card>
        <Card className="p-5">
          <div className="text-xs tracking-wider text-slate-500">LIVE WEATHER</div>
          <div className="mt-3 flex items-center gap-3">
            <div className="rounded-xl bg-sky-400/10 p-3 text-sky-400"><WeatherIcon weather={weather} /></div>
            <div><div className="text-2xl font-bold">{weather.rainfall} mm/hr</div><div className="text-xs text-slate-500">{weather.condition}</div></div>
          </div>
          <div className="mt-4 grid grid-cols-2 gap-2 text-xs">
            <div className="rounded-lg bg-[#0d293c] p-3"><span className="text-slate-500">Temp</span><br />{weather.temp}\u00b0C</div>
            <div className="rounded-lg bg-[#0d293c] p-3"><span className="text-slate-500">Humidity</span><br />{weather.humidity}%</div>
          </div>
        </Card>
        <Card className="p-5">
          <div className="text-xs tracking-wider text-slate-500">DATA SOURCE</div>
          <div className="mt-2 text-xl font-bold">Live backend</div>
          <div className="mt-1 text-xs text-slate-400">Nowcast refreshes every 60s</div>
        </Card>
      </div>
    </div>
  );
}

// ============================================================
// Forecast -- real nowcast + real explainability (Phase 6, new)
// ============================================================

function Forecast({ weather }) {
  const [timelineOpen, setTimelineOpen] = useState(true);
  const { nowcast, loading, error } = useNowcast(weather.zoneId);
  const { explanation } = useExplanation(weather.zoneId);

  const chartData = (nowcast?.forecast || []).map((s) => ({
    time: s.time, rain: s.rainfall_mm, risk: Math.round(s.flood_probability * 100),
  }));

  return (
    <div className="space-y-7">
      <SectionTitle
        title="AI Flood Forecast"
        subtitle={`Prediction horizon for ${weather.city} · 0-3 hour nowcast`}
        action={<Badge tone="green">Model online</Badge>}
      />
      {loading && !nowcast && <LoadingNote>Loading forecast\…</LoadingNote>}
      {error && <ErrorNote message={error} />}

      {nowcast && (
        <>
          <div className="grid gap-5 lg:grid-cols-3">
            <Card className="p-6 lg:col-span-2">
              <h3 className="font-semibold">Rainfall & Flood Probability</h3>
              <div className="mt-5 h-72">
                <ResponsiveContainer>
                  <AreaChart data={chartData}>
                    <CartesianGrid stroke="#294052" strokeDasharray="3 3" />
                    <XAxis dataKey="time" stroke="#64748b" fontSize={11} />
                    <YAxis stroke="#64748b" fontSize={11} />
                    <Tooltip contentStyle={{ background: "#071a29", border: "1px solid #294052", borderRadius: 10 }} />
                    <Area type="monotone" dataKey="rain" stroke="#38bdf8" fill="#38bdf8" fillOpacity={0.12} />
                    <Line type="monotone" dataKey="risk" stroke="#fb923c" strokeWidth={3} />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </Card>
            <Card className="p-6">
              <h3 className="font-semibold">0&ndash;3 Hour Steps</h3>
              <div className="mt-5 space-y-3">
                {nowcast.forecast.map((s) => (
                  <div key={s.offset_minutes} className="flex items-center gap-3 rounded-xl bg-[#0d293c] p-3">
                    <span className="w-14 text-xs text-slate-500">{s.time}</span>
                    <RiskDot risk={toFrontendRisk(s.risk_category)} />
                    <span className="flex-1 text-sm">{toFrontendRisk(s.risk_category)}</span>
                    <span className="text-xs font-semibold text-slate-400">{Math.round(s.flood_probability * 100)}%</span>
                  </div>
                ))}
              </div>
            </Card>
          </div>

          <Card className="p-6">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="font-semibold">Prediction Timeline</h3>
                <p className="mt-1 text-xs text-slate-500">Current moment is included as <b className="text-sky-300">Now</b>.</p>
              </div>
              <div className="flex items-center gap-2">
                <Badge tone="blue">{nowcast.forecast[0].model_version}</Badge>
                <button onClick={() => setTimelineOpen((v) => !v)} className="grid h-8 w-8 place-items-center rounded-lg border border-slate-700 text-slate-300" title={timelineOpen ? "Minimize timeline" : "Show timeline"}>
                  {timelineOpen ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
                </button>
              </div>
            </div>
            {timelineOpen && (
              <div className="mt-7 grid grid-cols-4 gap-2 md:grid-cols-7">
                {nowcast.forecast.map((s, i) => (
                  <div key={s.offset_minutes} className={`relative rounded-xl border p-4 text-center ${i === 0 ? "border-sky-400/40 bg-sky-400/10" : "border-slate-700/50 bg-[#0d293c]"}`}>
                    <div className="text-xs text-slate-500">{s.offset_minutes === 0 ? "Now" : `+${s.offset_minutes}m`}</div>
                    {i === 0 && <div className="mx-auto mt-2 w-fit rounded-full bg-sky-500 px-2 py-0.5 text-[9px] font-bold text-white">NOW</div>}
                    <div className="mt-3 flex justify-center"><RiskDot risk={toFrontendRisk(s.risk_category)} /></div>
                    <div className="mt-2 text-sm font-semibold">{toFrontendRisk(s.risk_category)}</div>
                    <div className="mt-1 text-xs text-slate-400">{Math.round(s.flood_probability * 100)}%</div>
                  </div>
                ))}
              </div>
            )}
          </Card>

          {explanation && (
            <Card className="p-6">
              <h3 className="font-semibold">Why This Risk Level</h3>
              <p className="mt-2 text-sm leading-6 text-slate-300">{explanation.explanation_text}</p>
              <div className="mt-5 space-y-3">
                {explanation.breakdown.slice(0, 5).map((f) => (
                  <div key={f.factor} className="flex items-center gap-3 text-xs">
                    <span className="w-32 shrink-0 text-slate-400">{f.factor}</span>
                    <div className="h-2 flex-1 overflow-hidden rounded-full bg-slate-800">
                      <div className="h-full rounded-full bg-gradient-to-r from-sky-400 to-cyan-300" style={{ width: `${f.severity_percent}%` }} />
                    </div>
                    <span className="w-10 text-right font-semibold text-sky-300">{f.severity_percent}%</span>
                  </div>
                ))}
              </div>
              <p className="mt-4 text-[11px] italic text-slate-500">{explanation.disclaimer}</p>
            </Card>
          )}
        </>
      )}
    </div>
  );
}

// ============================================================
// Safe Route -- real 2-route comparison from the backend
// ============================================================

function SafeRoute({ weather, zones }) {
  const [fromId, setFromId] = useState("");
  const [toId, setToId] = useState("");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    // Keep both selectors explicitly unselected until the user chooses them.
    // This fixes the first-position option feeling unclickable because it was
    // previously preselected by default.
    if (zones.length && fromId && !zones.some((z) => String(z.id) === fromId)) setFromId("");
    if (zones.length && toId && !zones.some((z) => String(z.id) === toId)) setToId("");
  }, [zones, fromId, toId]);

  const findRoute = () => {
    const from = zones.find((z) => String(z.id) === fromId);
    const to = zones.find((z) => String(z.id) === toId);
    if (!from || !to || from.id === to.id) {
      setError("Choose two different monitored zones.");
      return;
    }
    setLoading(true);
    setError(null);
    fetchSafeRoute(from.latitude, from.longitude, to.latitude, to.longitude, from.name, to.name)
      .then((res) => setResult(res.data))
      .catch((err) => setError(err.message || "Failed to compute route"))
      .finally(() => setLoading(false));
  };

  const openGoogleMaps = (mode = "driving") => {
    const from = zones.find((z) => String(z.id) === fromId);
    const to = zones.find((z) => String(z.id) === toId);
    if (!from || !to) return;
    const params = new URLSearchParams({
      api: "1",
      origin: `${from.latitude},${from.longitude}`,
      destination: `${to.latitude},${to.longitude}`,
      travelmode: mode,
    });
    window.open(`https://www.google.com/maps/dir/?${params.toString()}`, "_blank", "noopener,noreferrer");
  };

  const RouteCard = ({ title, route, highlight }) => route && (
    <div className={`rounded-xl border p-4 ${highlight ? "border-sky-400/40 bg-sky-400/5" : "border-slate-700/60 bg-[#0d293c]"}`}>
      <div className="flex items-center justify-between">
        <span className="font-semibold">{title}</span>
        <RiskBadge risk={toFrontendRisk(route.risk_category || route.risk || "LOW")} />
      </div>
      <div className="mt-3 flex gap-5 text-sm"><span>{route.distance_km} km</span><span>{route.duration_minutes} min</span></div>
      {route.avoided_segments?.length > 0 && (
        <p className="mt-2 text-xs text-slate-400">Avoids {route.avoided_segments.length} flood-risk road segment{route.avoided_segments.length === 1 ? "" : "s"}.</p>
      )}
    </div>
  );

  return (
    <div className="space-y-6">
      <SectionTitle title="Safe Route" subtitle="Risk-aware routing between monitored zones" />
      <Card className="p-5">
        <div className="grid gap-3 md:grid-cols-[1fr_1fr_auto]">
          <label className="text-xs text-slate-500">FROM
            <select value={fromId} onChange={(e) => setFromId(e.target.value)} className="mt-1 w-full rounded-lg border border-slate-700 bg-[#071a29] px-3 py-3 text-sm text-slate-100 outline-none focus:border-sky-400">
              <option value="">Select starting zone</option>
              {zones.map((z) => <option key={z.id} value={z.id}>{z.name}</option>)}
            </select>
          </label>
          <label className="text-xs text-slate-500">TO
            <select value={toId} onChange={(e) => setToId(e.target.value)} className="mt-1 w-full rounded-lg border border-slate-700 bg-[#071a29] px-3 py-3 text-sm outline-none focus:border-sky-400">
              <option value="">Select destination zone</option>
              {zones.map((z) => <option key={z.id} value={z.id}>{z.name}</option>)}
            </select>
          </label>
          <button onClick={findRoute} disabled={loading || zones.length < 2} className="self-end rounded-lg bg-sky-500 px-6 py-3 text-sm font-semibold hover:bg-sky-400 disabled:opacity-50">
            {loading ? "Finding…" : "Find safe route"}
          </button>
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          <button onClick={() => openGoogleMaps("driving")} disabled={!fromId || !toId} className="rounded-lg border border-slate-700 px-4 py-2 text-xs font-semibold text-slate-200 hover:border-sky-400 hover:text-sky-300 disabled:opacity-50">
            Open route in Google Maps ↗
          </button>
          <span className="self-center text-[11px] text-slate-500">Google Maps navigation uses its own live road/traffic routing; FlowState's flood-safe recommendation is shown separately.</span>
        </div>
        {error && <div className="mt-3"><ErrorNote message={error} /></div>}
      </Card>

      <div className="grid gap-5 xl:grid-cols-[1.5fr_.75fr]">
        <Card className="overflow-hidden"><div className="h-[650px]"><FloodMap compact showTimeline /></div></Card>
        <Card className="p-6">
          <h3 className="font-semibold">Route comparison</h3>
          {result ? (
            <>
              <p className="mt-1 text-xs text-slate-500">{result.from?.label || "Start"} → {result.to?.label || "Destination"}</p>
              <div className="mt-5 space-y-3">
                <RouteCard title="Normal route" route={result.normal_route} />
                <RouteCard title="Flood-safe recommendation" route={result.safe_route} highlight />
              </div>
              <p className="mt-4 rounded-lg bg-[#0d293c] p-3 text-xs leading-5 text-slate-400">{result.explanation}</p>
              <div className="mt-3 flex flex-wrap gap-2">
                <button onClick={() => openGoogleMaps("driving")} className="rounded-lg bg-sky-500 px-4 py-2 text-xs font-semibold text-white hover:bg-sky-400">Navigate with Google Maps</button>
              </div>
              <p className="mt-3 text-[10px] text-slate-600">Routing source: {result.normal_route?.source === "demo_estimate" ? "FlowState estimate" : "OpenRouteService"}. The flood-safe detour is a FlowState risk-aware recommendation, not a Google route.</p>
            </>
          ) : (
            <p className="mt-5 text-sm text-slate-500">Choose a start and destination zone, then find a route.</p>
          )}
        </Card>
      </div>
    </div>
  );
}

// ============================================================
// Alerts
// ============================================================

function Alerts() {
  const [filter, setFilter] = useState("All");
  const { alerts, loading, error } = useAlerts(null, 30000);

  const visible = filter === "All" ? alerts : alerts.filter((a) => toFrontendRisk(a.severity) === filter);

  return (
    <div className="space-y-7">
      <SectionTitle title="Alert Center" subtitle="Live warnings + 0–3 hour early warnings" />
      <div className="rounded-xl border border-orange-400/20 bg-orange-400/5 px-4 py-3 text-xs text-orange-200">
        <b>3-hour alert:</b> FlowState checks the next 180 minutes of the flood nowcast and raises an early warning when HIGH/SEVERE risk is forecast.
      </div>
      <div className="flex gap-2">
        {["All", "Critical", "High", "Moderate"].map((x) => (
          <button onClick={() => setFilter(x)} key={x} className={`rounded-full border px-4 py-2 text-xs ${filter === x ? "border-sky-400/30 bg-sky-400/10 text-sky-300" : "border-slate-700 text-slate-400"}`}>{x}</button>
        ))}
      </div>
      {loading && !alerts.length && <LoadingNote>Loading alerts\…</LoadingNote>}
      {error && <ErrorNote message={error} />}
      <Card className="divide-y divide-slate-700/60">
        {visible.map((a) => {
          const risk = toFrontendRisk(a.severity);
          const tone = risk === "Critical" ? "red" : risk === "High" ? "orange" : risk === "Moderate" ? "yellow" : "green";
          return (
            <div key={a.id} className="flex gap-4 p-5">
              <div className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-sky-400/10 text-sky-400"><AlertTriangle size={20} /></div>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="font-semibold">{a.alert_type.replace(/_/g, " ")}</h3>
                  <Badge tone={tone}>{a.severity}</Badge>
                </div>
                <p className="mt-1 text-sm text-slate-400">{a.message}</p>
                {a.recommended_action && <p className="mt-1 text-xs text-sky-300">{a.recommended_action}</p>}
                {a.time_to_critical_minutes != null && (
                  <p className="mt-2 text-xs font-semibold text-orange-300">
                    3-hour forecast window · expected in {a.time_to_critical_minutes < 60 ? `${a.time_to_critical_minutes} min` : `${Math.round(a.time_to_critical_minutes / 60 * 10) / 10} hr`}
                  </p>
                )}
                <p className="mt-2 text-xs text-slate-600">{new Date(a.created_at).toLocaleString()}</p>
              </div>
            </div>
          );
        })}
        {!loading && !visible.length && <div className="p-5 text-sm text-slate-500">No alerts match this filter.</div>}
      </Card>
    </div>
  );
}

// ============================================================
// Drainage -- real drains
// ============================================================

function Drainage() {
  const { drains, loading, error } = useDrains(null, 60000);
  const [selected, setSelected] = useState(null);

  useEffect(() => { if (drains.length && !selected) setSelected(drains[0]); }, [drains, selected]);

  const counts = useMemo(() => {
    const c = { NORMAL: 0, WARNING: 0, CRITICAL: 0 };
    drains.forEach((d) => { c[d.status] = (c[d.status] || 0) + 1; });
    return c;
  }, [drains]);

  return (
    <div className="space-y-7">
      <SectionTitle title="Drainage Network" subtitle="Network status and intervention priorities" />
      {loading && !drains.length && <LoadingNote>Loading drain data\…</LoadingNote>}
      {error && <ErrorNote message={error} />}
      <div className="grid gap-4 md:grid-cols-4">
        <Stat title="Total drains" value={String(drains.length)} />
        <Stat title="Operational" value={String(counts.NORMAL)} tone="green" />
        <Stat title="Watch" value={String(counts.WARNING)} tone="orange" />
        <Stat title="Overloaded" value={String(counts.CRITICAL)} tone="red" />
      </div>
      <div className="grid gap-5 xl:grid-cols-[1.45fr_.8fr]">
        <Card className="overflow-hidden"><div className="h-[540px]"><FloodMap compact showTimeline={false} /></div></Card>
        <Card className="p-5">
          <SectionTitle title="Priority Drains" subtitle="Live blockage status" />
          <div className="max-h-[420px] space-y-2 overflow-y-auto">
            {drains.map((d) => {
              const status = toFrontendDrainStatus(d.status);
              const flow = d.latest_reading ? Math.round(d.latest_reading.blockage_percent) : 0;
              return (
                <button onClick={() => setSelected(d)} key={d.id} className={`w-full rounded-xl border p-4 text-left ${selected?.id === d.id ? "border-sky-400/30 bg-sky-400/5" : "border-slate-700/50 bg-[#0d293c]"}`}>
                  <div className="flex items-center justify-between">
                    <span className="font-semibold">{d.drain_code}</span>
                    <Badge tone={drainStatusBadgeTone(status)}>{status}</Badge>
                  </div>
                  <div className="mt-3 flex justify-between text-xs"><span>Blockage</span><span>{flow}%</span></div>
                  <div className="mt-1 h-1.5 rounded-full bg-slate-800"><div className="h-full rounded-full bg-sky-400" style={{ width: `${flow}%` }} /></div>
                </button>
              );
            })}
          </div>
          {selected && (
            <div className="mt-4 rounded-xl border border-sky-400/20 bg-sky-400/5 p-4">
              <div className="text-xs text-slate-500">SELECTED DRAIN</div>
              <div className="mt-1 text-lg font-bold">{selected.drain_code}</div>
              <div className="mt-2 text-xs text-slate-400">Design capacity: <b className="text-slate-200">{selected.normal_capacity_m3s} m&sup3;/s</b></div>
              {selected.latest_reading && <div className="mt-1 text-xs text-slate-400">Estimated blockage: <b className="text-slate-200">{selected.latest_reading.blockage_percent}%</b></div>}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}

function Stat({ title, value, tone = "blue" }) {
  return (
    <Card className="p-5">
      <p className="text-xs text-slate-500">{title}</p>
      <p className={`mt-2 text-2xl font-bold ${tone === "green" ? "text-emerald-400" : tone === "orange" ? "text-orange-400" : tone === "red" ? "text-red-400" : "text-slate-100"}`}>{value}</p>
    </Card>
  );
}

// ============================================================
// Analytics -- risk distribution is real; historical trend +
// model performance are clearly-labeled illustrative examples
// (no backend endpoint provides these yet)
// ============================================================

function Analytics({ snapshot }) {
  const distribution = useMemo(() => {
    const counts = { Low: 0, Moderate: 0, High: 0, Critical: 0 };
    snapshot.forEach((s) => { counts[toFrontendRisk(s.risk_category)] += 1; });
    return Object.entries(counts).map(([name, value]) => ({ name, value }));
  }, [snapshot]);

  const illustrativeHist = [
    { month: "Apr", incidents: 3, rain: 42 }, { month: "May", incidents: 5, rain: 57 },
    { month: "Jun", incidents: 4, rain: 51 }, { month: "Jul", incidents: 8, rain: 79 },
    { month: "Aug", incidents: 11, rain: 96 },
  ];

  return (
    <div className="space-y-7">
      <SectionTitle title="Analytics" subtitle="Zone distribution is live; trend/performance panels below are illustrative examples" />
      <div className="grid gap-5 xl:grid-cols-2">
        <Card className="p-6">
          <div className="flex items-center justify-between"><h3 className="font-semibold">Flood incidents vs rainfall</h3><Badge tone="yellow">Illustrative example</Badge></div>
          <div className="mt-5 h-72">
            <ResponsiveContainer>
              <BarChart data={illustrativeHist}>
                <CartesianGrid stroke="#294052" strokeDasharray="3 3" />
                <XAxis dataKey="month" stroke="#64748b" fontSize={11} />
                <YAxis stroke="#64748b" fontSize={11} />
                <Tooltip contentStyle={{ background: "#071a29", border: "1px solid #294052", borderRadius: 10 }} />
                <Bar dataKey="incidents" fill="#38bdf8" radius={[5, 5, 0, 0]} />
                <Line dataKey="rain" stroke="#fb923c" strokeWidth={3} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
        <Card className="p-6">
          <div className="flex items-center justify-between"><h3 className="font-semibold">Current zone distribution</h3><Badge tone="green">Live</Badge></div>
          <div className="mt-3 h-72">
            <ResponsiveContainer>
              <PieChart>
                <Pie data={distribution} dataKey="value" nameKey="name" innerRadius={65} outerRadius={100} paddingAngle={3}>
                  {distribution.map((x) => <Cell key={x.name} fill={riskColors[x.name]} />)}
                </Pie>
                <Tooltip contentStyle={{ background: "#071a29", border: "1px solid #294052", borderRadius: 10 }} />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </div>
      <div>
        <Badge tone="yellow">Illustrative example \u2014 no live model-performance endpoint yet</Badge>
        <div className="mt-3 grid gap-4 md:grid-cols-4">
          <Performance label="Precision" value="89.7%" />
          <Performance label="Recall" value="92.1%" />
          <Performance label="F1 Score" value="90.8%" />
          <Performance label="Uptime" value="99.4%" />
        </div>
      </div>
    </div>
  );
}

function Performance({ label, value }) {
  return (
    <Card className="p-5">
      <p className="text-xs text-slate-500">{label}</p>
      <p className="mt-2 text-2xl font-bold text-sky-400">{value}</p>
      <div className="mt-3 h-1 rounded-full bg-slate-800"><div className="h-full w-[90%] rounded-full bg-sky-400" /></div>
    </Card>
  );
}

// ============================================================
// Simulation -- real POST /api/simulation, with the blockage
// control the spec calls for (missing from the original mock)
// ============================================================

function Simulation({ zones }) {
  const [zoneId, setZoneId] = useState("");
  const [rain, setRain] = useState(82);
  const [duration, setDuration] = useState(1);
  const [blockage, setBlockage] = useState(20);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => { if (zones.length && !zoneId) setZoneId(String(zones[0].id)); }, [zones, zoneId]);

  const run = () => {
    if (!zoneId) return;
    setLoading(true);
    setError(null);
    apiRunSimulation(Number(zoneId), rain, duration, blockage)
      .then((res) => setResult(res.data))
      .catch((err) => setError(err.message || "Simulation failed"))
      .finally(() => setLoading(false));
  };

  const sim = result?.simulated;
  const impactLevel = sim ? toFrontendRisk(sim.risk_category) : null;

  return (
    <div className="space-y-7">
      <SectionTitle title="Flood Simulation" subtitle="Explore a hypothetical rainfall scenario and its predicted impact" />
      <div className="grid gap-5 xl:grid-cols-[.8fr_1.2fr]">
        <Card className="p-6">
          <h3 className="font-semibold">Scenario controls</h3>
          <p className="mt-2 text-xs text-slate-500">Runs the real flood engine with these hypothetical inputs against a chosen zone.</p>
          <label className="mt-5 block text-xs text-slate-500">ZONE
            <select value={zoneId} onChange={(e) => setZoneId(e.target.value)} className="mt-1 w-full rounded-lg border border-slate-700 bg-[#071a29] px-3 py-3 text-sm outline-none focus:border-sky-400">
              {zones.map((z) => <option key={z.id} value={z.id}>{z.name}</option>)}
            </select>
          </label>
          <Control label="Rainfall intensity" value={rain} suffix="mm/hr" set={setRain} min={5} max={150} />
          <Control label="Rain duration" value={duration} suffix="hr" set={setDuration} min={1} max={6} />
          <Control label="Drainage blockage" value={blockage} suffix="%" set={setBlockage} min={0} max={100} />
          <button onClick={run} disabled={loading} className="mt-6 w-full rounded-lg bg-sky-500 py-3 text-sm font-semibold hover:bg-sky-400 disabled:opacity-50">
            {loading ? "Running\…" : "Run Simulation"}
          </button>
          {error && <div className="mt-3"><ErrorNote message={error} /></div>}
        </Card>

        <Card className="p-6">
          <div className="flex items-center justify-between">
            <h3 className="font-semibold">Predicted impact</h3>
            {impactLevel && <RiskBadge risk={impactLevel} />}
          </div>

          {!result && <p className="mt-6 text-sm text-slate-500">Configure a scenario and run the simulation.</p>}

          {result && (
            <>
              <div className="mt-6 grid grid-cols-1 gap-4 md:grid-cols-3">
                <SimStat label="Flood probability" value={`${Math.round(sim.flood_probability * 100)}%`} />
                <SimStat label="Water depth" value={`${sim.water_depth_cm} cm`} />
                <SimStat label="Affected area" value={`${sim.affected_area_percent}%`} />
              </div>

              <div className="mt-7 grid grid-cols-2 gap-4 rounded-xl bg-[#0d293c] p-5 text-xs">
                <div>
                  <div className="text-slate-500">BEFORE (current real conditions)</div>
                  <div className="mt-1 font-semibold">{toFrontendRisk(result.baseline.risk_category)} · {Math.round(result.baseline.flood_probability * 100)}%</div>
                </div>
                <div>
                  <div className="text-slate-500">AFTER (this scenario)</div>
                  <div className="mt-1 font-semibold" style={{ color: riskColors[impactLevel] }}>{impactLevel} · {Math.round(sim.flood_probability * 100)}%</div>
                </div>
              </div>

              <div className="mt-7">
                <div className="mb-2 flex items-center justify-between text-xs"><span className="text-slate-500">Impact level</span><span className="font-semibold text-sky-300">{Math.round(sim.flood_probability * 100)}%</span></div>
                <div className="h-3 overflow-hidden rounded-full bg-slate-800"><div className="h-full rounded-full" style={{ width: `${Math.round(sim.flood_probability * 100)}%`, background: riskColors[impactLevel] }} /></div>
              </div>

              <div className="mt-7 rounded-xl bg-[#0d293c] p-5">
                <div className="flex items-center gap-2 text-sm font-semibold"><ShieldAlert size={17} className="text-orange-400" />Scenario interpretation</div>
                <p className="mt-2 text-sm leading-6 text-slate-400">
                  At {rain} mm/hr for {duration}hr with {blockage}% drainage blockage, this zone's engine-computed risk is <b className="text-slate-200">{impactLevel.toLowerCase()}</b>.
                </p>
              </div>
            </>
          )}
        </Card>
      </div>
    </div>
  );
}

function Control({ label, value, suffix, set, min, max }) {
  return (
    <div className="mt-6">
      <div className="flex justify-between text-sm"><span>{label}</span><span className="font-semibold text-sky-400">{value} {suffix}</span></div>
      <input type="range" min={min} max={max} value={value} onChange={(e) => set(+e.target.value)} className="mt-3 w-full accent-sky-400" />
    </div>
  );
}

function SimStat({ label, value }) {
  return <div className="rounded-xl bg-[#0d293c] p-4"><p className="text-xs text-slate-500">{label}</p><p className="mt-2 text-xl font-bold">{value}</p></div>;
}

// ============================================================
// About / FAQ, Help / Action -- no data dependency, unchanged
// ============================================================

function AboutFAQ() {
  const faqs = [
    ["What is FlowState?", "FlowState combines live weather, flood-risk prediction, monitored zones, routes, alerts and response guidance."],
    ["How is flood risk calculated?", "A physics-based runoff/drainage engine (Rational Method) is blended with a trained Random Forest model, using real rainfall, drainage capacity, and blockage data."],
    ["Can citizens use Safe Route?", "Yes. It compares a normal route against a flood-aware route that detours around zones currently at HIGH/SEVERE risk."],
    ["How often does the dashboard update?", "Most live values refresh automatically every 30-60 seconds from the backend."],
  ];
  return (
    <div className="mx-auto max-w-4xl space-y-7">
      <SectionTitle title="About FlowState" subtitle="Urban flood intelligence for faster, safer decisions" />
      <Card className="p-6">
        <div className="grid gap-5 md:grid-cols-3">
          <div><div className="text-xs text-slate-500">MISSION</div><p className="mt-2 text-sm leading-6 text-slate-300">Turn complex flood data into clear actions before water becomes a crisis.</p></div>
          <div><div className="text-xs text-slate-500">CORE DATA</div><p className="mt-2 text-sm leading-6 text-slate-300">Rainfall · flood zones · routes · alerts · AI prediction</p></div>
          <div><div className="text-xs text-slate-500">DESIGNED FOR</div><p className="mt-2 text-sm leading-6 text-slate-300">Citizens, responders and city operations teams.</p></div>
        </div>
      </Card>
      <div>
        <h2 className="mb-4 text-lg font-semibold">Frequently Asked Questions</h2>
        <div className="space-y-3">
          {faqs.map(([q, a]) => (
            <details key={q} className="group rounded-xl border border-slate-700/60 bg-[#0a2031] p-5">
              <summary className="cursor-pointer list-none font-semibold">{q}<span className="float-right text-slate-500 group-open:rotate-45">+</span></summary>
              <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-400">{a}</p>
            </details>
          ))}
        </div>
      </div>
    </div>
  );
}

function HelpAction() {
  const actions = [
    ["Move to safer ground", "If your area is marked Critical or water is rapidly rising, move away from low-lying locations.", "red"],
    ["Avoid flooded roads", "Do not enter roads marked as High/Critical on the map. Use Safe Route for an alternate path.", "orange"],
    ["Report waterlogging", "Share the location and approximate water depth so the monitored picture can be updated.", "yellow"],
    ["Emergency response", "Follow official emergency instructions and contact local emergency services when immediate assistance is required.", "blue"],
  ];
  return (
    <div className="space-y-7">
      <SectionTitle title="Help / Action Center" subtitle="What to do when flood risk increases" />
      <div className="grid gap-4 md:grid-cols-2">
        {actions.map(([title, detail, t], i) => (
          <Card key={title} className="p-6">
            <div className="flex items-start gap-4">
              <div className={`grid h-11 w-11 shrink-0 place-items-center rounded-xl ${t === "red" ? "bg-red-400/10 text-red-400" : t === "orange" ? "bg-orange-400/10 text-orange-400" : t === "yellow" ? "bg-yellow-400/10 text-yellow-400" : "bg-sky-400/10 text-sky-400"}`}>
                <span className="text-sm font-bold">0{i + 1}</span>
              </div>
              <div><h3 className="font-semibold">{title}</h3><p className="mt-2 text-sm leading-6 text-slate-400">{detail}</p></div>
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}

// ============================================================
// Shell: Auth, Brand, ZonePicker, Page router, App
// ============================================================

function Auth({ mode, onDone }) {
  const [signup, setSignup] = useState(mode === "signup");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const submit = async (event) => {
    event.preventDefault();
    setError("");
    if (signup) {
      setError("Account creation is disabled in the SIH demo. Use the demo admin account or continue as guest.");
      return;
    }
    setBusy(true);
    try {
      const response = await loginUser(email, password);
      const user = response.data?.user;
      if (!user) throw new Error("Login failed.");
      localStorage.setItem("flowstate_user", JSON.stringify(user));
      localStorage.setItem("flowstate_auth_email", user.email);
      onDone(user);
    } catch (err) {
      setError(err.message || "Unable to log in.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid min-h-screen place-items-center px-5 py-10">
      <div className="w-full max-w-md">
        <Brand />
        <Card className="p-7">
          <div className="mb-6 flex rounded-xl bg-[#071a29] p-1">
            <button onClick={() => setSignup(false)} className={`flex-1 rounded-lg py-2.5 text-sm ${!signup ? "bg-sky-500 text-white" : "text-slate-400"}`}>Login</button>
            <button onClick={() => setSignup(true)} className={`flex-1 rounded-lg py-2.5 text-sm ${signup ? "bg-sky-500 text-white" : "text-slate-400"}`}>Sign up</button>
          </div>
          <h1 className="text-2xl font-bold">{signup ? "Create your FlowState account" : "Welcome back"}</h1>
          <p className="mt-2 text-sm text-slate-400">{signup ? "Set up your flood alerts and preferred zone." : "Access your flood monitoring dashboard."}</p>
          {!signup && (
            <div className="mt-4 rounded-xl border border-sky-400/15 bg-sky-400/5 p-3 text-xs">
              <div className="font-semibold text-sky-300">SIH Demo Admin</div>
              <div className="mt-1 text-slate-400">Email: <span className="text-slate-200">admin@admin.com</span></div>
              <div className="text-slate-400">Password: <span className="text-slate-200">Admin@123</span></div>
            </div>
          )}
          <form onSubmit={submit}>
            {signup && <label className="mt-5 block text-xs text-slate-500">NAME<input className="mt-1 w-full rounded-lg border border-slate-700 bg-[#071a29] px-3 py-3 text-sm outline-none focus:border-sky-400" placeholder="Your name" /></label>}
            <label className="mt-4 block text-xs text-slate-500">EMAIL<input value={email} onChange={(e) => setEmail(e.target.value)} type="email" autoComplete="username" className="mt-1 w-full rounded-lg border border-slate-700 bg-[#071a29] px-3 py-3 text-sm outline-none focus:border-sky-400" placeholder="you@example.com" required /></label>
            <label className="mt-4 block text-xs text-slate-500">PASSWORD<input value={password} onChange={(e) => setPassword(e.target.value)} type="password" autoComplete="current-password" className="mt-1 w-full rounded-lg border border-slate-700 bg-[#071a29] px-3 py-3 text-sm outline-none focus:border-sky-400" placeholder="••••••••" required /></label>
            {error && <p className="mt-3 rounded-lg border border-red-400/20 bg-red-400/5 px-3 py-2 text-xs text-red-300">{error}</p>}
            <button type="submit" disabled={busy} className="mt-6 flex w-full items-center justify-center gap-2 rounded-lg bg-sky-500 py-3 text-sm font-semibold hover:bg-sky-400 disabled:cursor-not-allowed disabled:opacity-60">
              {signup ? <UserPlus size={17} /> : <LogIn size={17} />} {busy ? "Signing in…" : signup ? "Create account" : "Login"}
            </button>
          </form>
          <button onClick={onDone} className="mt-3 w-full rounded-lg border border-slate-700 py-3 text-sm text-slate-300">Continue as guest</button>
        </Card>
      </div>
    </div>
  );
}

function Brand() {
  return (
    <div className="mb-7 flex items-center gap-3">
      <div className="grid h-11 w-11 shrink-0 place-items-center"><img src={flowstateLogo} alt="FlowState logo" className="h-full w-full object-contain" /></div>
      <div><div className="text-lg font-bold text-sky-400">FlowState</div><div className="text-[11px] text-slate-400">Urban Flood Intelligence</div></div>
    </div>
  );
}

function ZonePicker({ zones, selectedZoneId, setSelectedZoneId }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const selected = zones.find((z) => z.id === selectedZoneId);
  const matches = zones.filter((z) => z.name.toLowerCase().includes(query.toLowerCase()));
  const choose = (z) => { setSelectedZoneId(z.id); setQuery(""); setOpen(false); };

  return (
    <div className="relative">
      <div className="flex items-center gap-1 rounded-xl border border-slate-700 bg-[#0a2031] px-3 py-2">
        <MapPin size={15} className="text-sky-400" />
        <input
          value={open ? query : (selected?.name || "My Location")}
          onFocus={() => setOpen(true)}
          onChange={(e) => { setQuery(e.target.value); setOpen(true); }}
          className="w-28 bg-transparent text-sm outline-none md:w-36"
          placeholder="Search zone"
        />
        <button type="button" onClick={() => setOpen((v) => !v)} aria-label="Open zone dropdown" aria-expanded={open} className="rounded-md p-1 text-slate-500 hover:bg-white/5 hover:text-slate-200">
          <ChevronDown size={15} />
        </button>
      </div>
      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <div className="absolute right-0 top-12 z-20 w-56 rounded-xl border border-slate-700 bg-[#071a29] p-2 shadow-2xl">
            <div className="mb-2 flex items-center gap-2 rounded-lg bg-[#0d293c] px-3 py-2">
              <Search size={14} className="text-slate-500" />
              <input autoFocus value={query} onChange={(e) => setQuery(e.target.value)} className="w-full bg-transparent text-xs outline-none" placeholder="Search zone..." />
            </div>
            <div className="max-h-64 overflow-y-auto">
              <button onClick={() => { setSelectedZoneId(null); setQuery(""); setOpen(false); }} className="mb-1 flex w-full items-center gap-2 rounded-lg px-3 py-2.5 text-left text-sm text-sky-300 hover:bg-sky-400/10">
                <LocateFixed size={14} /> My Location
              </button>
              <div className="px-3 pb-2 text-[10px] text-slate-600">Gurugram monitored zones</div>
              {matches.length ? matches.map((z) => (
                <button key={z.id} onClick={() => choose(z)} className="flex w-full items-center justify-between rounded-lg px-3 py-2.5 text-left text-sm hover:bg-sky-400/10">
                  <span>{z.name}</span>
                </button>
              )) : <div className="p-3 text-xs text-slate-500">No matching zone</div>}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function Page({ name, go, weather, zones, snapshot, selectedZoneId }) {
  if (name === "Dashboard") return <Dashboard go={go} weather={weather} snapshot={snapshot} selectedZoneId={selectedZoneId} />;
  if (name === "Flood Map") return <MapPage weather={weather} selectedZoneId={selectedZoneId} />;
  if (name === "Forecast") return <Forecast weather={weather} />;
  if (name === "Safe Route") return <SafeRoute weather={weather} zones={zones} />;
  if (name === "Alert") return <Alerts />;
  if (name === "Simulation") return <Simulation zones={zones} />;
  if (name === "Drainage") return <Drainage />;
  if (name === "About / FAQ") return <AboutFAQ />;
  if (name === "Help / Action") return <HelpAction />;
  return <Dashboard go={go} weather={weather} snapshot={snapshot} />;
}

export default function App() {
  const [active, setActive] = useState("Dashboard");
  const [mobile, setMobile] = useState(false);
  const [selectedZoneId, setSelectedZoneId] = useState(null);
  const [userLocation, setUserLocation] = useState(null);
  const [auth, setAuth] = useState(null);
  const [currentUser, setCurrentUser] = useState(() => {
    try { return JSON.parse(localStorage.getItem("flowstate_user") || "null"); } catch { return null; }
  });
  const [notificationsOpen, setNotificationsOpen] = useState(false);

  const { zones } = useZones();
  const { snapshot } = useFloodRiskSnapshot(60000);
  const { alerts } = useAlerts(null, 60000);
  const { weather: weatherResp } = useWeather(selectedZoneId);
  const { weather: locationWeatherResp } = useLocationWeather(userLocation);

  useEffect(() => {
    if (!navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition(
      (position) => setUserLocation({ lat: position.coords.latitude, lng: position.coords.longitude }),
      () => {},
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 30000 }
    );
  }, []);

  const selectedZone = zones.find((z) => z.id === selectedZoneId) || null;
  const riskEntry = snapshot.find((s) => s.zone_id === selectedZoneId) || null;
  const weather = buildWeatherView(selectedZone, riskEntry, weatherResp, locationWeatherResp);

  const go = (name) => { setActive(name); setMobile(false); window.scrollTo({ top: 0, behavior: "smooth" }); };
  const bg = weatherTheme(weather);

  if (auth) {
    return (
      <div className={`min-h-screen bg-gradient-to-br ${bg} text-slate-100 transition-colors duration-700`}>
        <div className="weather-glow" /><Auth mode={auth} onDone={(user) => { setCurrentUser(user); setAuth(null); }} />
      </div>
    );
  }

  return (
    <div className={`relative min-h-screen bg-gradient-to-br ${bg} text-slate-100 transition-colors duration-700`}>
      <div className="pointer-events-none fixed inset-0 z-0 weather-overlay" data-weather={weather.icon} />

      <aside className="fixed inset-y-0 left-0 z-[1100] hidden w-64 border-r border-slate-700/60 bg-[#071a29]/95 lg:block">
        <div className="flex h-full flex-col p-5">
          <Brand />
          <nav className="space-y-1">
            {nav.map(([label, I]) => (
              <button key={label} onClick={() => go(label)} className={`flex w-full items-center gap-3 rounded-lg px-3 py-3 text-left text-sm transition ${active === label ? "bg-sky-500/15 text-sky-300 ring-1 ring-sky-400/20" : "text-slate-400 hover:bg-white/5 hover:text-slate-100"}`}>
                <I size={18} />{label}
              </button>
            ))}
          </nav>
          <div className="mt-auto rounded-xl border border-slate-700/60 bg-[#0a2031] p-4">
            <div className="flex items-center gap-2 text-sm font-semibold"><Activity size={16} className="text-sky-400" />System Status</div>
            <div className="mt-2 flex items-center gap-2 text-xs text-emerald-400"><span className="h-2 w-2 rounded-full bg-emerald-400" />Connected to live backend</div>
          </div>
        </div>
      </aside>

      {mobile && (
        <div className="fixed inset-0 z-[1200] bg-black/60 lg:hidden" onClick={() => setMobile(false)}>
          <aside onClick={(e) => e.stopPropagation()} className="h-full w-72 bg-[#071a29] p-5 relative z-[1201]">
            <div className="flex justify-between"><Brand /><button onClick={() => setMobile(false)}><X /></button></div>
            <nav className="mt-6 space-y-1">
              {nav.map(([label, I]) => (
                <button key={label} onClick={() => go(label)} className={`flex w-full items-center gap-3 rounded-lg px-3 py-3 text-left text-sm ${active === label ? "bg-sky-500/15 text-sky-300" : "text-slate-400"}`}>
                  <I size={18} />{label}
                </button>
              ))}
            </nav>
          </aside>
        </div>
      )}

      <main className="relative z-10 lg:pl-64">
        <header className="sticky top-0 z-[1000] flex min-h-20 items-center justify-between gap-3 border-b border-slate-700/60 bg-[#061421]/90 px-4 py-3 backdrop-blur md:px-8">
          <div className="flex items-center gap-3">
            <button className="rounded-lg border border-slate-700 p-2 lg:hidden" onClick={() => setMobile(true)}><Menu size={19} /></button>
            <div>
              <h1 className="text-xl font-semibold">{active}</h1>
              <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-slate-400">
                <span>{weather.condition} · {weather.temp}°C · {weather.city}{weather.isLocation ? " · GPS" : ""}</span>
                <span className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold ${
                  weather.source === "demo"
                    ? "border-amber-400/30 bg-amber-400/10 text-amber-300"
                    : weather.source
                    ? "border-emerald-400/30 bg-emerald-400/10 text-emerald-300"
                    : "border-slate-700 text-slate-500"
                }`}>
                  {weather.sourceLabel}
                </span>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2 md:gap-3">
            <ZonePicker zones={zones} selectedZoneId={selectedZoneId} setSelectedZoneId={setSelectedZoneId} />
            <div className="relative">
              <button onClick={() => setNotificationsOpen((v) => !v)} aria-label="Open notifications" aria-expanded={notificationsOpen} className={`relative rounded-lg border border-slate-700 bg-[#0a2031] p-2.5 text-slate-300 transition ${notificationsOpen ? "border-sky-400/40 text-sky-300" : ""}`}>
                <Bell size={19} />
                {alerts.length > 0 && <span className="absolute -right-1 -top-1 grid h-4 min-w-4 place-items-center rounded-full bg-red-500 px-1 text-[10px] font-bold">{Math.min(9, alerts.length)}</span>}
              </button>
              {notificationsOpen && (
                <>
                  <div className="fixed inset-0 z-20" onClick={() => setNotificationsOpen(false)} />
                  <div className="absolute right-0 top-12 z-30 w-80 overflow-hidden rounded-2xl border border-slate-700 bg-[#071a29] shadow-2xl">
                    <div className="flex items-center justify-between border-b border-slate-700/60 px-4 py-3">
                      <div><div className="text-sm font-semibold">Notifications</div><div className="text-[10px] text-slate-500">{alerts.length} active alert(s)</div></div>
                      <button onClick={() => setNotificationsOpen(false)} className="text-slate-500 hover:text-slate-200"><X size={15} /></button>
                    </div>
                    <div className="space-y-1 p-2">
                      {alerts.slice(0, 3).map((a) => (
                        <button key={a.id} onClick={() => { setNotificationsOpen(false); go("Alert"); }} className="w-full rounded-xl p-3 text-left hover:bg-white/5">
                          <div className="flex items-center gap-2">
                            <span className="h-2 w-2 rounded-full" style={{ background: riskColors[toFrontendRisk(a.severity)] }} />
                            <span className="text-xs font-semibold">{a.alert_type.replace(/_/g, " ")}</span>
                          </div>
                          <p className="mt-1 pl-4 text-[11px] text-slate-400">{a.message}</p>
                        </button>
                      ))}
                      {!alerts.length && <p className="p-3 text-xs text-slate-500">No active alerts.</p>}
                    </div>
                    <div className="border-t border-slate-700/60 p-2">
                      <button onClick={() => { setNotificationsOpen(false); go("Alert"); }} className="w-full rounded-lg py-2 text-xs font-semibold text-sky-300 hover:bg-sky-400/5">View all alerts →</button>
                    </div>
                  </div>
                </>
              )}
            </div>
            {currentUser ? (
              <div className="flex items-center gap-2">
                <div className="hidden rounded-lg border border-emerald-400/20 bg-emerald-400/5 px-3 py-2 text-xs md:block">
                  <div className="font-semibold text-emerald-300">{currentUser.role === "admin" ? "Admin" : "User"}</div>
                  <div className="text-[10px] text-slate-500">{currentUser.email}</div>
                </div>
                <button onClick={() => { localStorage.removeItem("flowstate_user"); localStorage.removeItem("flowstate_auth_email"); setCurrentUser(null); }} className="flex items-center gap-2 rounded-lg border border-slate-700 bg-[#0a2031] px-3 py-2 text-sm"><LogIn size={16} /> Logout</button>
              </div>
            ) : (
              <button onClick={() => setAuth("login")} className="hidden items-center gap-2 rounded-lg border border-slate-700 bg-[#0a2031] px-3 py-2 text-sm md:flex"><User size={16} /> Login</button>
            )}
          </div>
        </header>
        <div className="p-4 md:p-7"><Page name={active} go={go} weather={weather} zones={zones} snapshot={snapshot} selectedZoneId={selectedZoneId} /></div>
      </main>
    </div>
  );
}
