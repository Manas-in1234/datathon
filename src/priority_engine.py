"""
CityFix AI — Explainable Location-Priority Engine
=================================================
Datathon 2026 — Track 3: Smart City (Where Should We Fix First?)

This module aggregates multi-source civic datasets (locations, incidents, complaints),
computes normalized, transparent priority scores across four distinct pillars,
and produces explainable, actionable recommendations for municipal intervention.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd

from src.data_pipeline import load_all_datasets


@dataclass
class WeightConfig:
    """
    Configurable weights and thresholds for transparent priority scoring.

    Pillar Weights:
    - incident_weight (0.35): Primary physical hazard weight (verified real-world disruptions).
    - backlog_weight (0.25): Urgency of pending, unaddressed civic issues (unresolved burden).
    - vulnerability_weight (0.25): Infrastructure condition and proximity to vulnerable receptors (schools/hospitals).
    - complaint_weight (0.15): Citizen reporting frequency and dissatisfaction pressure.

    Note:
    Weights are configurable assumptions intended for municipal decision support
    and should not be claimed as objectively optimal.
    """

    # Pillar composite weights (must sum to 1.0)
    incident_weight: float = 0.35
    backlog_weight: float = 0.25
    vulnerability_weight: float = 0.25
    complaint_weight: float = 0.15

    # Incident severity weights
    critical_severity_weight: float = 4.0
    high_severity_weight: float = 3.0
    medium_severity_weight: float = 2.0
    low_severity_weight: float = 1.0
    injury_weight: float = 2.0

    # Backlog burden weights
    unresolved_incident_weight: float = 2.5
    open_complaint_weight: float = 1.0

    # Complaint priority weights
    high_priority_complaint_weight: float = 2.0
    normal_priority_complaint_weight: float = 0.5
    low_priority_complaint_weight: float = 0.0

    # Vulnerability points (max sum = 100)
    road_condition_critical_pts: float = 35.0
    road_condition_poor_pts: float = 25.0
    road_condition_fair_pts: float = 12.0
    road_condition_good_pts: float = 0.0

    school_proximity_pts: float = 20.0
    hospital_proximity_pts: float = 20.0
    pedestrian_high_pts: float = 15.0
    pedestrian_medium_pts: float = 8.0
    pedestrian_low_pts: float = 0.0
    max_population_density_pts: float = 10.0
    population_density_ceiling: float = 25000.0

    # Priority level thresholds (Score out of 100)
    critical_threshold: float = 50.0
    high_threshold: float = 40.0
    medium_threshold: float = 30.0

    def validate(self) -> None:
        """Validate that weights are non-negative and properly proportioned."""
        total_weight = (
            self.incident_weight
            + self.backlog_weight
            + self.vulnerability_weight
            + self.complaint_weight
        )
        if not np.isclose(total_weight, 1.0, atol=1e-3):
            raise ValueError(
                f"Pillar weights must sum to 1.0. Current sum: {total_weight:.4f}"
            )
        for name, val in [
            ("incident_weight", self.incident_weight),
            ("backlog_weight", self.backlog_weight),
            ("vulnerability_weight", self.vulnerability_weight),
            ("complaint_weight", self.complaint_weight),
        ]:
            if val < 0.0:
                raise ValueError(f"Weight '{name}' cannot be negative: {val}")


INCIDENT_CATEGORIES = [
    "Streetlight outage",
    "Signal failure",
    "Pothole",
    "Blocked drain",
    "Collision",
    "Flooding",
]

COMPLAINT_CATEGORIES = [
    "Road damage",
    "Traffic",
    "Lighting",
    "Waste",
    "Pedestrian safety",
    "Drainage",
]


def aggregate_location_data(
    locations_df: pd.DataFrame,
    incidents_df: pd.DataFrame,
    complaints_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Aggregate incident and complaint records by location_id and merge with location context.

    Preserves the distinction between verified incident records and citizen complaints.
    Does not assume every complaint represents a separate physical incident.

    Parameters
    ----------
    locations_df : pd.DataFrame
        Master location table.
    incidents_df : pd.DataFrame
        Operational incident table.
    complaints_df : pd.DataFrame
        Public complaint table.

    Returns
    -------
    pd.DataFrame
        Aggregated location metrics.
    """
    # Validate required columns
    required_loc = [
        "location_id",
        "zone",
        "road_type",
        "road_condition",
        "population_density_per_km2",
        "near_school",
        "near_hospital",
        "pedestrian_activity",
        "latitude",
        "longitude",
    ]
    required_inc = [
        "incident_id",
        "location_id",
        "incident_type",
        "severity",
        "injuries",
        "resolved",
    ]
    required_comp = [
        "complaint_id",
        "location_id",
        "category",
        "priority_reported",
        "status",
    ]

    for col in required_loc:
        if col not in locations_df.columns:
            raise KeyError(f"Missing required column in locations: '{col}'")
    for col in required_inc:
        if col not in incidents_df.columns:
            raise KeyError(f"Missing required column in incidents: '{col}'")
    for col in required_comp:
        if col not in complaints_df.columns:
            raise KeyError(f"Missing required column in complaints: '{col}'")

    if locations_df.empty:
        raise ValueError("Locations dataset cannot be empty.")

    # 1. Base copy to preserve source immutability
    df_loc = locations_df[required_loc].copy()

    # 2. Incident Aggregations
    if incidents_df.empty:
        inc_summary = pd.DataFrame(
            {
                "location_id": df_loc["location_id"],
                "incident_count": 0,
                "critical_incidents": 0,
                "high_incidents": 0,
                "medium_incidents": 0,
                "low_incidents": 0,
                "unresolved_incidents": 0,
                "resolved_incidents": 0,
                "total_injuries": 0,
            }
        )
        inc_piv = pd.DataFrame(
            {"location_id": df_loc["location_id"]}
            | {f"inc_{c.lower().replace(' ', '_')}": 0 for c in INCIDENT_CATEGORIES}
        )
    else:
        inc_summary = (
            incidents_df.groupby("location_id")
            .agg(
                incident_count=("incident_id", "count"),
                critical_incidents=("severity", lambda s: (s == "Critical").sum()),
                high_incidents=("severity", lambda s: (s == "High").sum()),
                medium_incidents=("severity", lambda s: (s == "Medium").sum()),
                low_incidents=("severity", lambda s: (s == "Low").sum()),
                unresolved_incidents=("resolved", lambda r: (r == 0).sum()),
                resolved_incidents=("resolved", lambda r: (r == 1).sum()),
                total_injuries=("injuries", "sum"),
            )
            .reset_index()
        )

        inc_piv = incidents_df.pivot_table(
            index="location_id",
            columns="incident_type",
            values="incident_id",
            aggfunc="count",
            fill_value=0,
        )
        # Standardize column naming
        inc_piv.columns = [
            f"inc_{str(c).lower().replace(' ', '_')}" for c in inc_piv.columns
        ]
        inc_piv = inc_piv.reset_index()

        # Ensure all expected incident categories are present
        for cat in INCIDENT_CATEGORIES:
            col_name = f"inc_{cat.lower().replace(' ', '_')}"
            if col_name not in inc_piv.columns:
                inc_piv[col_name] = 0

    # 3. Complaint Aggregations
    if complaints_df.empty:
        comp_summary = pd.DataFrame(
            {
                "location_id": df_loc["location_id"],
                "complaint_count": 0,
                "high_priority_complaints": 0,
                "normal_priority_complaints": 0,
                "low_priority_complaints": 0,
                "open_complaints": 0,
                "closed_complaints": 0,
            }
        )
        comp_piv = pd.DataFrame(
            {"location_id": df_loc["location_id"]}
            | {f"comp_{c.lower().replace(' ', '_')}": 0 for c in COMPLAINT_CATEGORIES}
        )
    else:
        comp_summary = (
            complaints_df.groupby("location_id")
            .agg(
                complaint_count=("complaint_id", "count"),
                high_priority_complaints=(
                    "priority_reported",
                    lambda p: (p == "High").sum(),
                ),
                normal_priority_complaints=(
                    "priority_reported",
                    lambda p: (p == "Normal").sum(),
                ),
                low_priority_complaints=(
                    "priority_reported",
                    lambda p: (p == "Low").sum(),
                ),
                open_complaints=(
                    "status",
                    lambda s: s.isin(["Open", "In progress", "Assigned"]).sum(),
                ),
                closed_complaints=(
                    "status",
                    lambda s: s.isin(["Resolved", "Closed"]).sum(),
                ),
            )
            .reset_index()
        )

        comp_piv = complaints_df.pivot_table(
            index="location_id",
            columns="category",
            values="complaint_id",
            aggfunc="count",
            fill_value=0,
        )
        comp_piv.columns = [
            f"comp_{str(c).lower().replace(' ', '_')}" for c in comp_piv.columns
        ]
        comp_piv = comp_piv.reset_index()

        # Ensure all expected complaint categories are present
        for cat in COMPLAINT_CATEGORIES:
            col_name = f"comp_{cat.lower().replace(' ', '_')}"
            if col_name not in comp_piv.columns:
                comp_piv[col_name] = 0

    # 4. Merge all components onto master locations
    merged = df_loc.merge(inc_summary, on="location_id", how="left")
    merged = merged.merge(inc_piv, on="location_id", how="left")
    merged = merged.merge(comp_summary, on="location_id", how="left")
    merged = merged.merge(comp_piv, on="location_id", how="left")

    # Fill NaN for any locations that had zero records
    metric_cols = [
        "incident_count",
        "critical_incidents",
        "high_incidents",
        "medium_incidents",
        "low_incidents",
        "unresolved_incidents",
        "resolved_incidents",
        "total_injuries",
        "complaint_count",
        "high_priority_complaints",
        "normal_priority_complaints",
        "low_priority_complaints",
        "open_complaints",
        "closed_complaints",
    ]
    for col in metric_cols:
        merged[col] = merged[col].fillna(0).astype(int)

    for cat in INCIDENT_CATEGORIES:
        col = f"inc_{cat.lower().replace(' ', '_')}"
        merged[col] = merged[col].fillna(0).astype(int)

    for cat in COMPLAINT_CATEGORIES:
        col = f"comp_{cat.lower().replace(' ', '_')}"
        merged[col] = merged[col].fillna(0).astype(int)

    return merged


