"""Build the browser-side aggregate from the supplied synthetic CSV files.

Applies strict data quality rules:
- Unresolved incidents (resolved == 0) are excluded from completed turnaround-time metrics.
- Open/Assigned/In-progress complaints are excluded from completed turnaround-time metrics.
- Preserves raw CSV contents without modification.
- Enriches location aggregates with severity distributions, category counts, and resolution metrics.
"""

from __future__ import annotations

import csv
import gzip
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data" / "raw" / "03_smart_city_where_fix_first"
OUT = ROOT / "data.js"
RECORDS_OUT = ROOT / "records.json.gz"


def read_csv(name: str) -> list[dict[str, str]]:
    with (RAW / name).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def number(value: str | None, default: float = 0.0) -> float:
    if value is None or str(value).strip().lower() in {"", "na", "n/a", "null", "none"}:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def main() -> None:
    locations = read_csv("locations.csv")
    incidents = read_csv("incidents.csv")
    complaints = read_csv("public_complaints.csv")

    by_location: dict[str, dict] = {}
    records_by_location: dict[str, list[dict]] = defaultdict(list)

    for row in locations:
        by_location[row["location_id"]] = {
            "id": row["location_id"],
            "zone": row["zone"],
            "road": row["road_type"],
            "condition": row["road_condition"],
            "density": int(number(row["population_density_per_km2"])),
            "school": row["near_school"] == "1",
            "hospital": row["near_hospital"] == "1",
            "pedestrian": row["pedestrian_activity"],
            "lat": number(row["latitude"]),
            "lon": number(row["longitude"]),
            "simulated": True,
            # Incident counts
            "incidentCount": 0,
            "resolvedIncidents": 0,
            "unresolved": 0,
            "severityTotal": 0,
            "severityCount": 0,
            "highCritical": 0,
            "injuries": 0,
            "severityDistribution": {"Low": 0, "Medium": 0, "High": 0, "Critical": 0},
            "incidentTypes": {},
            "typeSeverity": {},
            # Completed turnaround metrics
            "incidentResolutionHoursSum": 0.0,
            "incidentResolutionCount": 0,
            # Complaint counts
            "complaintCount": 0,
            "highPriority": 0,
            "openComplaints": 0,
            "resolvedComplaints": 0,
            "complaintCategories": {},
            "complaintPriority": {"Low": 0, "Normal": 0, "High": 0},
            "complaintResolutionDaysSum": 0.0,
            "complaintResolutionCount": 0,
            # Time series (12 months)
            "monthIncidents": [0] * 12,
            "monthByType": {},
            "monthComplaints": [0] * 12,
            "monthResolvedIncidents": [0] * 12,
            "monthOpenIncidents": [0] * 12,
        }

    monthly_incidents = [0] * 12
    monthly_complaints = [0] * 12
    monthly_resolved_incidents = [0] * 12
    monthly_open_incidents = [0] * 12

    incident_type_totals: Counter[str] = Counter()
    complaint_cat_totals: Counter[str] = Counter()
    global_severity_counts: Counter[str] = Counter()

    severity_value = {"Low": 1, "Medium": 2, "High": 3, "Critical": 4}
    valid_incident_ids = set()
    valid_complaint_ids = set()
    unmatched_incident_locations = 0
    unmatched_complaint_locations = 0

    total_valid_incident_res_hours = 0.0
    total_valid_incident_res_count = 0
    excluded_unresolved_incident_turnaround = 0

    total_valid_complaint_res_days = 0.0
    total_valid_complaint_res_count = 0
    excluded_open_complaint_turnaround = 0

    for row in incidents:
        iid = row["incident_id"]
        valid_incident_ids.add(iid)
        loc = by_location.get(row["location_id"])
        if loc is None:
            unmatched_incident_locations += 1
            continue

        is_resolved = row["resolved"] == "1"
        res_hours_raw = number(row["resolution_hours"])

        # DATA QUALITY RULE: Only treat resolved incidents as completed turnaround times
        if is_resolved and res_hours_raw > 0:
            res_hours = round(res_hours_raw, 1)
            loc["incidentResolutionHoursSum"] += res_hours
            loc["incidentResolutionCount"] += 1
            total_valid_incident_res_hours += res_hours
            total_valid_incident_res_count += 1
        else:
            res_hours = None
            if not is_resolved and res_hours_raw > 0:
                excluded_unresolved_incident_turnaround += 1

        records_by_location[row["location_id"]].append({
            "id": iid,
            "kind": "Incident",
            "date": row["timestamp"],
            "type": row["incident_type"],
            "severity": row["severity"],
            "status": "Resolved" if is_resolved else "Open",
            "injuries": int(number(row["injuries"])),
            "reportedBy": row["reported_by"],
            "resolutionHours": res_hours,
        })

        kind = row["incident_type"]
        sev_label = row["severity"] if row["severity"] in severity_value else "Medium"
        severity = severity_value.get(sev_label, 2)

        loc["incidentCount"] += 1
        loc["severityTotal"] += severity
        loc["severityCount"] += 1
        loc["highCritical"] += int(severity >= 3)
        loc["injuries"] += int(number(row["injuries"]))
        loc["severityDistribution"][sev_label] = loc["severityDistribution"].get(sev_label, 0) + 1
        global_severity_counts[sev_label] += 1

        if is_resolved:
            loc["resolvedIncidents"] += 1
        else:
            loc["unresolved"] += 1

        loc["incidentTypes"][kind] = loc["incidentTypes"].get(kind, 0) + 1
        loc["typeSeverity"][kind] = loc["typeSeverity"].get(kind, 0) + severity
        incident_type_totals[kind] += 1

        month = datetime.strptime(row["timestamp"], "%Y-%m-%d %H:%M:%S").month - 1
        monthly_incidents[month] += 1
        loc["monthIncidents"][month] += 1
        loc["monthByType"].setdefault(kind, [0] * 12)[month] += 1
        if is_resolved:
            monthly_resolved_incidents[month] += 1
            loc["monthResolvedIncidents"][month] += 1
        else:
            monthly_open_incidents[month] += 1
            loc["monthOpenIncidents"][month] += 1

    for row in complaints:
        cid = row["complaint_id"]
        valid_complaint_ids.add(cid)
        loc = by_location.get(row["location_id"])
        if loc is None:
            unmatched_complaint_locations += 1
            continue

        raw_status = row["status"]
        is_closed_or_resolved = raw_status in {"Resolved", "Closed"}
        res_days_raw = number(row["days_to_resolution"])

        # DATA QUALITY RULE: Only treat resolved/closed complaints as completed turnaround times
        if is_closed_or_resolved and res_days_raw >= 0:
            res_days = round(res_days_raw, 1)
            loc["complaintResolutionDaysSum"] += res_days
            loc["complaintResolutionCount"] += 1
            total_valid_complaint_res_days += res_days
            total_valid_complaint_res_count += 1
        else:
            res_days = None
            if not is_closed_or_resolved and res_days_raw > 0:
                excluded_open_complaint_turnaround += 1

        records_by_location[row["location_id"]].append({
            "id": cid,
            "kind": "Complaint",
            "date": row["created_at"],
            "type": row["category"],
            "severity": row["priority_reported"],
            "status": raw_status,
            "resolutionDays": res_days,
        })

        loc["complaintCount"] += 1
        pri = row["priority_reported"]
        if pri == "High":
            loc["highPriority"] += 1
        loc["complaintPriority"][pri] = loc["complaintPriority"].get(pri, 0) + 1

        if raw_status in {"Open", "In progress", "Assigned"}:
            loc["openComplaints"] += 1
        else:
            loc["resolvedComplaints"] += 1

        category = row["category"]
        loc["complaintCategories"][category] = loc["complaintCategories"].get(category, 0) + 1
        complaint_cat_totals[category] += 1

        month = datetime.strptime(row["created_at"], "%Y-%m-%d %H:%M:%S").month - 1
        monthly_complaints[month] += 1
        loc["monthComplaints"][month] += 1

    for loc in by_location.values():
        loc["avgSeverity"] = round(loc["severityTotal"] / loc["severityCount"], 2) if loc["severityCount"] else 0.0
        del loc["severityTotal"]
        del loc["severityCount"]
        loc["topIssue"] = max(loc["incidentTypes"], key=loc["incidentTypes"].get) if loc["incidentTypes"] else "No incidents"
        loc["avgResolutionHours"] = round(loc["incidentResolutionHoursSum"] / loc["incidentResolutionCount"], 1) if loc["incidentResolutionCount"] else None
        loc["avgDaysToResolution"] = round(loc["complaintResolutionDaysSum"] / loc["complaintResolutionCount"], 1) if loc["complaintResolutionCount"] else None
        del loc["incidentResolutionHoursSum"]
        del loc["incidentResolutionCount"]
        del loc["complaintResolutionDaysSum"]
        del loc["complaintResolutionCount"]

    bundle = {
        "locations": list(by_location.values()),
        "months": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
        "monthlyIncidents": monthly_incidents,
        "monthlyComplaints": monthly_complaints,
        "monthlyResolvedIncidents": monthly_resolved_incidents,
        "monthlyOpenIncidents": monthly_open_incidents,
        "incidentTypes": sorted(incident_type_totals),
        "incidentTypeTotals": dict(incident_type_totals),
        "complaintCategories": sorted(complaint_cat_totals),
        "complaintCategoryTotals": dict(complaint_cat_totals),
        "severityCounts": dict(global_severity_counts),
        "summary": {
            "locations": len(locations),
            "incidents": len(incidents),
            "complaints": len(complaints),
            "openIncidents": len(incidents) - sum(loc["resolvedIncidents"] for loc in by_location.values()),
            "resolvedIncidents": sum(loc["resolvedIncidents"] for loc in by_location.values()),
            "openComplaints": sum(loc["openComplaints"] for loc in by_location.values()),
            "resolvedComplaints": sum(loc["resolvedComplaints"] for loc in by_location.values()),
            "avgCompletedIncidentResolutionHours": round(total_valid_incident_res_hours / max(1, total_valid_incident_res_count), 1),
            "avgCompletedComplaintResolutionDays": round(total_valid_complaint_res_days / max(1, total_valid_complaint_res_count), 1),
            "excludedUnresolvedTurnaroundRecords": excluded_unresolved_incident_turnaround + excluded_open_complaint_turnaround,
            "unmatchedIncidentLocations": unmatched_incident_locations,
            "unmatchedComplaintLocations": unmatched_complaint_locations,
            "uniqueIncidentIds": len(valid_incident_ids),
            "uniqueComplaintIds": len(valid_complaint_ids),
            "period": "Jan — Dec 2025",
            "synthetic": True,
            "simulatedCoordinates": True,
            "dataLimitations": [
                "Synthetic educational dataset created for DATATHON 2026.",
                "Map coordinates are simulated demo positions within a local bounding box.",
                "Citizen complaints and operational incidents may report identical physical events (potential overlap).",
                "Unresolved records with populated turnaround times were cleaned to prevent completion-time contamination."
            ],
        },
    }

    OUT.write_text("window.CITYFIX_DATA = " + json.dumps(bundle, separators=(",", ":")) + ";\n", encoding="utf-8")

    for items in records_by_location.values():
        items.sort(key=lambda item: item["date"], reverse=True)

    records_json = json.dumps(records_by_location, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    RECORDS_OUT.write_bytes(gzip.compress(records_json, mtime=0))

    print(f"Wrote {OUT.name}: {len(locations):,} locations, {len(incidents):,} incidents, {len(complaints):,} complaints")
    print(f"Wrote {RECORDS_OUT.name}: {len(records_json):,} bytes uncompressed ({len(RECORDS_OUT.read_bytes()):,} bytes compressed)")
    print(f"Completed turnaround data: {total_valid_incident_res_count:,} resolved incidents ({round(total_valid_incident_res_hours / total_valid_incident_res_count, 1)} hrs avg)")
    print(f"Completed complaints turnaround: {total_valid_complaint_res_count:,} resolved complaints ({round(total_valid_complaint_res_days / total_valid_complaint_res_count, 1)} days avg)")
    print(f"Excluded turnaround contamination: {excluded_unresolved_incident_turnaround} unresolved incidents + {excluded_open_complaint_turnaround} open complaints = {excluded_unresolved_incident_turnaround + excluded_open_complaint_turnaround} total")


if __name__ == "__main__":
    main()
