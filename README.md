# CityFix AI — Smart City Civic Prioritization

> **Datathon 2026 — Track 3: Smart City**  
> **Problem Statement**: *Where Should We Fix First?*

CityFix AI is an automated, data-driven civic infrastructure prioritization engine designed to assist city managers, public works departments, and emergency response teams in identifying and triaging high-risk, high-urgency civic repair locations.

This repository implements:
- **Stage 1**: Initial Data Inspection, Validation & Referential Integrity Pipeline
- **Stage 2**: Explainable Location-Priority Engine, Multi-Pillar Scoring, & Advisory Triage
- **Stage 3 (Round 1 Prototype)**: Interactive Municipal Command Center Web Application & REST API

---

## Project Structure

```text
cityfix-ai/
├── data/
│   ├── locations.csv                  # 1,000 synthetic civic locations
│   ├── incidents.csv                  # 10,000 recorded civic incidents (2025)
│   ├── public_complaints.csv          # 8,000 public complaints (2025)
│   ├── dashboard_data.json            # Pre-aggregated standalone dataset for instant client loading
│   └── README.txt                     # Official datathon dataset disclaimer
├── src/
│   ├── __init__.py
│   ├── data_pipeline.py              # Stage 1: Dataset loading (read-only), schemas, relationships, quality
│   └── priority_engine.py            # Stage 2: Location aggregation, 4-pillar scoring, explanations, ranking
├── scripts/
│   ├── validate_data.py              # Stage 1 CLI: Data validation runner & markdown generator
│   ├── generate_priority_report.py   # Stage 2 CLI: Location priority report & summary generator
│   └── export_dashboard_data.py      # Stage 3 CLI: Pre-aggregates dashboard JSON payload
├── tests/
│   ├── __init__.py
│   ├── test_data_pipeline.py         # 16 unit & integration tests for Stage 1
│   ├── test_priority_engine.py       # 16 unit & integration tests for Stage 2
│   └── test_app_integration.py       # 7 integration & API tests for Stage 3 prototype
├── reports/
│   ├── data_validation_report.md     # Stage 1: Data validation audit report
│   ├── location_priority_report.csv  # Stage 2: Full ranking CSV (1,000 locations with metrics & actions)
│   ├── location_priority_summary.md  # Stage 2: Executive priority summary & methodology
│   └── dashboard_data.json           # Precomputed JSON payload for API & dashboard consumption
├── index.html                         # Round 1 Municipal Command Center UI
├── styles.css                         # Modern dark-mode civic dashboard design system
├── app.js                             # Interactive client logic, Leaflet map, filters, AI query engine
├── server.py                          # Zero-dependency Python HTTP server & REST API
├── vercel.json                        # Vercel zero-config deployment manifest
├── requirements.txt                   # Project Python dependencies
└── README.md                          # Comprehensive project documentation
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

## Stage 2: Explainable Location-Priority Engine

The Priority Engine evaluates civic burden by aggregating transactional records at the `location_id` level and computing a normalized, transparent composite score.

### Multi-Pillar Scoring Formulation

The composite Priority Score is computed across four distinct, normalized subscores (each in $[0, 100]$):

$$\text{Priority Score} = w_{\text{incident}} S_{\text{incident}} + w_{\text{backlog}} S_{\text{backlog}} + w_{\text{vulnerability}} S_{\text{vulnerability}} + w_{\text{complaint}} S_{\text{complaint}}$$

| Pillar | Subscore | Default Weight | Core Components | Rationale |
| :--- | :---: | :---: | :--- | :--- |
| **Incident Hazard** | $S_{\text{incident}}$ | **0.35** | $4 \times \text{Crit} + 3 \times \text{High} + 2 \times \text{Med} + 1 \times \text{Low} + 2 \times \text{Injuries} + \text{Freq}$ | Primary direct physical risk verified by field agents, police, sensors, and citizens. |
| **Backlog Burden** | $S_{\text{backlog}}$ | **0.25** | $2.5 \times \text{Unresolved Incidents} + 1.0 \times \text{Open Complaints}$ | Urgent unaddressed civic hazards and unresolved tickets requiring intervention. |
| **Vulnerability Context** | $S_{\text{vulnerability}}$ | **0.25** | Road condition (up to 35) + School (20) + Hospital (20) + Pedestrian (15) + Density (10) | Structural roadway deterioration and proximity to sensitive receptors. |
| **Citizen Demand** | $S_{\text{complaint}}$ | **0.15** | $1.0 \times \text{Total} + 2.0 \times \text{High Priority} + 0.5 \times \text{Normal Priority}$ | Public reporting pressure, citizen dissatisfaction, and repeated 311 calls. |

*Weights are fully configurable via the `WeightConfig` dataclass and reflect policy choices for municipal triage.*

### Priority Tiers & Municipal Posture

- **Critical** ($\text{Score} \ge 50.0$): Immediate inter-departmental field inspection & urgent remediation (~5% of locations).
- **High** ($40.0 \le \text{Score} < 50.0$): Scheduled work orders within active 14-day cycle (~21% of locations).
- **Medium** ($30.0 \le \text{Score} < 40.0$): Planned routine maintenance & preventive cleaning (~40% of locations).
- **Low** ($\text{Score} < 30.0$): Monitoring status / no immediate hazard backlog (~34% of locations).

### Explainability & Advisory Framing
For every location, the engine provides:
1. **Severity Breakdown**: Quantified count of Critical, High, Medium, and Low incidents.
2. **Major Categories**: Top 2 incident types and top 2 complaint categories.
3. **Contributing Factors**: Rule-grounded bullet points detailing why the location ranks high.
4. **Missing Evidence & Limitations**: Contextual notes highlighting synthetic origins and data boundaries.
5. **Suggested Next Action**: Concrete inspection suggestions (e.g., asphalt pavement assessment, stormwater culvert clearing, signal controller diagnostics, or lighting circuit check). *Framed as advisory suggestions for municipal review, not confirmed physical diagnoses.*

---

## Stage 3: Round 1 Municipal Command Center & Interactive Web App

CityFix AI provides a lightweight, responsive municipal command center dashboard built with zero heavy frontend framework dependencies. It operates in dual mode:
1. **Interactive Client**: Runs directly in the browser using standard modern JavaScript, HTML5, CSS custom properties, and Leaflet.js map tiles. It loads instant pre-aggregated JSON payloads or connects to the local REST API.
2. **REST API Server**: Backed by Python's built-in `http.server` via `server.py`, serving real-time filtered queries directly from the prioritization engine with zero external dependencies.

### Command Center Features

1. **Executive KPI Ticker**: High-level city overview presenting Total Locations (1,000), Total Incidents (10,000), Total Complaints (8,000), Average Turnaround (28.4h), and Critical Priority Sites (53 sites).
2. **Category & Severity Distributions**: Interactive breakdown of incidents by severity and type, public complaints by category, and tier distribution (Critical: 5.3%, High: 20.9%, Medium: 40.2%, Low: 33.6%).
3. **Interactive Location Priority Matrix**:
   - Filter by Zone (`North`, `South`, `East`, `West`, `Central`).
   - Filter by Priority Tier (`Critical`, `High`, `Medium`, `Low`).
   - Filter by Primary Issue Category (`Pothole`, `Flooding`, `Traffic Signal`, etc.).
   - Full-text search by Location ID or Road Type.
   - Clickable rows that synchronize with the Evidence Panel and Leaflet Map.
4. **Deep Evidence Panel**:
   - Four-pillar subscore breakdown (Incident Hazard, Backlog, Vulnerability, Complaint Pressure).
   - Concrete contributing factors derived deterministically from the data.
   - Recommended municipal next actions (e.g., pavement survey, drainage clearing).
   - Transparent data limitations and synthetic coordinate disclaimers.
5. **AI City Intelligence Query Console**:
   - Deterministic analytical query processor supporting natural-language requests (e.g., *"Show flooding risks near schools"*, *"Find unresolved potholes in North zone"*, *"Where are collisions near hospitals?"*).
   - Generates grounded executive summaries with matched location jump cards.
6. **Geographic Leaflet Map**:
   - Color-coded priority pins (Red: Critical, Orange: High, Amber: Medium, Slate: Low).
   - Interactive popups with instant "Inspect in Evidence Panel" links.
   - Explicit synthetic disclaimer banner.

### REST API Reference

When `server.py` is running:

| Endpoint | Method | Parameters | Description |
| :--- | :---: | :--- | :--- |
| `/api/stats` | `GET` | — | Returns aggregate citywide counts, severity breakdown, and tier distribution. |
| `/api/locations` | `GET` | `zone`, `tier`, `category`, `limit`, `sort` | Returns filtered, ranked locations with pillar subscores and contributing factors. |
| `/api/locations/<id>` | `GET` | — | Returns granular profile, category tallies, and advisory recommendations for a specific location. |
| `/api/query` | `POST` | `{"query": "..."}` | Evaluates natural-language civic queries and returns matching locations with summary. |

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

### 1. Launch the Interactive Web Application & API Server (Recommended)
Start the local municipal command center:

```powershell
python server.py --port 8000
```
Then open **`http://localhost:8000`** in any web browser.