def _normalize_series(series: pd.Series) -> pd.Series:
    """Normalize numeric series to [0.0, 100.0] range safely."""
    s_min = series.min()
    s_max = series.max()
    if np.isclose(s_max, s_min) or pd.isna(s_max) or pd.isna(s_min):
        return pd.Series(0.0, index=series.index)
    return (100.0 * (series - s_min) / (s_max - s_min)).clip(0.0, 100.0)


def calculate_priority_scores(
    aggregated_df: pd.DataFrame,
    config: Optional[WeightConfig] = None,
) -> pd.DataFrame:
    """
    Compute multi-pillar normalized priority scores and assign priority levels.

    Four Subscores (each normalized to 0-100):
    1. Incident Hazard & Severity (S_incident)
    2. Backlog & Unresolved Burden (S_backlog)
    3. Vulnerability & Infrastructure Context (S_vulnerability)
    4. Citizen Demand & Complaint Density (S_complaint)

    Parameters
    ----------
    aggregated_df : pd.DataFrame
        Output from aggregate_location_data.
    config : Optional[WeightConfig]
        Configurable weights and thresholds.

    Returns
    -------
    pd.DataFrame
        DataFrame with subscores, composite priority_score, and priority_level.
    """
    if config is None:
        config = WeightConfig()
    config.validate()

    df = aggregated_df.copy()
    if df.empty:
        for col in [
            "subscore_incident",
            "subscore_backlog",
            "subscore_vulnerability",
            "subscore_complaint",
            "priority_score",
            "priority_level",
        ]:
            df[col] = []
        return df

    # Pillar 1: Incident Hazard & Severity
    raw_hazard = (
        df["critical_incidents"] * config.critical_severity_weight
        + df["high_incidents"] * config.high_severity_weight
        + df["medium_incidents"] * config.medium_severity_weight
        + df["low_incidents"] * config.low_severity_weight
        + df["total_injuries"] * config.injury_weight
        + df["incident_count"] * 1.0
    )
    df["subscore_incident"] = _normalize_series(raw_hazard).round(2)

    # Pillar 2: Backlog & Unresolved Burden
    raw_backlog = (
        df["unresolved_incidents"] * config.unresolved_incident_weight
        + df["open_complaints"] * config.open_complaint_weight
    )
    df["subscore_backlog"] = _normalize_series(raw_backlog).round(2)

    # Pillar 3: Citizen Demand & Complaints
    raw_complaints = (
        df["complaint_count"] * 1.0
        + df["high_priority_complaints"] * config.high_priority_complaint_weight
        + df["normal_priority_complaints"] * config.normal_priority_complaint_weight
        + df["low_priority_complaints"] * config.low_priority_complaint_weight
    )
    df["subscore_complaint"] = _normalize_series(raw_complaints).round(2)

    # Pillar 4: Vulnerability & Infrastructure Context
    road_map = {
        "Critical": config.road_condition_critical_pts,
        "Poor": config.road_condition_poor_pts,
        "Fair": config.road_condition_fair_pts,
        "Good": config.road_condition_good_pts,
    }
    road_pts = df["road_condition"].map(road_map).fillna(0.0)
    school_pts = df["near_school"] * config.school_proximity_pts
    hospital_pts = df["near_hospital"] * config.hospital_proximity_pts

    ped_map = {
        "High": config.pedestrian_high_pts,
        "Medium": config.pedestrian_medium_pts,
        "Low": config.pedestrian_low_pts,
    }
    ped_pts = df["pedestrian_activity"].map(ped_map).fillna(0.0)

    pop_pts = (
        (df["population_density_per_km2"] / config.population_density_ceiling).clip(
            0.0, 1.0
        )
        * config.max_population_density_pts
    )

    raw_vulnerability = road_pts + school_pts + hospital_pts + ped_pts + pop_pts
    df["subscore_vulnerability"] = raw_vulnerability.clip(0.0, 100.0).round(2)

    # Composite Priority Score
    composite = (
        df["subscore_incident"] * config.incident_weight
        + df["subscore_backlog"] * config.backlog_weight
        + df["subscore_vulnerability"] * config.vulnerability_weight
        + df["subscore_complaint"] * config.complaint_weight
    )
    df["priority_score"] = composite.round(2)

    # Assign Priority Level
    def _assign_level(score: float) -> str:
        if score >= config.critical_threshold:
            return "Critical"
        if score >= config.high_threshold:
            return "High"
        if score >= config.medium_threshold:
            return "Medium"
        return "Low"

    df["priority_level"] = df["priority_score"].apply(_assign_level)
    return df


