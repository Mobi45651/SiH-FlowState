"""Flood-aware road routing for FlowState.

The service uses RouteSegment endpoints as a small road graph. When real
OpenStreetMap segments are imported with scripts/import_osm.py, the same
algorithm becomes a street-level graph over Gurugram roads. High/severe
segments are removed for the safe route; Dijkstra then returns the shortest
remaining path. If no connected graph is available, the service falls back
to a clearly labelled straight-line estimate rather than inventing a route.
"""
import heapq
import json
import logging
import math
from collections import defaultdict

import requests
from flask import current_app

from models import Zone, RouteSegment
from services.nowcast_engine import get_cached_zone_nowcast
from flood_engine.routing import haversine_distance_km, worst_risk

logger = logging.getLogger(__name__)
REQUEST_TIMEOUT_SECONDS = 8
ORS_DIRECTIONS_URL = "https://api.openrouteservice.org/v2/directions/driving-car"
RISK_PENALTY = {"LOW": 0.0, "MODERATE": 0.20, "HIGH": 2.0, "SEVERE": 100.0}


def _node_key(lat, lng):
    # OSM-derived segments normally share exact node coordinates; quantising
    # also makes hand/imported data robust to tiny floating point differences.
    return (round(float(lat), 6), round(float(lng), 6))


def _build_graph(segments):
    graph = defaultdict(list)
    nodes = {}
    for s in segments:
        a = _node_key(s.start_lat, s.start_lng)
        b = _node_key(s.end_lat, s.end_lng)
        nodes[a] = (s.start_lat, s.start_lng)
        nodes[b] = (s.end_lat, s.end_lng)
        graph[a].append((b, s))
        graph[b].append((a, s))
    return graph, nodes


def _nearest_node(nodes, lat, lng):
    if not nodes:
        return None
    return min(nodes, key=lambda n: haversine_distance_km(lat, lng, n[0], n[1]))


def _edge_cost(segment, mode, risk_override=None):
    risk = (risk_override or getattr(segment, "risk_category", None) or "LOW").upper()
    minutes = max(0.1, (segment.distance_km / 25.0) * 60.0)
    if mode == "safe" and risk in ("HIGH", "SEVERE"):
        return math.inf
    if mode == "balanced":
        return minutes * (1.0 + RISK_PENALTY.get(risk, 0.0))
    return minutes


def _dijkstra(segments, start_lat, start_lng, end_lat, end_lng, mode="normal", risk_by_id=None):
    graph, nodes = _build_graph(segments)
    start = _nearest_node(nodes, start_lat, start_lng)
    goal = _nearest_node(nodes, end_lat, end_lng)
    if start is None or goal is None:
        return None
    dist = {start: 0.0}
    prev = {}
    heap = [(0.0, start)]
    while heap:
        cost, node = heapq.heappop(heap)
        if cost != dist.get(node):
            continue
        if node == goal:
            break
        for nxt, seg in graph[node]:
            edge = _edge_cost(seg, mode, (risk_by_id or {}).get(seg.id))
            if math.isinf(edge):
                continue
            new = cost + edge
            if new < dist.get(nxt, math.inf):
                dist[nxt] = new
                prev[nxt] = (node, seg)
                heapq.heappush(heap, (new, nxt))
    if goal not in dist:
        return None
    nodes_path = [goal]
    segments_path = []
    cur = goal
    while cur != start:
        parent, seg = prev[cur]
        nodes_path.append(parent)
        segments_path.append(seg)
        cur = parent
    nodes_path.reverse(); segments_path.reverse()
    return {
        "segments": segments_path,
        "coordinates": [[n[1], n[0]] for n in nodes_path],  # Leaflet [lat,lng]
        "distance_km": round(sum(max(0.0, s.distance_km) for s in segments_path), 2),
        "duration_minutes": round(sum((max(0.0, s.distance_km) / 25.0) * 60.0 for s in segments_path), 1),
        "risk": worst_risk([(s.risk_category or "LOW").upper() for s in segments_path]),
    }


