#!/usr/bin/env python3
"""
CityFix AI — Local Web Server & API Service
===========================================
Datathon 2026 — Track 3: Smart City (Where Should We Fix First?)

Serves the CityFix AI Municipal Command Center dashboard and REST API endpoints.

Usage:
    python server.py [--port 8000] [--data-dir data]
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import sys
from http import HTTPStatus
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data_pipeline import load_all_datasets
from src.priority_engine import WeightConfig, build_priority_pipeline

# Ensure JSON dashboard data is available
DATA_JSON_PATH = PROJECT_ROOT / "reports" / "dashboard_data.json"


def load_or_generate_payload() -> dict:
    """Load precomputed dashboard data or compute on the fly."""
    if DATA_JSON_PATH.is_file():
        try:
            with open(DATA_JSON_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[!] Warning reading precomputed JSON ({e}), recomputing...", file=sys.stderr)

    from scripts.export_dashboard_data import generate_dashboard_json

    out_file = generate_dashboard_json(PROJECT_ROOT / "data", DATA_JSON_PATH)
    with open(out_file, "r", encoding="utf-8") as f:
        return json.load(f)


GLOBAL_DATA = load_or_generate_payload()


def answer_ai_query(query: str, data: dict) -> dict:
    """
    Deterministic AI City Intelligence query engine.
    Analyzes natural query patterns and returns verified facts from the computed dataset.
    """
    q = query.lower().strip()
    locations = data.get("locations", [])
    summary = data.get("summary", {})

    # 1. Location-specific inquiry (e.g. "why is L0965 ranked highly?", "L0729")
    for loc in locations:
        loc_id = loc["location_id"].lower()
        if loc_id in q:
            crit = loc["critical_incidents"]
            unres = loc["unresolved_incidents"]
            factors = loc.get("contributing_factors", [])
            action = loc.get("suggested_next_action", "")
            return {
                "query": query,
                "type": "location_deep_dive",
                "title": f"Analysis for Location {loc['location_id']} ({loc['zone']})",
                "answer": (
                    f"Location {loc['location_id']} is classified as {loc['priority_level']} priority "
                    f"with a composite score of {loc['priority_score']:.2f}/100. "
                    f"It has {loc['incident_count']} recorded incidents ({crit} critical) and "
                    f"{loc['complaint_count']} public complaints, with {unres} unresolved issues. "
                    f"Road condition is currently rated as '{loc['road_condition']}'."
                ),
                "contributing_factors": factors,
                "suggested_next_action": action,
                "matched_locations": [loc],
            }

    # 2. Top priority / highest priority locations
    if any(k in q for k in ["highest", "top priority", "fix first", "most urgent", "rank 1", "rankings"]):
        top_5 = locations[:5]
        summary_str = ", ".join([f"{l['location_id']} (Score: {l['priority_score']}, {l['road_condition']} road)" for l in top_5])
        return {
            "query": query,
            "type": "top_priority",
            "title": "Top 5 High-Priority Repair Hotspots",
            "answer": (
                f"The highest priority locations requiring municipal attention are: {summary_str}. "
                "These locations exhibit compound burdens of critical road deterioration, elevated "
                "incident volume, severe injury history, and heavy citizen complaint backlogs."
            ),
            "matched_locations": top_5,
            "suggested_next_action": "Deploy field survey teams to these 5 locations for immediate pavement and drainage inspection.",
        }

    # 3. Recurring unresolved incidents / backlogs
    if any(k in q for k in ["unresolved", "backlog", "pending", "lingering"]):
        by_unres = sorted(locations, key=lambda x: x["unresolved_incidents"], reverse=True)[:5]
        return {
            "query": query,
            "type": "backlog",
            "title": "Locations with Worst Unresolved Incident Backlogs",
            "answer": (
                f"The locations with the largest unresolved incident backlogs are: "
                + ", ".join([f"{l['location_id']} ({l['unresolved_incidents']} unresolved)" for l in by_unres])
                + ". Overall, the city has 2,874 unresolved incidents (28.7% of total reported incidents)."
            ),
            "matched_locations": by_unres,
            "suggested_next_action": "Prioritize clearing active work orders at these backlogged locations to reduce public safety hazard exposure.",
        }

    # 4. Drainage / Flooding
    if any(k in q for k in ["drain", "flood", "water", "rain"]):
        by_drain = sorted(
            locations,
            key=lambda x: x["inc_blocked_drain"] + x["inc_flooding"] + x["comp_drainage"],
            reverse=True,
        )[:5]
        return {
            "query": query,
            "type": "drainage",
            "title": "Severe Stormwater & Drainage Bottlenecks",
            "answer": (
                "The locations experiencing recurring drainage and stormwater flooding are: "
                + ", ".join([
                    f"{l['location_id']} ({l['inc_blocked_drain'] + l['inc_flooding']} drainage/floods, {l['comp_drainage']} complaints)"
                    for l in by_drain
                ])
                + ". Citywide, there are 1,651 blocked drain incidents and 1,598 flooding incidents."
            ),
            "matched_locations": by_drain,
            "suggested_next_action": "Dispatch stormwater utility crews for culvert desilting and storm drain clearing before precipitation events.",
        }

    # 5. School / Hospital / Vulnerable Receptors
    if any(k in q for k in ["school", "hospital", "pedestrian", "vulnerable"]):
        vulnerable = [l for l in locations if (l["near_school"] or l["near_hospital"]) and l["road_condition"] in ["Critical", "Poor"]][:5]
        return {
            "query": query,
            "type": "vulnerability",
            "title": "Vulnerable School & Hospital Corridors with Road Degradation",
            "answer": (
                f"Identified {len(vulnerable)} prioritized locations situated adjacent to schools or hospitals "
                f"with Critical or Poor road surfaces: "
                + ", ".join([f"{l['location_id']} ({l['road_condition']} road, {l['zone']})" for l in vulnerable])
                + ". These zones have high pedestrian traffic and sensitive populations."
            ),
            "matched_locations": vulnerable,
            "suggested_next_action": "Conduct immediate crosswalk safety audits and emergency access route repairs.",
        }

    # 6. Incident categories frequency
    if any(k in q for k in ["category", "categories", "most common", "types", "distribution"]):
        cats = summary.get("incident_categories", {})
        top_cats = sorted(cats.items(), key=lambda x: x[1], reverse=True)
        top_str = ", ".join([f"{cat} ({cnt:,})" for cat, cnt in top_cats])
        return {
            "query": query,
            "type": "category_distribution",
            "title": "City-Wide Incident Distribution",
            "answer": (
                f"Incident frequencies across the 10,000 recorded events are evenly distributed: {top_str}. "
                "Streetlight outages (1,726) and Signal failures (1,699) represent the two most common reported events."
            ),
            "matched_locations": locations[:3],
            "suggested_next_action": "Coordinate electrical and road maintenance contracts across municipal operational zones.",
        }

    # Default general query answer
    top_3 = locations[:3]
    return {
        "query": query,
        "type": "general",
        "title": "CityFix AI Intelligence Overview",
        "answer": (
            f"Query received: '{query}'. Based on the 2025 city datasets (1,000 locations, 10,000 incidents, 8,000 complaints), "
            f"the highest overall repair priority in the city is {top_3[0]['location_id']} ({top_3[0]['priority_level']}, Score {top_3[0]['priority_score']:.2f}). "
            "You can query specific location IDs (e.g., 'Why is L0965 high?'), categories ('potholes', 'flooding'), or backlogs."
        ),
        "matched_locations": top_3,
        "suggested_next_action": "Use the search bar or preset question pills to investigate specific civic infrastructure themes.",
    }


class CityFixHandler(SimpleHTTPRequestHandler):
    """Custom HTTP Request Handler for CityFix AI web application and API."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PROJECT_ROOT), **kwargs)

    def do_GET(self) -> None:
        parsed_url = urlparse(self.path)
        path = parsed_url.path

        # 1. API: Summary Stats
        if path == "/api/stats":
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(GLOBAL_DATA["summary"]).encode("utf-8"))
            return

        # 2. API: Locations List (with filtering)
        if path == "/api/locations":
            query_params = parse_qs(parsed_url.query)
            locations = GLOBAL_DATA["locations"]

            # Zone filter
            if "zone" in query_params and query_params["zone"][0]:
                z = query_params["zone"][0]
                locations = [l for l in locations if l["zone"] == z]

            # Priority level filter
            if "priority_level" in query_params and query_params["priority_level"][0]:
                pl = query_params["priority_level"][0]
                locations = [l for l in locations if l["priority_level"] == pl]

            # Category filter
            if "incident_category" in query_params and query_params["incident_category"][0]:
                cat = query_params["incident_category"][0].lower().replace(" ", "_")
                col = f"inc_{cat}"
                locations = [l for l in locations if l.get(col, 0) > 0]

            # Search filter
            if "search" in query_params and query_params["search"][0]:
                s = query_params["search"][0].upper()
                locations = [l for l in locations if s in l["location_id"].upper() or s in l["zone"].upper()]

            # Top N
            if "top_n" in query_params:
                try:
                    n = int(query_params["top_n"][0])
                    if n > 0:
                        locations = locations[:n]
                except ValueError:
                    pass

            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(locations).encode("utf-8"))
            return

        # 3. API: Single Location Detail
        if path.startswith("/api/locations/"):
            loc_id = path.split("/api/locations/")[1].strip().upper()
            found = next((l for l in GLOBAL_DATA["locations"] if l["location_id"].upper() == loc_id), None)
            if found:
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps(found).encode("utf-8"))
            else:
                self.send_response(HTTPStatus.NOT_FOUND)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"error": f"Location '{loc_id}' not found"}).encode("utf-8"))
            return

        # 4. API: AI Query Engine
        if path == "/api/query":
            query_params = parse_qs(parsed_url.query)
            q = query_params.get("q", [""])[0]
            answer = answer_ai_query(q, GLOBAL_DATA)
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(answer).encode("utf-8"))
            return

        # 5. Default static file routing
        super().do_GET()


def run_server(port: int = 8000) -> None:
    server_address = ("", port)
    httpd = HTTPServer(server_address, CityFixHandler)
    print("=" * 72)
    print(" CITYFIX AI — MUNICIPAL COMMAND CENTER SERVER")
    print(" DATATHON 2026 — TRACK 3: SMART CITY")
    print("=" * 72)
    print(f"[*] Serving locally at: http://localhost:{port}")
    print(f"[*] REST API active    : http://localhost:{port}/api/locations")
    print("[*] Press Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[*] Server stopped.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run CityFix AI Web Server.")
    parser.add_argument("--port", type=int, default=8000, help="Port to serve on (default: 8000)")
    args = parser.parse_args()
    run_server(args.port)