def generate_location_explanation(row: Union[pd.Series, Dict[str, Any]]) -> Dict[str, Any]:
    """
    Generate transparent, data-grounded explanations and advisory actions for a location.

    Parameters
    ----------
    row : Union[pd.Series, Dict[str, Any]]
        A row containing aggregated metrics and scores for one location.

    Returns
    -------
    Dict[str, Any]
        Dictionary of severity breakdown, major categories, contributing factors,
        limitations, and suggested next actions.
    """
    # 1. Severity breakdown
    severity_breakdown = {
        "Critical": int(row.get("critical_incidents", 0)),
        "High": int(row.get("high_incidents", 0)),
        "Medium": int(row.get("medium_incidents", 0)),
        "Low": int(row.get("low_incidents", 0)),
    }

    # 2. Major incident categories
    inc_cat_counts = []
    for cat in INCIDENT_CATEGORIES:
        col = f"inc_{cat.lower().replace(' ', '_')}"
        cnt = int(row.get(col, 0))
        if cnt > 0:
            inc_cat_counts.append((cat, cnt))
    inc_cat_counts.sort(key=lambda x: x[1], reverse=True)
    major_incident_categories = [
        f"{cat} ({cnt})" for cat, cnt in inc_cat_counts[:2]
    ]

    # 3. Major complaint categories
    comp_cat_counts = []
    for cat in COMPLAINT_CATEGORIES:
        col = f"comp_{cat.lower().replace(' ', '_')}"
        cnt = int(row.get(col, 0))
        if cnt > 0:
            comp_cat_counts.append((cat, cnt))
    comp_cat_counts.sort(key=lambda x: x[1], reverse=True)
    major_complaint_categories = [
        f"{cat} ({cnt})" for cat, cnt in comp_cat_counts[:2]
    ]

    # 4. Contributing factors
    factors: List[str] = []
    road_cond = str(row.get("road_condition", ""))
    if road_cond == "Critical":
        factors.append("Critical structural road degradation recorded")
    elif road_cond == "Poor":
        factors.append("Poor road surface condition observed")

    crit_inc = int(row.get("critical_incidents", 0))
    high_inc = int(row.get("high_incidents", 0))
    if crit_inc > 0:
        factors.append(f"{crit_inc} critical-severity incident(s) recorded")
    elif high_inc >= 3:
        factors.append(f"Elevated high-severity incidents ({high_inc})")

    injuries = int(row.get("total_injuries", 0))
    if injuries >= 3:
        factors.append(f"Multiple recorded personal injuries ({injuries} total)")

    unresolved = int(row.get("unresolved_incidents", 0))
    if unresolved >= 3:
        factors.append(f"Persistent unresolved incident backlog ({unresolved} active)")

    near_school = int(row.get("near_school", 0))
    near_hosp = int(row.get("near_hospital", 0))
    ped_act = str(row.get("pedestrian_activity", ""))

    if near_school == 1 and ped_act == "High":
        factors.append("School zone with high pedestrian exposure")
    elif near_school == 1:
        factors.append("Proximity to active school zone")

    if near_hosp == 1:
        factors.append("Adjacent to hospital / emergency response corridor")

    complaints = int(row.get("complaint_count", 0))
    if complaints >= 10:
        factors.append(f"High citizen complaint volume ({complaints} total)")

    potholes = int(row.get("inc_pothole", 0))
    road_dmg = int(row.get("comp_road_damage", 0))
    if (potholes + road_dmg) >= 4:
        factors.append(f"Recurring roadway damage ({potholes} potholes, {road_dmg} complaints)")

    drainage_issues = (
        int(row.get("inc_blocked_drain", 0))
        + int(row.get("inc_flooding", 0))
        + int(row.get("comp_drainage", 0))
    )
    if drainage_issues >= 4:
        factors.append(
            f"Persistent drainage bottleneck ({drainage_issues} water/drainage issues)"
        )

    signal_issues = int(row.get("inc_signal_failure", 0)) + int(row.get("comp_traffic", 0))
    if signal_issues >= 4:
        factors.append(f"Traffic flow & signal disruptions ({signal_issues} issues)")

    lighting_issues = int(row.get("inc_streetlight_outage", 0)) + int(row.get("comp_lighting", 0))
    if lighting_issues >= 4:
        factors.append(f"Illumination deficit ({lighting_issues} outage/lighting issues)")

    if not factors:
        factors.append("Standard routine civic monitoring level")

    # 5. Missing Evidence or Limitations
    limitations: List[str] = [
        "Synthetic educational dataset (simulated civic metrics and coordinates).",
        "Unresolved durations do not represent verified closed turnaround times.",
        "Citizen complaints are subjective reports and not verified physical duplicates of incident logs.",
    ]

    # 6. Suggested Next Action (Framed as advisory suggestions for municipal review)
    # Ground action on dominant issue category
    total_road = potholes + road_dmg
    total_drainage = drainage_issues
    total_traffic = signal_issues
    total_lighting = lighting_issues
    total_ped_safety = int(row.get("inc_collision", 0)) + int(row.get("comp_pedestrian_safety", 0))

    action_candidates = [
        ("pavement", total_road, "Dispatch road-maintenance team for asphalt pavement and surface evaluation."),
        ("drainage", total_drainage, "Schedule stormwater drainage inspection and culvert clearing."),
        ("signal", total_traffic, "Deploy traffic engineering technician for signal controller diagnostics."),
        ("lighting", total_lighting, "Dispatch municipal electrical crew to inspect luminaires and lighting circuits."),
        ("safety", total_ped_safety, "Conduct pedestrian crossing safety review and traffic calming assessment."),
    ]
    action_candidates.sort(key=lambda x: x[1], reverse=True)

    if road_cond == "Critical":
        suggested_action = (
            "Priority structural roadway inspection recommended due to Critical pavement degradation; "
            + action_candidates[0][2].lower()
        )
    elif action_candidates[0][1] >= 3:
        suggested_action = (
            f"Targeted review suggested: {action_candidates[0][2]} "
            "(Advisory suggestion based on historical frequency; subject to field verification)."
        )
    else:
        suggested_action = (
            "Conduct routine multi-departmental field inspection covering road condition, drainage, and lighting. "
            "(Advisory suggestion for municipal planning)."
        )

    return {
        "location_id": str(row.get("location_id")),
        "zone": str(row.get("zone")),
        "priority_score": float(row.get("priority_score", 0.0)),
        "priority_level": str(row.get("priority_level", "Low")),
        "incident_count": int(row.get("incident_count", 0)),
        "complaint_count": int(row.get("complaint_count", 0)),
        "severity_breakdown": severity_breakdown,
        "unresolved_incident_count": unresolved,
        "major_incident_categories": major_incident_categories,
        "major_complaint_categories": major_complaint_categories,
        "contributing_factors": factors,
        "missing_evidence_or_limitations": limitations,
        "suggested_next_action": suggested_action,
    }


