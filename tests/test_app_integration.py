"""
Integration Tests for CityFix AI Dashboard and Web API Service
==============================================================
Datathon 2026 — Track 3: Smart City (Where Should We Fix First?)
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from server import answer_ai_query, load_or_generate_payload

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class TestDashboardDataPayload(unittest.TestCase):
    """Verify precomputed dashboard payload data integrity and structure."""

    def setUp(self):
        self.payload = load_or_generate_payload()

    def test_summary_metrics_match_dataset(self):
        """Verify summary metrics match physical dataset totals."""
        summary = self.payload["summary"]
        self.assertEqual(summary["total_locations"], 1000)
        self.assertEqual(summary["total_incidents"], 10000)
        self.assertEqual(summary["total_complaints"], 8000)
        self.assertEqual(summary["total_unresolved_incidents"], 2874)
        self.assertEqual(summary["total_open_complaints"], 3438)
        self.assertEqual(len(summary["zones"]), 20)

    def test_all_1000_locations_present_and_structured(self):
        """Verify all 1,000 locations have complete indicators and explanations."""
        locations = self.payload["locations"]
        self.assertEqual(len(locations), 1000)

        # Check top location record structure
        first = locations[0]
        self.assertEqual(first["location_id"], "L0965")
        self.assertEqual(first["priority_level"], "Critical")
        self.assertGreater(first["priority_score"], 60.0)
        self.assertIn("suggested_next_action", first)
        self.assertIn("contributing_factors", first)
        self.assertIn("subscore_incident", first)
        self.assertIn("subscore_backlog", first)
        self.assertIn("subscore_vulnerability", first)
        self.assertIn("subscore_complaint", first)


class TestAiCityIntelligenceEngine(unittest.TestCase):
    """Verify deterministic AI intelligence query handler."""

    def setUp(self):
        self.payload = load_or_generate_payload()

    def test_query_top_priority(self):
        """Verify top priority query returns highest-ranked locations."""
        res = answer_ai_query("Which locations have the highest priority?", self.payload)
        self.assertEqual(res["type"], "top_priority")
        self.assertEqual(len(res["matched_locations"]), 5)
        self.assertEqual(res["matched_locations"][0]["location_id"], "L0965")

    def test_query_location_deep_dive(self):
        """Verify querying a specific location ID returns targeted analysis."""
        res = answer_ai_query("Why is location L0965 ranked highly?", self.payload)
        self.assertEqual(res["type"], "location_deep_dive")
        self.assertIn("L0965", res["title"])
        self.assertEqual(len(res["matched_locations"]), 1)
        self.assertEqual(res["matched_locations"][0]["location_id"], "L0965")

    def test_query_unresolved_backlog(self):
        """Verify query on unresolved backlogs sorts by unresolved incidents."""
        res = answer_ai_query("Which locations have recurring unresolved incidents?", self.payload)
        self.assertEqual(res["type"], "backlog")
        self.assertGreater(len(res["matched_locations"]), 0)
        unres_counts = [l["unresolved_incidents"] for l in res["matched_locations"]]
        self.assertTrue(all(unres_counts[i] >= unres_counts[i + 1] for i in range(len(unres_counts) - 1)))

    def test_query_drainage_and_flooding(self):
        """Verify query on drainage returns drainage hotspots."""
        res = answer_ai_query("Where are recurring drainage and flooding issues concentrated?", self.payload)
        self.assertEqual(res["type"], "drainage")
        self.assertGreater(len(res["matched_locations"]), 0)

    def test_query_vulnerable_receptors(self):
        """Verify query on schools and hospitals returns vulnerable corridors."""
        res = answer_ai_query("Which locations near schools or hospitals have poor roads?", self.payload)
        self.assertEqual(res["type"], "vulnerability")
        self.assertGreater(len(res["matched_locations"]), 0)
        for loc in res["matched_locations"]:
            self.assertTrue(loc["near_school"] or loc["near_hospital"])


if __name__ == "__main__":
    unittest.main()