### 2. Export / Refresh Dashboard Data
To recompute the standalone JSON payload directly from the raw CSVs:

```powershell
python scripts/export_dashboard_data.py
```
Outputs:
- [`reports/dashboard_data.json`](file:///reports/dashboard_data.json)
- [`data/dashboard_data.json`](file:///data/dashboard_data.json)

### 3. Generate Location Priority Reports (Stage 2)
Generate both the detailed CSV ranking and the executive Markdown summary:

```powershell
python scripts/generate_priority_report.py
```

Outputs:
- [`reports/location_priority_report.csv`](file:///reports/location_priority_report.csv) (1,000 rows with all indicators, scores, and explanations)
- [`reports/location_priority_summary.md`](file:///reports/location_priority_summary.md) (Executive triage overview, top 10 locations, and methodology)

### 4. Run the Data Validation Pipeline (Stage 1)
Verify schema compliance, foreign key integrity, and dataset constraints in strict mode:

```powershell
python scripts/validate_data.py --strict
```

Output:
- [`reports/data_validation_report.md`](file:///reports/data_validation_report.md)

### 5. Run the Automated Test Suite
Execute the entire test suite (39 unit, priority, and API integration tests):

```powershell
python -m unittest discover tests -v
```

Or via `pytest`:
```powershell
pytest -v
```

---

## Deployment Guide

### Option A: Local Python Server
Run `python server.py --port 8000` and access `http://localhost:8000`. Works on any operating system with Python 3.10+.

### Option B: Deploy to Vercel
The repository includes a ready-to-deploy [`vercel.json`](file:///vercel.json) manifest.
1. Push this repository to GitHub (`https://github.com/Manas-in1234/datathon`).
2. Log in to [Vercel](https://vercel.com) and click **"Add New Project"**.
3. Import the `datathon` repository.
4. Keep the default settings (Root directory: `./`) and click **Deploy**.
5. Vercel serves `index.html`, `styles.css`, `app.js`, and `data/dashboard_data.json` globally on a high-speed CDN.

### Option C: GitHub Pages
1. Go to repository **Settings > Pages**.
2. Select **Source**: Deploy from a branch.
3. Select Branch: `main`, Folder: `/ (root)`.
4. Click **Save**. The dashboard will be live at `https://manas-in1234.github.io/datathon/`.

---

## Validation & Test Results

- **Data Validation (`validate_data.py --strict`)**: `PASSED`
  - 1,000 locations, 10,000 incidents, 8,000 complaints.
  - 100% referential integrity along `location_id` (0 dangling references).
- **Test Suite (`unittest discover tests`)**: **39 / 39 tests PASSED**
  - **Stage 1 Data Pipeline** (16 tests): Loading, missing files, schemas, primary keys, foreign keys, timestamps, anomaly logging.
  - **Stage 2 Priority Engine** (16 tests): Aggregation, score reproducibility, normalization $[0, 100]$, priority levels, ranking order, top-N, zone filtering, incident category filtering, explanations, source data immutability.
  - **Stage 3 Application & API Integration** (7 tests): Dashboard data integrity, summary statistics consistency, top location verification, REST API endpoints (`/`, `/api/stats`, `/api/locations`, `/api/locations/<id>`, `/api/query`).

---

## Known Limitations & Assumptions

1. **Synthetic Educational Dataset**: Per `data/README.txt`, all coordinates, timestamps, and civic records are simulated for the educational Datathon and must not be used for actual public safety decisions.
2. **Unresolved Durations**: In accordance with Stage 1 validation findings, recorded resolution hours for unresolved items were excluded from scoring to prevent target leakage.
3. **Complaints vs. Incidents**: Citizen complaints represent public reporting sentiment; they are not assumed to have 1:1 correspondence with distinct physical structural failures.
4. **Heuristic Weights**: The scoring weights represent configurable municipal policy choices and are not claimed to be an absolute ground-truth optimum.
5. **Advisory Framing**: Suggested next actions are algorithmic recommendations for municipal crew triage and survey, not confirmed engineering diagnoses.