def _fetch_real_route(from_lat, from_lng, to_lat, to_lng):
    api_key = current_app.config.get("ROUTING_API_KEY")
    if not api_key:
        raise RuntimeError("No ROUTING_API_KEY configured")
    params = {"api_key": api_key, "start": f"{from_lng},{from_lat}", "end": f"{to_lng},{to_lat}"}
    r = requests.get(ORS_DIRECTIONS_URL, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
    r.raise_for_status()
    payload = r.json(); summary = payload["features"][0]["properties"]["summary"]
    geometry = payload["features"][0].get("geometry")
    coords = geometry.get("coordinates", []) if isinstance(geometry, dict) else []
    return {"distance_km": round(summary["distance"] / 1000, 2), "duration_minutes": round(summary["duration"] / 60, 1), "source": "openrouteservice", "geometry": [[p[1],p[0]] for p in coords]}


def _segment_risks(offset_minutes=0):
    """Return dynamic risk by segment ID without mutating ORM rows."""
    zones = {z.id: z for z in Zone.query.all()}
    risks = {}
    for zone_id, zone in zones.items():
        try:
            forecast = get_cached_zone_nowcast(zone)["forecast"]
            if forecast:
                target = min(forecast, key=lambda step: abs((step.get("offset_minutes") or 0) - int(offset_minutes)))
                risks[zone_id] = target["risk_category"]
        except Exception:
            continue
    return risks


def route_geojson(offset_minutes=0):
    segments = RouteSegment.query.all()
    zone_risks = _segment_risks(offset_minutes)
    features = []
    for s in segments:
        risk = (zone_risks.get(s.zone_id, s.risk_category) or "LOW").upper()
        props = s.to_dict()
        props["risk_category"] = risk
        props["is_flood_prone"] = risk in ("HIGH", "SEVERE")
        features.append({"type":"Feature","properties":props,"geometry":{"type":"LineString","coordinates":[[s.start_lng,s.start_lat],[s.end_lng,s.end_lat]]}})
    return {"type":"FeatureCollection","features":features,"meta":{"source":"database+nowcast","street_level":True}}


def _fallback_route(from_lat, from_lng, to_lat, to_lng):
    straight = haversine_distance_km(from_lat, from_lng, to_lat, to_lng)
    distance = round(straight * 1.35, 2)
    duration = round(distance / 25.0 * 60.0, 1)
    return {"distance_km":distance,"duration_minutes":duration,"source":"demo_estimate","geometry":[[from_lat,from_lng],[to_lat,to_lng]],"risk":"LOW"}


def calculate_safe_route(from_lat, from_lng, to_lat, to_lng, from_label=None, to_label=None):
    segments = RouteSegment.query.all()
    zone_risks = _segment_risks(0)
    risk_by_id = {s.id: (zone_risks.get(s.zone_id, s.risk_category) or "LOW").upper() for s in segments}
    graph_available = len(segments) >= 2
    normal_graph = _dijkstra(segments, from_lat, from_lng, to_lat, to_lng, "normal", risk_by_id) if graph_available else None
    safe_graph = _dijkstra(segments, from_lat, from_lng, to_lat, to_lng, "safe", risk_by_id) if graph_available else None
    balanced_graph = _dijkstra(segments, from_lat, from_lng, to_lat, to_lng, "balanced", risk_by_id) if graph_available else None

    if normal_graph:
        normal = {**normal_graph, "source":"flowstate_road_graph"}
    else:
        try:
            normal = _fetch_real_route(from_lat, from_lng, to_lat, to_lng)
            normal["risk"] = "LOW"
        except Exception:
            normal = _fallback_route(from_lat, from_lng, to_lat, to_lng)

    safe = safe_graph
    if safe:
        safe = {**safe, "source":"flowstate_safe_dijkstra"}
    else:
        # No safe path: never pretend a risky route is safe.
        safe = {"distance_km": normal["distance_km"], "duration_minutes": normal["duration_minutes"], "risk":"UNSAFE","source":"no_safe_path","geometry":normal.get("geometry",[]) }

    balanced = {**balanced_graph, "source":"flowstate_balanced_dijkstra"} if balanced_graph else None
    avoided = [s for s in (normal_graph["segments"] if normal_graph else []) if risk_by_id.get(s.id, (s.risk_category or "LOW")).upper() in ("HIGH","SEVERE")]
    return {
        "from":{"latitude":from_lat,"longitude":from_lng,"label":from_label},
        "to":{"latitude":to_lat,"longitude":to_lng,"label":to_label},
        "normal_route":normal,
        "safe_route":safe,
        "balanced_route":balanced,
        "avoided_segments":[s.to_dict() for s in avoided],
        "zones_considered":sorted({s.zone_id for s in (normal_graph["segments"] if normal_graph else [])}),
        "explanation": (
            "Shortest route through currently safe road segments." if safe_graph else
            "No fully safe connected route was found. The system does not label the normal route as safe."
        ),
        "street_level": bool(normal_graph),
    }
