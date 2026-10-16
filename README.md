# CityFix AI — Smart City Civic Prioritization

> **Datathon 2026 — Track 3: Smart City**  
> **Problem Statement**: *Where Should We Fix First?*

CityFix AI is an automated, data-driven civic infrastructure prioritization engine designed to assist city managers, public works departments, and emergency response teams in identifying high-risk, high-urgency civic repair locations.

This repository implements the **Stage 1: Initial Data Inspection & Validation** foundation.

---

## Project Structure

```text
cityfix-ai/
├── data/
│   ├── locations.csv                  # 1,000 synthetic civic locations
│   ├── incidents.csv                  # 10,000 recorded civic incidents (2025)
│   ├── public_complaints.csv          # 8,000 public complaints (2025)
│   └── README.txt                     # Official datathon dataset disclaimer
├── src/
│   ├── __init__.py
│   └── data_pipeline.py              # Reusable loading, schema, relational & quality pipeline
├── scripts/
│   └── validate_data.py              # CLI validation runner & markdown generator
├── tests/
│   ├── __init__.py
│   └── test_data_pipeline.py         # 16 unit & integration tests
├── reports/
│   └── data_validation_report.md     # Generated data validation audit report
├── requirements.txt                   # Project Python dependencies
└── README.md                          # Project documentation and guide
```

---

## Datasets Overview

As stated in `data/README.txt`:
> *Synthetic educational dataset created for DATATHON. Coordinates are simulated and should not be interpreted as real civic reports.*

| Dataset | Dimensions | Primary Key | Description |
| :--- | :---: | :---: | :--- |
| [`data/locations.csv`](file:///data/locations.csv) | 1,000 × 10 | `location_id` | Geographic coordinates, zone, road type, road condition, population density, school/hospital proximity. |
| [`data/incidents.csv`](file:///data/incidents.csv) | 10,000 × 9 | `incident_id` | Incident records across 2025 (Pothole, Flooding, Collision, etc.), severity, injuries, resolution hours. |
| [`data/public_complaints.csv`](file:///data/public_complaints.csv) | 8,000 × 7 | `complaint_id` | Civic 311 complaints across 2025 (Road damage, Lighting, Waste, etc.), priority, status, days to resolution. |

---

## Setup & Installation

### Prerequisites
- Python 3.10+
- `pip`

### 1. Clone / Navigate to Project Directory
```powershell
cd C:\Users\kasse\.gemini\antigravity\scratch\cityfix-ai
```

### 2. Install Dependencies
```powershell
pip install -r requirements.txt
```

---

## Execution Instructions

### Run the Data Validation Script
Execute the validation CLI to inspect schemas, verify foreign key referential integrity, and generate the validation report:

```powershell
python scripts/validate_data.py --strict
```

#### Optional CLI Arguments:
- `--data-dir <path>`: Specify custom data directory (default: `data`).
- `--output-report <path>`: Specify markdown report destination (default: `reports/data_validation_report.md`).
- `--strict`: Return non-zero exit code if validation fails.

### Run the Automated Test Suite
Run the 16 unit and integration tests using Python's standard `unittest`:

```powershell
python -m unittest tests/test_data_pipeline.py -v
```

Or via `pytest` (if installed):
```powershell
pytest -v
```

---

## Validation Summary & Key Findings

1. **Schema & Dimensionality**:
   - Master entity `locations`: exactly 1,000 unique IDs (`L0001` to `L1000`), 0 missing values, 0 duplicate rows.
   - `incidents`: exactly 10,000 unique records (`I000001` to `I010000`), 0 missing values, 0 duplicates.
   - `public_complaints`: exactly 8,000 unique records (`C000001` to `C008000`), 0 missing values, 0 duplicates.

2. **Referential Integrity & Join Cardinality**:
   - **0 unmatched foreign keys**: 100% of incident records and complaint records reference valid `location_id`s in `locations.csv`.
   - Complete coverage: All 1,000 locations have between 2 and 23 incidents (median: 10.0) and between 1 and 17 public complaints (median: 8.0).

3. **Data Quality & Semantic Inconsistencies**:
   - **Unresolved Incident Durations**: 2,874 records in `incidents.csv` have `resolved == 0` (unresolved), yet all 2,874 records contain a non-null `resolution_hours` value (mean: 32.18h), identical to the distribution of resolved incidents (mean: 32.27h).
   - **Active Complaint Durations**: 3,438 tickets in `public_complaints.csv` have open/active statuses (`Open`, `In progress`, `Assigned`), yet have populated `days_to_resolution` (mean: 6.07 days), mirroring closed tickets.
   - **Synthetic Generation Independence**: Injury frequencies across incident types (such as streetlights and collisions) follow independent random distributions.
   - *Action*: In downstream modeling, resolution duration must not be directly used on unresolved items without conditioning on resolution status to avoid data leakage.

See [`reports/data_validation_report.md`](file:///reports/data_validation_report.md) for full statistical breakdown.
