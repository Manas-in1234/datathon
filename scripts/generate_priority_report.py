#!/usr/bin/env python3
"""
CityFix AI — Location Priority Report Generator
===============================================
Datathon 2026 — Track 3: Smart City (Where Should We Fix First?)

Executes the Stage 2 Explainable Priority Engine and generates:
- reports/location_priority_report.csv
- reports/location_priority_summary.md

Usage:
    python scripts/generate_priority_report.py [--data-dir data] [--output-csv reports/location_priority_report.csv] [--output-summary reports/location_priority_summary.md]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.priority_engine import WeightConfig, build_priority_pipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate CityFix AI Location Priority Report and Summary."
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default=str(PROJECT_ROOT / "data"),
        help="Path to data directory containing CSV files (default: data)",
    )
    parser.add_argument(
        "--output-csv",
        type=str,
        default=str(PROJECT_ROOT / "reports" / "location_priority_report.csv"),
        help="Path where the location priority CSV should be saved (default: reports/location_priority_report.csv)",
    )
    parser.add_argument(
        "--output-summary",
        type=str,
        default=str(PROJECT_ROOT / "reports" / "location_priority_summary.md"),
        help="Path where the Markdown summary report should be saved (default: reports/location_priority_summary.md)",
    )
    return parser.parse_args()


def format_summary_markdown(df, config: WeightConfig) -> str:
    """Format an executive Markdown summary of the location ranking results."""
    total_locations = len(df)
    level_counts = df["priority_level"].value_counts().to_dict()
    top_10 = df.head(10)

    # Top incident categories across all locations
    inc_cat_sums = {
        "Pothole": int(df["inc_pothole"].sum()),
        "Flooding": int(df["inc_flooding"].sum()),
        "Collision": int(df["inc_collision"].sum()),
        "Blocked drain": int(df["inc_blocked_drain"].sum()),
        "Signal failure": int(df["inc_signal_failure"].sum()),
        "Streetlight outage": int(df["inc_streetlight_outage"].sum()),
    }
    sorted_inc_cats = sorted(inc_cat_sums.items(), key=lambda x: x[1], reverse=True)

    # Top complaint categories across all locations
    comp_cat_sums = {
        "Road damage": int(df["comp_road_damage"].sum()),
        "Traffic": int(df["comp_traffic"].sum()),
        "Lighting": int(df["comp_lighting"].sum()),
        "Waste": int(df["comp_waste"].sum()),
        "Pedestrian safety": int(df["comp_pedestrian_safety"].sum()),
        "Drainage": int(df["comp_drainage"].sum()),
    }
    sorted_comp_cats = sorted(comp_cat_sums.items(), key=lambda x: x[1], reverse=True)

    lines = [
        "# CityFix AI — Location Priority Engine Summary Report",
        "",
        "**Track**: Datathon 2026 — Track 3: Smart City  ",
        "**Problem Statement**: *Where Should We Fix First?*  ",
        "**Stage**: Stage 2 — Explainable Priority Engine & Municipal Triage  ",
        "",
        "---",
        "",
        "## 1. Executive Summary",
        "",
        f"The CityFix AI Priority Engine evaluated **{total_locations:,}** civic locations by synthesizing "
        "historical physical incidents, citizen 311 complaints, and infrastructural context. "
        "The scoring methodology is deterministic, transparent, and multi-pillared.",
        "",
        "### Priority Level Distribution",
        "",
        "| Priority Level | Score Range | Location Count | % of City Locations | Recommended Municipal Posture |",
        "| :--- | :---: | :---: | :---: | :--- |",
        f"| **Critical** | ≥ {config.critical_threshold:.1f} | **{level_counts.get('Critical', 0):,}** | {level_counts.get('Critical', 0)/total_locations*100:.1f}% | Immediate inter-departmental field inspection & urgent remediation |",
        f"| **High** | {config.high_threshold:.1f} – {config.critical_threshold:.1f} | **{level_counts.get('High', 0):,}** | {level_counts.get('High', 0)/total_locations*100:.1f}% | Scheduled work orders within active 14-day cycle |",
        f"| **Medium** | {config.medium_threshold:.1f} – {config.high_threshold:.1f} | **{level_counts.get('Medium', 0):,}** | {level_counts.get('Medium', 0)/total_locations*100:.1f}% | Planned routine maintenance & preventive cleaning |",
        f"| **Low** | < {config.medium_threshold:.1f} | **{level_counts.get('Low', 0):,}** | {level_counts.get('Low', 0)/total_locations*100:.1f}% | Monitoring status / no immediate hazard backlog |",
        "",
        "---",
        "",
        "## 2. Top 10 Highest-Priority Locations",
        "",
        "The table below details the top 10 locations requiring municipal prioritization, along with their key driving factors:",
        "",
        "| Rank | Location ID | Zone | Priority Score | Level | Road Cond. | Incidents (Crit/High) | Complaints | Injuries | Backlog | Primary Suggested Action |",
        "| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |",
    ]

    for rank, (_, row) in enumerate(top_10.iterrows(), start=1):
        crit = int(row["critical_incidents"])
        high = int(row["high_incidents"])
        unres = int(row["unresolved_incidents"])
        inj = int(row["total_injuries"])
        action = str(row["suggested_next_action"])
        # Truncate action for table readability
        short_action = action.split(".")[0] + "." if "." in action else action
        lines.append(
            f"| {rank} | `{row['location_id']}` | {row['zone']} | **{row['priority_score']:.2f}** | `{row['priority_level']}` | {row['road_condition']} | {int(row['incident_count'])} ({crit}/{high}) | {int(row['complaint_count'])} | {inj} | {unres} | {short_action} |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## 3. Most Common Civic Issue Categories",
        "",
        "### Incident Types (Verified Disruptions)",
        "| Incident Category | Total Recorded Incidents | % of Incident Volume |",
        "| :--- | :---: | :---: |",
    ])
    total_incidents = sum(inc_cat_sums.values())
    for cat, cnt in sorted_inc_cats:
        lines.append(f"| {cat} | {cnt:,} | {cnt/total_incidents*100:.1f}% |")

    lines.extend([
        "",
        "### Citizen Complaints (Public 311 Demands)",
        "| Complaint Category | Total Recorded Complaints | % of Complaint Volume |",
        "| :--- | :---: | :---: |",
    ])
    total_complaints = sum(comp_cat_sums.values())
    for cat, cnt in sorted_comp_cats:
        lines.append(f"| {cat} | {cnt:,} | {cnt/total_complaints*100:.1f}% |")

    lines.extend([
        "",
        "---",
        "",
        "## 4. Scoring Methodology & Mathematical Formulation",
        "",
        "The CityFix AI Priority Engine synthesizes four normalized subscores into a deterministic 0–100 index:",
        "",
        r"$$\text{Priority Score} = w_{\text{incident}} S_{\text{incident}} + w_{\text{backlog}} S_{\text{backlog}} + w_{\text{vulnerability}} S_{\text{vulnerability}} + w_{\text{complaint}} S_{\text{complaint}}$$",
        "",
        "### Component Definitions & Configured Weights:",
        f"1. **Incident Hazard Subscore ($S_{{\\text{{incident}}}}$, Weight: {config.incident_weight:.2f})**:",
        "   - Computes weighted incident severity: $4 \\times \\text{Critical} + 3 \\times \\text{High} + 2 \\times \\text{Medium} + 1 \\times \\text{Low} + 2 \\times \\text{Injuries} + \\text{Frequency}$.",
        "   - Normalized across the city distribution to $[0, 100]$.",
        f"2. **Backlog & Unresolved Burden ($S_{{\\text{{backlog}}}}$, Weight: {config.backlog_weight:.2f})**:",
        "   - Quantifies pending physical hazard exposure: $2.5 \\times \\text{Unresolved Incidents} + 1.0 \\times \\text{Open Complaints}$.",
        "   - Normalized to $[0, 100]$.",
        f"3. **Vulnerability & Exposure Subscore ($S_{{\\text{{vulnerability}}}}$, Weight: {config.vulnerability_weight:.2f})**:",
        "   - Evaluates surrounding receptors and structural health:",
        "     - Road condition: Critical (35 pts), Poor (25 pts), Fair (12 pts), Good (0 pts).",
        "     - School proximity: +20 pts.",
        "     - Hospital proximity: +20 pts.",
        "     - Pedestrian density: High (15 pts), Medium (8 pts), Low (0 pts).",
        "     - Population density: Scaled up to 10 pts.",
        f"4. **Citizen Demand Subscore ($S_{{\\text{{complaint}}}}$, Weight: {config.complaint_weight:.2f})**:",
        "   - Incorporates community reporting pressure: $1.0 \\times \\text{Total Complaints} + 2.0 \\times \\text{High Priority} + 0.5 \\times \\text{Normal Priority}$.",
        "   - Normalized to $[0, 100]$.",
        "",
        "---",
        "",
        "## 5. Limitations & Boundary Assumptions",
        "",
        "> [!IMPORTANT]",
        "> 1. **Synthetic Educational Data**: Coordinates and civic records are simulated for the Datathon 2026 educational challenge per `data/README.txt` and must not be used for real municipal dispatch.",
        "> 2. **Unresolved Durations**: In accordance with Stage 1 validation findings, recorded resolution hours for unresolved items were excluded from scoring to prevent target leakage.",
        "> 3. **Complaints vs. Incidents**: Citizen complaints represent public reporting sentiment; they are not assumed to have 1:1 correspondence with distinct physical structural failures.",
        "> 4. **Heuristic Weights**: The scoring weights represent configurable municipal policy choices and are not claimed to be an absolute ground-truth optimum.",
        "> 5. **Advisory Framing**: Suggested next actions are algorithmic recommendations for municipal crew triage and survey, not confirmed engineering diagnoses.",
        "",
        "---",
        "**Report Generated By**: CityFix AI Priority Engine (Stage 2)  ",
        "**Data Source**: `data/locations.csv`, `data/incidents.csv`, `data/public_complaints.csv`  ",
    ])

    return "\n".join(lines)


def main() -> int:
    args = parse_args()

    data_dir = Path(args.data_dir).resolve()
    csv_out = Path(args.output_csv).resolve()
    summary_out = Path(args.output_summary).resolve()

    print("=" * 72)
    print(" CITYFIX AI — EXPLAINABLE LOCATION-PRIORITY REPORT GENERATOR")
    print(" DATATHON 2026 — TRACK 3: SMART CITY")
    print("=" * 72)
    print(f"[*] Input Data Directory : {data_dir}")
    print(f"[*] Output CSV Report    : {csv_out}")
    print(f"[*] Output Summary MD    : {summary_out}\n")

    try:
        config = WeightConfig()
        ranked_df = build_priority_pipeline(data_dir, config=config)
    except FileNotFoundError as err:
        print(f"[!] Error: {err}", file=sys.stderr)
        return 1
    except Exception as err:
        print(f"[!] Unexpected error during pipeline execution: {err}", file=sys.stderr)
        return 1

    # Ensure parent directories exist
    csv_out.parent.mkdir(parents=True, exist_ok=True)
    summary_out.parent.mkdir(parents=True, exist_ok=True)

    # 1. Export CSV
    ranked_df.to_csv(csv_out, index=False)
    print(f"[+] Priority Report CSV exported ({len(ranked_df)} rows):\n    {csv_out}")

    # 2. Export Summary Markdown
    summary_md = format_summary_markdown(ranked_df, config)
    with open(summary_out, "w", encoding="utf-8") as f:
        f.write(summary_md)
    print(f"[+] Priority Summary Markdown exported:\n    {summary_out}\n")

    # Console Highlights
    print("------------------------------------------------------------------------")
    print(" TOP 5 PRIORITIZED LOCATIONS FOR MUNICIPAL INTERVENTION")
    print("------------------------------------------------------------------------")
    top_5 = ranked_df.head(5)
    for idx, (_, row) in enumerate(top_5.iterrows(), start=1):
        print(
            f"  #{idx} [{row['location_id']}] {row['zone']} | Score: {row['priority_score']} ({row['priority_level']}) | "
            f"Road: {row['road_condition']} | Incidents: {row['incident_count']} (Crit: {row['critical_incidents']}) | "
            f"Backlog: {row['unresolved_incidents']}"
        )
        print(f"      Action: {row['suggested_next_action']}\n")

    print("------------------------------------------------------------------------")
    counts = ranked_df["priority_level"].value_counts().to_dict()
    print(f" PRIORITY TIERS: Critical: {counts.get('Critical', 0)} | High: {counts.get('High', 0)} | Medium: {counts.get('Medium', 0)} | Low: {counts.get('Low', 0)}")
    print("------------------------------------------------------------------------")
    print("[*] Stage 2 Priority Engine execution complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
