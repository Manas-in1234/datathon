#!/usr/bin/env python3
"""
CityFix AI — Dataset Validation CLI Script
==========================================
Datathon 2026 — Track 3: Smart City (Where Should We Fix First?)

Usage:
    python scripts/validate_data.py [--data-dir data] [--output-report reports/data_validation_report.md] [--strict]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add project root to sys.path to ensure src imports work cleanly
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data_pipeline import (
    export_validation_report,
    format_validation_report,
    run_validation_pipeline,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate CityFix AI Datasets (locations, incidents, complaints)."
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default=str(PROJECT_ROOT / "data"),
        help="Path to data directory containing CSV files and README.txt (default: data)",
    )
    parser.add_argument(
        "--output-report",
        type=str,
        default=str(PROJECT_ROOT / "reports" / "data_validation_report.md"),
        help="Path where the Markdown validation report should be saved (default: reports/data_validation_report.md)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with non-zero code if schema or relational validation fails.",
    )
    return parser.parse_args()


def print_banner() -> None:
    print("=" * 72)
    print(" CITYFIX AI — DATASET INSPECTION & VALIDATION PIPELINE")
    print(" DATATHON 2026 — TRACK 3: SMART CITY")
    print("=" * 72)


def main() -> int:
    args = parse_args()
    print_banner()

    data_dir = Path(args.data_dir).resolve()
    report_path = Path(args.output_report).resolve()

    print(f"[*] Target Data Directory: {data_dir}")
    print(f"[*] Report Output Destination: {report_path}")
    print(f"[*] Strict Mode: {'Enabled' if args.strict else 'Disabled'}\n")

    try:
        results = run_validation_pipeline(data_dir)
    except FileNotFoundError as err:
        print(f"\n[!] ERROR: Missing file or directory: {err}", file=sys.stderr)
        return 1
    except Exception as err:
        print(f"\n[!] UNEXPECTED ERROR during validation: {err}", file=sys.stderr)
        return 1

    schemas = results["schemas"]
    rel = results["relationships"]
    qual = results["quality"]
    overall = results["overall_status"]

    print("------------------------------------------------------------------------")
    print(" 1. DATASET DIMENSIONS & SCHEMAS")
    print("------------------------------------------------------------------------")
    for name, s in schemas.items():
        status_flag = "[PASS]" if s["schema_passed"] else "[FAIL]"
        print(f"  {status_flag} {name:<18}: {s['rows']:>6,} rows | {s['columns']:>2} cols | Nulls: {sum(s['null_counts'].values())} | Dupes: {s['full_row_duplicates']}")
        if not s["schema_passed"]:
            if s["missing_columns"]:
                print(f"       -> Missing columns: {s['missing_columns']}")
            if not s["primary_key_unique"]:
                print(f"       -> Primary key '{s['primary_key']}' is NOT unique!")

    print("\n------------------------------------------------------------------------")
    print(" 2. RELATIONAL INTEGRITY (Foreign Key: location_id)")
    print("------------------------------------------------------------------------")
    rel_flag = "[PASS]" if rel["referential_integrity_passed"] else "[FAIL]"
    print(f"  {rel_flag} Master Locations Count       : {rel['total_locations']:,}")
    print(f"  {rel_flag} Unmatched Incidents IDs     : {rel['unmatched_incidents_count']}")
    print(f"  {rel_flag} Unmatched Complaints IDs    : {rel['unmatched_complaints_count']}")
    print(f"  [*] Locations with 0 Incidents       : {rel['locations_without_incidents_count']}")
    print(f"  [*] Locations with 0 Complaints      : {rel['locations_without_complaints_count']}")
    print(f"  [*] Incidents per Location           : Min {rel['incidents_per_location_cardinality']['min']}, Median {rel['incidents_per_location_cardinality']['median']}, Max {rel['incidents_per_location_cardinality']['max']}, Mean {rel['incidents_per_location_cardinality']['mean']}")
    print(f"  [*] Complaints per Location          : Min {rel['complaints_per_location_cardinality']['min']}, Median {rel['complaints_per_location_cardinality']['median']}, Max {rel['complaints_per_location_cardinality']['max']}, Mean {rel['complaints_per_location_cardinality']['mean']}")

    print("\n------------------------------------------------------------------------")
    print(" 3. TEMPORAL COVERAGE (Timestamps)")
    print("------------------------------------------------------------------------")
    ts = qual["timestamp_ranges"]
    print(f"  [PASS] incidents.csv timestamp      : {ts['incidents']['min_timestamp']} -> {ts['incidents']['max_timestamp']} (Span: {ts['incidents']['span_days']} days)")
    print(f"  [PASS] complaints.csv created_at    : {ts['public_complaints']['min_timestamp']} -> {ts['public_complaints']['max_timestamp']} (Span: {ts['public_complaints']['span_days']} days)")

    print("\n------------------------------------------------------------------------")
    print(" 4. DATA QUALITY & SEMANTIC ANOMALIES")
    print("------------------------------------------------------------------------")
    anom = qual["semantic_anomalies"]
    print(f"  [!] Note: {anom['incidents_unresolved_with_resolution_hours']['unresolved_with_resolution_hours_count']} unresolved incidents (resolved=0) contain resolution_hours (Mean: {anom['incidents_unresolved_with_resolution_hours']['unresolved_resolution_hours_mean']}h).")
    print(f"  [!] Note: {anom['complaints_non_resolved_with_days_to_resolution']['non_resolved_complaints_count']} open/active complaints contain days_to_resolution.")
    print("  [*] Reason: Synthetic dataset generator unconditionally populates durations.")

    print("\n------------------------------------------------------------------------")
    print(f" OVERALL VALIDATION STATUS: {overall}")
    print("------------------------------------------------------------------------")

    # Export markdown report
    saved_path = export_validation_report(results, report_path)
    print(f"[+] Markdown validation report successfully written to:\n    {saved_path}\n")

    if args.strict and overall != "PASSED":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