def enrich_with_explanations(scored_df: pd.DataFrame) -> pd.DataFrame:
    """
    Enrich scored DataFrame with structured explanations, factors, and advisory actions.

    Parameters
    ----------
    scored_df : pd.DataFrame
        DataFrame with scores and aggregated metrics.

    Returns
    -------
    pd.DataFrame
        Enriched DataFrame with explanation columns.
    """
    if scored_df.empty:
        df = scored_df.copy()
        df["severity_breakdown"] = []
        df["major_incident_categories"] = []
        df["major_complaint_categories"] = []
        df["contributing_factors"] = []
        df["missing_evidence_or_limitations"] = []
        df["suggested_next_action"] = []
        return df

    explanations = [
        generate_location_explanation(row) for _, row in scored_df.iterrows()
    ]

    df = scored_df.copy()
    df["severity_breakdown"] = [e["severity_breakdown"] for e in explanations]
    df["major_incident_categories"] = [
        "; ".join(e["major_incident_categories"]) for e in explanations
    ]
    df["major_complaint_categories"] = [
        "; ".join(e["major_complaint_categories"]) for e in explanations
    ]
    df["contributing_factors"] = [
        "; ".join(e["contributing_factors"]) for e in explanations
    ]
    df["missing_evidence_or_limitations"] = [
        "; ".join(e["missing_evidence_or_limitations"]) for e in explanations
    ]
    df["suggested_next_action"] = [e["suggested_next_action"] for e in explanations]

    return df


