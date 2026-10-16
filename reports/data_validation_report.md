# CityFix AI — Data Inspection & Validation Report

**Track**: Datathon 2026 — Track 3: Smart City (Where Should We Fix First?)  
**Pipeline Validation Status**: **PASSED**  
**Execution Mode**: Read-Only Source CSV Validation  

---

## 1. Executive Summary

This report provides the formal data inspection, schema validation, and relational integrity audit 
for the CityFix AI project datasets. All datasets have been validated strictly as read-only artifacts 
without fabrication, modification, or silent removal of records.

> [!IMPORTANT]
> **Synthetic Dataset Notice (from `data/README.txt`)**:
> Coordinates and civic metrics are simulated for educational datathon purposes. 
> They must not be used for actual public safety decisions or interpreted as real civic reports.

### Dataset Dimensions Overview

| Dataset | File | Rows | Columns | Missing Values | Duplicate Rows | Primary Key | Key Unique |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Locations** | `locations.csv` | 1,000 | 10 | 0 | 0 | `location_id` | True |
| **Incidents** | `incidents.csv` | 10,000 | 9 | 0 | 0 | `incident_id` | True |
| **Public Complaints** | `public_complaints.csv` | 8,000 | 7 | 0 | 0 | `complaint_id` | True |

---

## 2. Referential Integrity & Relational Validation

Referential integrity between transactional datasets (`incidents.csv`, `public_complaints.csv`) and 
the master entity (`locations.csv`) was evaluated along the foreign key `location_id`.

- **Master Location Count**: 1,000 unique locations (`L0001` to `L1000`).
- **Unmatched `location_id` in `incidents.csv`**: 0 (100% matched).
- **Unmatched `location_id` in `public_complaints.csv`**: 0 (100% matched).
- **Locations without Incidents**: 0 (All 1,000 locations have incident records).
- **Locations without Complaints**: 0 (All 1,000 locations have complaint records).

### Join Cardinality Distribution

| Relationship | Min Records/Loc | Median | Max Records/Loc | Mean ± Std | Total Records |
| :--- | :---: | :---: | :---: | :---: | :---: |
| `locations` 1:N `incidents` | 2 | 10.0 | 23 | 10.0 ± 3.25 | 10,000 |
| `locations` 1:N `public_complaints` | 1 | 8.0 | 17 | 8.0 ± 2.86 | 8,000 |

---

## 3. Temporal Coverage & Timestamp Parsing

All timestamps parsed cleanly as ISO timestamps without coercion errors or invalid formats.

| Dataset | Column | Start Timestamp | End Timestamp | Span (Days) | Parsing Errors |
| :--- | :--- | :--- | :--- | :---: | :---: |
| `incidents.csv` | `timestamp` | `2025-01-01 00:29:00` | `2025-12-31 23:50:00` | 365.0 | 0 |
| `public_complaints.csv` | `created_at` | `2025-01-01 00:03:00` | `2025-12-31 21:31:00` | 364.9 | 0 |

> [!NOTE]
> Both transactional tables cover exactly the 365 calendar days of the synthetic operational year 2025.

---

## 4. Categorical Distributions & Numerical Summaries

### Locations Dataset
- **Zones**: 20 distinct zones (`ZONE_01` to `ZONE_20`), balanced across locations (43 to 65 locations per zone).
- **Road Types**: {'Local': 263, 'Collector': 242, 'Residential': 228, 'Arterial': 215, 'Highway': 52}
- **Road Conditions**: {'Fair': 383, 'Poor': 309, 'Good': 230, 'Critical': 78}
- **Pedestrian Activity**: {'Medium': 431, 'Low': 316, 'High': 253}
- **Proximity Indicators**: Near School: 286 (28.6%), Near Hospital: 155 (15.5%)
- **Population Density**: Min: 507.0 /km², Max: 24,983.0 /km², Mean: 12,719.8 /km².
- **Coordinates**: Latitude [16.186032, 16.706502], Longitude [80.248067, 80.818627]. Centered around (16.45° N, 80.50° E).

