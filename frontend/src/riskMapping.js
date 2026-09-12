/**
 * src/riskMapping.js
 * ---------------------
 * The backend (see backend/flood_engine/risk.py) uses LOW/MODERATE/HIGH/
 * SEVERE. This frontend was already built using Low/Moderate/High/
 * Critical. Rather than rewrite one side to match the other, this is the
 * one translation point both directions go through -- so a naming
 * mismatch can never silently show the wrong color/label somewhere.
 */

export const riskColors = { Low: "#22c55e", Moderate: "#facc15", High: "#fb923c", Critical: "#ef4444" };

const BACKEND_TO_FRONTEND = { LOW: "Low", MODERATE: "Moderate", HIGH: "High", SEVERE: "Critical" };
const FRONTEND_TO_BACKEND = { Low: "LOW", Moderate: "MODERATE", High: "HIGH", Critical: "SEVERE" };

export function toFrontendRisk(backendRiskCategory) {
  return BACKEND_TO_FRONTEND[backendRiskCategory] || "Low";
}

export function toBackendRisk(frontendRiskLabel) {
  return FRONTEND_TO_BACKEND[frontendRiskLabel] || "LOW";
}

// Backend drain status (NORMAL/WARNING/CRITICAL) -> a frontend-style label.
// The original mock UI used a 4th status ("Degraded") the backend has no
// equivalent for, so WARNING covers both "Watch" and "Degraded" territory.
const DRAIN_STATUS_TO_FRONTEND = { NORMAL: "Operational", WARNING: "Watch", CRITICAL: "Overloaded" };

export function toFrontendDrainStatus(backendStatus) {
  return DRAIN_STATUS_TO_FRONTEND[backendStatus] || "Operational";
}

export function drainStatusBadgeTone(frontendStatus) {
  if (frontendStatus === "Overloaded") return "red";
  if (frontendStatus === "Watch") return "yellow";
  return "green";
}