def rank_locations(
    df: pd.DataFrame,
    top_n: Optional[int] = None,
    zone: Optional[str] = None,
    incident_category: Optional[str] = None,
    priority_level: Optional[str] = None,
) -> pd.DataFrame:
    """
    Filter and rank locations deterministically by priority score.

    Tie-breaking order:
    1. priority_score (descending)
    2. critical_incidents (descending)
    3. unresolved_incidents (descending)
    4. incident_count (descending)
    5. location_id (ascending)

    Parameters
    ----------
    df : pd.DataFrame
        Scored or enriched locations DataFrame.
    top_n : Optional[int]
        Limit output to top N records.
    zone : Optional[str]
        Filter by specific zone (e.g. 'ZONE_01').
    incident_category : Optional[str]
        Filter to locations having at least one incident in this category.
    priority_level : Optional[str]
        Filter by 'Critical', 'High', 'Medium', or 'Low'.

    Returns
    -------
    pd.DataFrame
        Sorted, filtered DataFrame.
    """
    ranked = df.copy()

    # Filtering
    if zone is not None:
        ranked = ranked[ranked["zone"] == zone]

    if priority_level is not None:
        ranked = ranked[ranked["priority_level"] == priority_level]

    if incident_category is not None:
        col = f"inc_{incident_category.lower().replace(' ', '_')}"
        if col in ranked.columns:
            ranked = ranked[ranked[col] > 0]
        else:
            raise ValueError(f"Unknown incident category for filtering: '{incident_category}'")

    # Deterministic sorting
    sort_cols = [
        "priority_score",
        "critical_incidents",
        "unresolved_incidents",
        "incident_count",
        "location_id",
    ]
    ascending_order = [False, False, False, False, True]

    # Handle missing sort columns gracefully if custom df passed
    active_sort_cols = [c for c in sort_cols if c in ranked.columns]
    active_asc = [ascending_order[sort_cols.index(c)] for c in active_sort_cols]

    if active_sort_cols:
        ranked = ranked.sort_values(by=active_sort_cols, ascending=active_asc)

    if top_n is not None and top_n > 0:
        ranked = ranked.head(top_n)

    return ranked.reset_index(drop=True)


def build_priority_pipeline(
    data_dir: Path | str,
    config: Optional[WeightConfig] = None,
) -> pd.DataFrame:
    """
    Run the end-to-end Priority Engine pipeline.

    1. Loads read-only datasets via data_pipeline.
    2. Aggregates data by location_id.
    3. Calculates normalized subscores and composite priority score.
    4. Enriches with transparent explanations and suggested next actions.
    5. Ranks deterministically.

    Parameters
    ----------
    data_dir : Path | str
        Path to directory with locations.csv, incidents.csv, public_complaints.csv.
    config : Optional[WeightConfig]
        Optional custom weight configuration.

    Returns
    -------
    pd.DataFrame
        Fully enriched and ranked priority DataFrame.
    """
    datasets = load_all_datasets(data_dir)
    agg_df = aggregate_location_data(
        datasets["locations"],
        datasets["incidents"],
        datasets["public_complaints"],
    )
    scored_df = calculate_priority_scores(agg_df, config=config)
    enriched_df = enrich_with_explanations(scored_df)
    ranked_df = rank_locations(enriched_df)
    return ranked_df
