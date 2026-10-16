#!/usr/bin/env python3
"""
CityFix AI — Export Dashboard Data JSON
=======================================
Datathon 2026 — Track 3: Smart City (Where Should We Fix First?)

Exports computed priority metrics, city-wide summaries, and explanations
into a JSON payload for the web dashboard.

Usage:
    python scripts/export_dashboard_data.py [--output reports/dashboard_data.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data_pipeline import load_all_datasets
from src.priority_engine import WeightConfig, build_priority_pipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export dashboard data JSON for CityFix AI web application."
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default=str(PROJECT_ROOT / "data"),
        help="Path to data directory (default: data)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(PROJECT_ROOT / "reports" / "dashboard_data.json"),
        help="Path to output JSON file (default: reports/dashboard_data.json)",
    )
    return parser.parse_args()


def generate_dashboard_json(data_dir: Path | str, output_path: Path | str) -> Path:
    out_file = Path(output_path).resolve()
    out_file.parent.mkdir(parents=True, exist_ok=True)

    data = load_all_datasets(data_dir)
    inc = data["incidents"]
    comp = data["public_complaints"]
    loc = data["locations"]

    config = WeightConfig()
    ranked_df = build_priority_pipeline(data_dir, config=config)

    summary = {
        "total_locations": int(len(loc)),
        "total_incidents": int(len(inc)),
        "total_complaints": int(len(comp)),
        "total_unresolved_incidents": int((inc["resolved"] == 0).sum()),
        "total_open_complaints": int(
            comp["status"].isin(["Open", "In progress", "Assigned"]).sum()
        ),
        "total_injuries": int(inc["injuries"].sum()),
        "severity_distribution": {
            str(k): int(v) for k, v in inc["severity"].value_counts().items()
        },
        "incident_categories": {
            str(k): int(v) for k, v in inc["incident_type"].value_counts().items()
        },
        "complaint_categories": {
            str(k): int(v) for k, v in comp["category"].value_counts().items()
        },
        "complaint_statuses": {
            str(k): int(v) for k, v in comp["status"].value_counts().items()
        },
        "priority_tiers": {
            str(k): int(v) for k, v in ranked_df["priority_level"].value_counts().items()
        },
        "zones": sorted(loc["zone"].unique().tolist()),
        "road_conditions": {
            str(k): int(v) for k, v in loc["road_condition"].value_counts().items()
        },
        "road_types": {
            str(k): int(v) for k, v in loc["road_type"].value_counts().items()
        },
    }

    records = []
    for _, row in ranked_df.iterrows():
        rec = {
            "location_id": str(row["location_id"]),
            "zone": str(row["zone"]),
            "latitude": float(row["latitude"]),
            "longitude": float(row["longitude"]),
            "road_type": str(row["road_type"]),
            "road_condition": str(row["road_condition"]),
            "population_density": int(row["population_density_per_km2"]),
            "near_school": int(row["near_school"]),
            "near_hospital": int(row["near_hospital"]),
            "pedestrian_activity": str(row["pedestrian_activity"]),
            "incident_count": int(row["incident_count"]),
            "critical_incidents": int(row["critical_incidents"]),
            "high_incidents": int(row["high_incidents"]),
            "medium_incidents": int(row["medium_incidents"]),
            "low_incidents": int(row["low_incidents"]),
            "unresolved_incidents": int(row["unresolved_incidents"]),
            "resolved_incidents": int(row["resolved_incidents"]),
            "total_injuries": int(row["total_injuries"]),
            "complaint_count": int(row["complaint_count"]),
            "high_priority_complaints": int(row["high_priority_complaints"]),
            "open_complaints": int(row["open_complaints"]),
            "subscore_incident": float(row["subscore_incident"]),
            "subscore_backlog": float(row["subscore_backlog"]),
            "subscore_vulnerability": float(row["subscore_vulnerability"]),
            "subscore_complaint": float(row["subscore_complaint"]),
            "priority_score": float(row["priority_score"]),
            "priority_level": str(row["priority_level"]),
            "inc_pothole": int(row["inc_pothole"]),
            "inc_flooding": int(row["inc_flooding"]),
            "inc_collision": int(row["inc_collision"]),
            "inc_blocked_drain": int(row["inc_blocked_drain"]),
            "inc_signal_failure": int(row["inc_signal_failure"]),
            "inc_streetlight_outage": int(row["inc_streetlight_outage"]),
            "comp_road_damage": int(row["comp_road_damage"]),
            "comp_traffic": int(row["comp_traffic"]),
            "comp_lighting": int(row["comp_lighting"]),
            "comp_waste": int(row["comp_waste"]),
            "comp_pedestrian_safety": int(row["comp_pedestrian_safety"]),
            "comp_drainage": int(row["comp_drainage"]),
            "severity_breakdown": row["severity_breakdown"],
            "major_incident_categories": row["major_incident_categories"],
            "major_complaint_categories": row["major_complaint_categories"],
            "contributing_factors": (
                row["contributing_factors"].split("; ")
                if isinstance(row["contributing_factors"], str)
                else []
            ),
            "missing_evidence_or_limitations": (
                row["missing_evidence_or_limitations"].split("; ")
                if isinstance(row["missing_evidence_or_limitations"], str)
                else []
            ),
            "suggested_next_action": str(row["suggested_next_action"]),
        }
        records.append(rec)

    dashboard_payload = {
        "summary": summary,
        "locations": records,
        "metadata": {
            "project": "CityFix AI — Datathon 2026 Track 3: Smart City",
            "scoring_formula": "0.35 * S_incident + 0.25 * S_backlog + 0.25 * S_vulnerability + 0.15 * S_complaint",
            "disclaimer": "Synthetic educational dataset created for Datathon 2026. Coordinates and records are simulated and must not be used for actual public safety decisions.",
        },
    }

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(dashboard_payload, f, indent=2)

    return out_file


def main() -> int:
    args = parse_args()
    out = generate_dashboard_json(args.data_dir, args.output)
    print(f"[+] Successfully exported dashboard JSON to: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
