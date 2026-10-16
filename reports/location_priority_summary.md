# CityFix AI — Location Priority Engine Summary Report

**Track**: Datathon 2026 — Track 3: Smart City  
**Problem Statement**: *Where Should We Fix First?*  
**Stage**: Stage 2 — Explainable Priority Engine & Municipal Triage  

---

## 1. Executive Summary

The CityFix AI Priority Engine evaluated **1,000** civic locations by synthesizing historical physical incidents, citizen 311 complaints, and infrastructural context. The scoring methodology is deterministic, transparent, and multi-pillared.

### Priority Level Distribution

| Priority Level | Score Range | Location Count | % of City Locations | Recommended Municipal Posture |
| :--- | :---: | :---: | :---: | :--- |
| **Critical** | ≥ 50.0 | **53** | 5.3% | Immediate inter-departmental field inspection & urgent remediation |
| **High** | 40.0 – 50.0 | **215** | 21.5% | Scheduled work orders within active 14-day cycle |
| **Medium** | 30.0 – 40.0 | **404** | 40.4% | Planned routine maintenance & preventive cleaning |
| **Low** | < 30.0 | **328** | 32.8% | Monitoring status / no immediate hazard backlog |

---

## 2. Top 10 Highest-Priority Locations

The table below details the top 10 locations requiring municipal prioritization, along with their key driving factors:

| Rank | Location ID | Zone | Priority Score | Level | Road Cond. | Incidents (Crit/High) | Complaints | Injuries | Backlog | Primary Suggested Action |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| 1 | `L0965` | ZONE_20 | **66.05** | `Critical` | Critical | 19 (1/2) | 15 | 12 | 2 | Priority structural roadway inspection recommended due to Critical pavement degradation; deploy traffic engineering technician for signal controller diagnostics. |
| 2 | `L0729` | ZONE_12 | **65.46** | `Critical` | Poor | 17 (3/4) | 9 | 6 | 6 | Targeted review suggested: Schedule stormwater drainage inspection and culvert clearing. |
| 3 | `L0362` | ZONE_05 | **63.93** | `Critical` | Poor | 23 (4/4) | 9 | 7 | 6 | Targeted review suggested: Schedule stormwater drainage inspection and culvert clearing. |
| 4 | `L0688` | ZONE_09 | **63.78** | `Critical` | Critical | 19 (0/7) | 6 | 3 | 7 | Priority structural roadway inspection recommended due to Critical pavement degradation; schedule stormwater drainage inspection and culvert clearing. |
| 5 | `L0624` | ZONE_13 | **63.17** | `Critical` | Good | 17 (0/4) | 11 | 5 | 13 | Targeted review suggested: Conduct pedestrian crossing safety review and traffic calming assessment. |
| 6 | `L0494` | ZONE_14 | **62.00** | `Critical` | Critical | 14 (0/4) | 14 | 7 | 5 | Priority structural roadway inspection recommended due to Critical pavement degradation; schedule stormwater drainage inspection and culvert clearing. |
| 7 | `L0642` | ZONE_02 | **61.82** | `Critical` | Fair | 11 (2/2) | 14 | 5 | 6 | Targeted review suggested: Schedule stormwater drainage inspection and culvert clearing. |
| 8 | `L0556` | ZONE_02 | **60.02** | `Critical` | Critical | 14 (2/3) | 9 | 7 | 5 | Priority structural roadway inspection recommended due to Critical pavement degradation; dispatch road-maintenance team for asphalt pavement and surface evaluation. |
| 9 | `L0802` | ZONE_14 | **59.84** | `Critical` | Good | 19 (0/4) | 10 | 4 | 3 | Targeted review suggested: Schedule stormwater drainage inspection and culvert clearing. |
| 10 | `L0675` | ZONE_19 | **58.97** | `Critical` | Poor | 16 (0/3) | 16 | 4 | 5 | Targeted review suggested: Conduct pedestrian crossing safety review and traffic calming assessment. |

---

