"""
Unit & Integration Tests for CityFix AI Priority Engine
=======================================================
Datathon 2026 — Track 3: Smart City (Where Should We Fix First?)
"""

from __future__ import annotations

import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from src.data_pipeline import load_all_datasets
from src.priority_engine import (
    WeightConfig,
    aggregate_location_data,
    build_priority_pipeline,
    calculate_priority_scores,
    enrich_with_explanations,
    generate_location_explanation,
    rank_locations,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"


class TestPriorityEngineAggregation(unittest.TestCase):
    """Tests for location aggregation logic and input validation."""

    def setUp(self):
        self.datasets = load_all_datasets(DATA_DIR)

    def test_aggregate_all_locations_preserved(self):
        """Verify aggregation preserves all 1,000 master locations."""
        agg = aggregate_location_data(
            self.datasets["locations"],
            self.datasets["incidents"],
            self.datasets["public_complaints"],
        )
        self.assertEqual(len(agg), 1000)
        self.assertEqual(agg["incident_count"].sum(), 10000)
        self.assertEqual(agg["complaint_count"].sum(), 8000)
        self.assertIn("critical_incidents", agg.columns)
        self.assertIn("unresolved_incidents", agg.columns)
        self.assertIn("inc_pothole", agg.columns)
        self.assertIn("comp_drainage", agg.columns)

    def test_missing_required_column_raises_error(self):
        """Verify KeyError is raised when required columns are absent."""
        tampered_loc = self.datasets["locations"].drop(columns=["road_condition"])
        with self.assertRaises(KeyError):
            aggregate_location_data(
                tampered_loc,
                self.datasets["incidents"],
                self.datasets["public_complaints"],
            )

        tampered_inc = self.datasets["incidents"].drop(columns=["severity"])
        with self.assertRaises(KeyError):
            aggregate_location_data(
                self.datasets["locations"],
                tampered_inc,
                self.datasets["public_complaints"],
            )

        tampered_comp = self.datasets["public_complaints"].drop(columns=["status"])
        with self.assertRaises(KeyError):
            aggregate_location_data(
                self.datasets["locations"],
                self.datasets["incidents"],
                tampered_comp,
            )

    def test_empty_locations_raises_error(self):
        """Verify empty locations dataframe raises ValueError."""
        empty_loc = self.datasets["locations"].head(0)
        with self.assertRaises(ValueError):
            aggregate_location_data(
                empty_loc,
                self.datasets["incidents"],
                self.datasets["public_complaints"],
            )

    def test_empty_incidents_handled_gracefully(self):
        """Verify locations with zero incidents are handled without error."""
        empty_inc = self.datasets["incidents"].head(0)
        agg = aggregate_location_data(
            self.datasets["locations"],
            empty_inc,
            self.datasets["public_complaints"],
        )
        self.assertEqual(len(agg), 1000)
        self.assertEqual(agg["incident_count"].sum(), 0)
        self.assertEqual(agg["critical_incidents"].sum(), 0)


class TestPriorityScoring(unittest.TestCase):
    """Tests for priority score calculation, normalization, and reproducibility."""

    def setUp(self):
        self.datasets = load_all_datasets(DATA_DIR)
        self.agg = aggregate_location_data(
            self.datasets["locations"],
            self.datasets["incidents"],
            self.datasets["public_complaints"],
        )

    def test_score_reproducibility(self):
        """Verify scoring produces identical deterministic results on identical inputs."""
        scored_1 = calculate_priority_scores(self.agg)
        scored_2 = calculate_priority_scores(self.agg)
        pd.testing.assert_series_equal(
            scored_1["priority_score"],
            scored_2["priority_score"],
        )
        pd.testing.assert_series_equal(
            scored_1["priority_level"],
            scored_2["priority_level"],
        )

    def test_score_normalization_bounds(self):
        """Verify subscores and composite priority score are bounded within [0.0, 100.0]."""
        scored = calculate_priority_scores(self.agg)
        for col in [
            "subscore_incident",
            "subscore_backlog",
            "subscore_vulnerability",
            "subscore_complaint",
            "priority_score",
        ]:
            self.assertTrue(
                (scored[col] >= 0.0).all(),
                f"Column {col} has values below 0.0",
            )
            self.assertTrue(
                (scored[col] <= 100.0).all(),
                f"Column {col} has values above 100.0",
            )

    def test_invalid_weight_config_validation(self):
        """Verify WeightConfig raises ValueError when weights do not sum to 1.0 or are negative."""
        with self.assertRaises(ValueError):
            cfg = WeightConfig(incident_weight=0.9, backlog_weight=0.5)
            cfg.validate()

        with self.assertRaises(ValueError):
            cfg = WeightConfig(incident_weight=-0.1, backlog_weight=0.4, vulnerability_weight=0.4, complaint_weight=0.3)
            cfg.validate()

    def test_priority_level_assignment(self):
        """Verify priority levels follow configured thresholds."""
        config = WeightConfig(critical_threshold=50.0, high_threshold=40.0, medium_threshold=30.0)
        scored = calculate_priority_scores(self.agg, config=config)

        critical_mask = scored["priority_score"] >= 50.0
        self.assertTrue((scored.loc[critical_mask, "priority_level"] == "Critical").all())

        high_mask = (scored["priority_score"] >= 40.0) & (scored["priority_score"] < 50.0)
        self.assertTrue((scored.loc[high_mask, "priority_level"] == "High").all())

        med_mask = (scored["priority_score"] >= 30.0) & (scored["priority_score"] < 40.0)
        self.assertTrue((scored.loc[med_mask, "priority_level"] == "Medium").all())

        low_mask = scored["priority_score"] < 30.0
        self.assertTrue((scored.loc[low_mask, "priority_level"] == "Low").all())


class TestRankingAndFiltering(unittest.TestCase):
    """Tests for ranking, tie-breaking, top-N, and multi-criteria filters."""

    def setUp(self):
        self.datasets = load_all_datasets(DATA_DIR)
        agg = aggregate_location_data(
            self.datasets["locations"],
            self.datasets["incidents"],
            self.datasets["public_complaints"],
        )
        self.scored = calculate_priority_scores(agg)

    def test_ranking_descending_order(self):
        """Verify ranked output is strictly monotonically non-increasing by priority score."""
        ranked = rank_locations(self.scored)
        scores = ranked["priority_score"].to_numpy()
        self.assertTrue(np.all(scores[:-1] >= scores[1:]))

    def test_top_n_selection(self):
        """Verify top_n limits the number of output records accurately."""
        top_5 = rank_locations(self.scored, top_n=5)
        self.assertEqual(len(top_5), 5)

        top_25 = rank_locations(self.scored, top_n=25)
        self.assertEqual(len(top_25), 25)

    def test_zone_filtering(self):
        """Verify zone filtering returns exclusively the requested zone."""
        filtered = rank_locations(self.scored, zone="ZONE_01")
        self.assertTrue((filtered["zone"] == "ZONE_01").all())
        self.assertGreater(len(filtered), 0)

    def test_priority_level_filtering(self):
        """Verify filtering by priority_level returns matching levels."""
        filtered = rank_locations(self.scored, priority_level="Critical")
        self.assertTrue((filtered["priority_level"] == "Critical").all())

    def test_incident_category_filtering(self):
        """Verify filtering by incident category returns locations with >0 incidents in that category."""
        filtered = rank_locations(self.scored, incident_category="Pothole")
        self.assertTrue((filtered["inc_pothole"] > 0).all())

    def test_unknown_incident_category_raises_error(self):
        """Verify unknown incident category raises ValueError."""
        with self.assertRaises(ValueError):
            rank_locations(self.scored, incident_category="NonExistentCategory")


class TestExplanationsAndDataIntegrity(unittest.TestCase):
    """Tests for structured explanations and dataset immutability."""

    def setUp(self):
        self.datasets = load_all_datasets(DATA_DIR)

    def test_explanation_structure_and_completeness(self):
        """Verify each location gets a complete and structured explanation."""
        agg = aggregate_location_data(
            self.datasets["locations"],
            self.datasets["incidents"],
            self.datasets["public_complaints"],
        )
        scored = calculate_priority_scores(agg)
        enriched = enrich_with_explanations(scored)

        self.assertIn("severity_breakdown", enriched.columns)
        self.assertIn("contributing_factors", enriched.columns)
        self.assertIn("suggested_next_action", enriched.columns)
        self.assertIn("missing_evidence_or_limitations", enriched.columns)

        # Inspect first row explanation details
        sample = enriched.iloc[0]
        self.assertIsInstance(sample["severity_breakdown"], dict)
        self.assertGreater(len(sample["contributing_factors"]), 0)
        self.assertGreater(len(sample["suggested_next_action"]), 0)
        self.assertIn("Synthetic educational dataset", sample["missing_evidence_or_limitations"])

    def test_no_modification_of_original_datasets(self):
        """Verify pipeline execution does not mutate original DataFrames or files."""
        # Capture original hashes and shapes
        orig_loc_shape = self.datasets["locations"].shape
        orig_inc_shape = self.datasets["incidents"].shape
        orig_comp_shape = self.datasets["public_complaints"].shape

        _ = build_priority_pipeline(DATA_DIR)

        # Check in-memory shapes
        self.assertEqual(self.datasets["locations"].shape, orig_loc_shape)
        self.assertEqual(self.datasets["incidents"].shape, orig_inc_shape)
        self.assertEqual(self.datasets["public_complaints"].shape, orig_comp_shape)


if __name__ == "__main__":
    unittest.main()