### Incidents Dataset
- **Incident Types**: {'Streetlight outage': 1726, 'Signal failure': 1699, 'Pothole': 1685, 'Blocked drain': 1651, 'Collision': 1641, 'Flooding': 1598}
- **Severity Breakdown**: {'Low': 3819, 'Medium': 3726, 'High': 1985, 'Critical': 470}
- **Reporting Source**: {'Citizen': 5071, 'Authority': 1913, 'Police': 1533, 'Sensor': 1483}
- **Resolution Status**: Resolved: 7126 (71.3%), Unresolved: 2874 (28.7%)
- **Injuries Summary**: Total records with injuries: 2179 (Max injuries in single incident: 3)
- **Resolution Hours**: Mean: 32.24h, Min: 1.0h, Max: 191.9h

### Public Complaints Dataset
- **Complaint Categories**: {'Road damage': 1361, 'Traffic': 1357, 'Lighting': 1343, 'Waste': 1330, 'Pedestrian safety': 1319, 'Drainage': 1290}
- **Reported Priorities**: {'Normal': 4469, 'Low': 1943, 'High': 1588}
- **Ticket Statuses**: {'Resolved': 3258, 'In progress': 1440, 'Closed': 1304, 'Assigned': 1062, 'Open': 936}
- **Days to Resolution**: Mean: 6.04 days, Min: 0.1 days, Max: 31.3 days

---

## 5. Data Quality Concerns & Unresolved Questions

During deep validation, the following semantic anomalies and operational inconsistencies were identified:

### Inconsistency 1: `resolution_hours` populated on Unresolved Incidents (`resolved == 0`)
- **Count**: 2874 of 2874 unresolved incidents have a non-null `resolution_hours` value.
- **Mean Resolution Hours**: Unresolved: 32.18h vs Resolved: 32.27h.
- **Operational Impact**: In real city infrastructure systems, unresolved incidents do not have a closed resolution duration. If this is an elapsed SLA counter or synthetic generation artifact, feeding `resolution_hours` directly into a model without conditioning on `resolved` will lead to target leakage.

### Inconsistency 2: `days_to_resolution` populated on Active/Open Complaints
- **Count**: 3438 complaints with status `Open`, `In progress`, or `Assigned` have non-null `days_to_resolution`.
- **Distribution**: Status `Open` has mean 6.09 days, `In progress` has mean 5.93 days, and `Assigned` has mean 6.19 days, virtually identical to `Resolved` (6.04 days) and `Closed` (6.01 days).
- **Operational Impact**: `days_to_resolution` cannot be interpreted as actual closed duration for in-flight tickets. Downstream aggregation should distinguish between open aging days versus completed resolution days.

### Inconsistency 3: Independent Synthetic Distribution of Injuries
- Non-collision incident types such as 'Streetlight outage' (384 injuries) and 'Signal failure' (379 injuries) exhibit identical injury rates to 'Collision' (357 injuries).
- Confirms independent synthetic data generator draws; civic prioritization models should capture both direct risk and secondary compound hazards without assuming domain causality rules from real-world telemetry.

---

## 6. Recommendations for Track 3 Prioritization Model

1. **Never mutate source files**: Maintain original CSV datasets as immutable read-only records.
2. **Feature Engineering Strategy**:
   - Compute location-level aggregations (e.g. incident rate, critical severity ratio, complaint volume, injury count, recurring pothole/drainage count).
   - Separate completed resolution metrics from pending backlog metrics.
   - Integrate vulnerability multipliers (near school, near hospital, high pedestrian activity, poor/critical road condition).
3. **Transparent Ranking Index**: Create an interpretable composite index with clear component weights so municipal crews know exactly *why* a location ranks first.

---
**Report Generated By**: CityFix AI Automated Validation Pipeline  
**Dataset Source**: Synthetic Datathon 2026 Collection (`data/`)  