## 3. Most Common Civic Issue Categories

### Incident Types (Verified Disruptions)
| Incident Category | Total Recorded Incidents | % of Incident Volume |
| :--- | :---: | :---: |
| Streetlight outage | 1,726 | 17.3% |
| Signal failure | 1,699 | 17.0% |
| Pothole | 1,685 | 16.9% |
| Blocked drain | 1,651 | 16.5% |
| Collision | 1,641 | 16.4% |
| Flooding | 1,598 | 16.0% |

### Citizen Complaints (Public 311 Demands)
| Complaint Category | Total Recorded Complaints | % of Complaint Volume |
| :--- | :---: | :---: |
| Road damage | 1,361 | 17.0% |
| Traffic | 1,357 | 17.0% |
| Lighting | 1,343 | 16.8% |
| Waste | 1,330 | 16.6% |
| Pedestrian safety | 1,319 | 16.5% |
| Drainage | 1,290 | 16.1% |

---

## 4. Scoring Methodology & Mathematical Formulation

The CityFix AI Priority Engine synthesizes four normalized subscores into a deterministic 0–100 index:

$$\text{Priority Score} = w_{\text{incident}} S_{\text{incident}} + w_{\text{backlog}} S_{\text{backlog}} + w_{\text{vulnerability}} S_{\text{vulnerability}} + w_{\text{complaint}} S_{\text{complaint}}$$

### Component Definitions & Configured Weights:
1. **Incident Hazard Subscore ($S_{\text{incident}}$, Weight: 0.35)**:
   - Computes weighted incident severity: $4 \times \text{Critical} + 3 \times \text{High} + 2 \times \text{Medium} + 1 \times \text{Low} + 2 \times \text{Injuries} + \text{Frequency}$.
   - Normalized across the city distribution to $[0, 100]$.
2. **Backlog & Unresolved Burden ($S_{\text{backlog}}$, Weight: 0.25)**:
   - Quantifies pending physical hazard exposure: $2.5 \times \text{Unresolved Incidents} + 1.0 \times \text{Open Complaints}$.
   - Normalized to $[0, 100]$.
3. **Vulnerability & Exposure Subscore ($S_{\text{vulnerability}}$, Weight: 0.25)**:
   - Evaluates surrounding receptors and structural health:
     - Road condition: Critical (35 pts), Poor (25 pts), Fair (12 pts), Good (0 pts).
     - School proximity: +20 pts.
     - Hospital proximity: +20 pts.
     - Pedestrian density: High (15 pts), Medium (8 pts), Low (0 pts).
     - Population density: Scaled up to 10 pts.
4. **Citizen Demand Subscore ($S_{\text{complaint}}$, Weight: 0.15)**:
   - Incorporates community reporting pressure: $1.0 \times \text{Total Complaints} + 2.0 \times \text{High Priority} + 0.5 \times \text{Normal Priority}$.
   - Normalized to $[0, 100]$.

---

## 5. Limitations & Boundary Assumptions

> [!IMPORTANT]
> 1. **Synthetic Educational Data**: Coordinates and civic records are simulated for the Datathon 2026 educational challenge per `data/README.txt` and must not be used for real municipal dispatch.
> 2. **Unresolved Durations**: In accordance with Stage 1 validation findings, recorded resolution hours for unresolved items were excluded from scoring to prevent target leakage.
> 3. **Complaints vs. Incidents**: Citizen complaints represent public reporting sentiment; they are not assumed to have 1:1 correspondence with distinct physical structural failures.
> 4. **Heuristic Weights**: The scoring weights represent configurable municipal policy choices and are not claimed to be an absolute ground-truth optimum.
> 5. **Advisory Framing**: Suggested next actions are algorithmic recommendations for municipal crew triage and survey, not confirmed engineering diagnoses.

---
**Report Generated By**: CityFix AI Priority Engine (Stage 2)  
**Data Source**: `data/locations.csv`, `data/incidents.csv`, `data/public_complaints.csv`  