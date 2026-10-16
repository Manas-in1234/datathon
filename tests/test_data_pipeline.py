"""
Unit & Integration Tests for CityFix AI Data Pipeline
=====================================================
Datathon 2026 — Track 3: Smart City (Where Should We Fix First?)
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from src.data_pipeline import (
    export_validation_report,
    format_validation_report,
    inspect_data_quality,
    load_all_datasets,
    load_dataset,
    load_readme,
    run_validation_pipeline,
    validate_relationships,
    validate_schema,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"


class TestDatasetLoading(unittest.TestCase):
    """Tests for dataset loading and file-handling edge cases."""

    def test_load_existing_datasets(self):
        """Verify that existing CSV files load successfully into DataFrames."""
        loc_df = load_dataset(DATA_DIR / "locations.csv")
        self.assertIsInstance(loc_df, pd.DataFrame)
        self.assertEqual(len(loc_df), 1000)

        inc_df = load_dataset(DATA_DIR / "incidents.csv", parse_dates=["timestamp"])
        self.assertIsInstance(inc_df, pd.DataFrame)
        self.assertEqual(len(inc_df), 10000)
        self.assertTrue(pd.api.types.is_datetime64_any_dtype(inc_df["timestamp"]))

        comp_df = load_dataset(DATA_DIR / "public_complaints.csv", parse_dates=["created_at"])
        self.assertIsInstance(comp_df, pd.DataFrame)
        self.assertEqual(len(comp_df), 8000)
        self.assertTrue(pd.api.types.is_datetime64_any_dtype(comp_df["created_at"]))

    def test_load_missing_file_raises_error(self):
        """Verify that attempting to load a non-existent file raises FileNotFoundError."""
        with self.assertRaises(FileNotFoundError):
            load_dataset(DATA_DIR / "non_existent_file.csv")

    def test_load_all_datasets(self):
        """Verify load_all_datasets loads all 3 DataFrames and README.txt."""
        datasets = load_all_datasets(DATA_DIR)
        self.assertIn("locations", datasets)
        self.assertIn("incidents", datasets)
        self.assertIn("public_complaints", datasets)
        self.assertIn("readme", datasets)
        self.assertIn("SMART CITY", datasets["readme"])

    def test_load_all_datasets_invalid_dir(self):
        """Verify that invalid directory raises FileNotFoundError."""
        with self.assertRaises(FileNotFoundError):
            load_all_datasets(DATA_DIR / "fake_dir_path")

    def test_load_readme_missing_fallback(self):
        """Verify that missing README returns descriptive string rather than crashing."""
        text = load_readme(DATA_DIR / "missing_readme.txt")
        self.assertEqual(text, "README.txt not found.")


class TestSchemaValidation(unittest.TestCase):
    """Tests for dataset schema validation, missing columns, and primary keys."""

    def setUp(self):
        self.datasets = load_all_datasets(DATA_DIR)

    def test_actual_datasets_pass_schema(self):
        """Verify that the original source datasets pass schema validation."""
        for name in ["locations", "incidents", "public_complaints"]:
            res = validate_schema(self.datasets[name], name)
            self.assertTrue(res["schema_passed"], f"Schema check failed for {name}: {res}")
            self.assertEqual(len(res["missing_columns"]), 0)
            self.assertTrue(res["primary_key_unique"])
            self.assertEqual(res["primary_key_nulls"], 0)
            self.assertEqual(len(res["null_counts"]), 0)
            self.assertEqual(res["full_row_duplicates"], 0)

    def test_missing_required_column_fails_validation(self):
        """Verify that dropping a required column flags schema_passed as False."""
        tampered_loc = self.datasets["locations"].drop(columns=["latitude"])
        res = validate_schema(tampered_loc, "locations")
        self.assertFalse(res["schema_passed"])
        self.assertIn("latitude", res["missing_columns"])

    def test_duplicate_primary_key_fails_validation(self):
        """Verify that duplicate primary keys are detected and flag schema_passed as False."""
        duplicate_row = self.datasets["locations"].iloc[[0]]
        tampered_loc = pd.concat([self.datasets["locations"], duplicate_row], ignore_index=True)
        res = validate_schema(tampered_loc, "locations")
        self.assertFalse(res["schema_passed"])
        self.assertFalse(res["primary_key_unique"])

    def test_null_value_in_required_column_fails_validation(self):
        """Verify that null values in required columns are detected."""
        tampered_inc = self.datasets["incidents"].copy()
        tampered_inc.loc[0, "severity"] = None
        res = validate_schema(tampered_inc, "incidents")
        self.assertFalse(res["schema_passed"])
        self.assertIn("severity", res["null_counts"])


class TestRelationshipValidation(unittest.TestCase):
    """Tests for foreign key referential integrity and join cardinality."""

    def setUp(self):
        self.datasets = load_all_datasets(DATA_DIR)

    def test_actual_relationships_pass(self):
        """Verify referential integrity on original datasets (0 unmatched)."""
        rel = validate_relationships(
            self.datasets["locations"],
            self.datasets["incidents"],
            self.datasets["public_complaints"],
        )
        self.assertTrue(rel["referential_integrity_passed"])
        self.assertEqual(rel["unmatched_incidents_count"], 0)
        self.assertEqual(rel["unmatched_complaints_count"], 0)
        self.assertEqual(rel["locations_without_incidents_count"], 0)
        self.assertEqual(rel["locations_without_complaints_count"], 0)
        self.assertEqual(rel["total_locations"], 1000)

    def test_unmatched_incident_location_detected(self):
        """Verify that an unmatched location_id in incidents is correctly caught."""
        tampered_inc = self.datasets["incidents"].copy()
        tampered_inc.loc[0, "location_id"] = "L_NON_EXISTENT_9999"
        rel = validate_relationships(
            self.datasets["locations"],
            tampered_inc,
            self.datasets["public_complaints"],
        )
        self.assertFalse(rel["referential_integrity_passed"])
        self.assertIn("L_NON_EXISTENT_9999", rel["unmatched_incidents_location_ids"])
        self.assertEqual(rel["unmatched_incidents_count"], 1)

    def test_unmatched_complaint_location_detected(self):
        """Verify that an unmatched location_id in complaints is correctly caught."""
        tampered_comp = self.datasets["public_complaints"].copy()
        tampered_comp.loc[0, "location_id"] = "L_ORPHAN_8888"
        rel = validate_relationships(
            self.datasets["locations"],
            self.datasets["incidents"],
            tampered_comp,
        )
        self.assertFalse(rel["referential_integrity_passed"])
        self.assertIn("L_ORPHAN_8888", rel["unmatched_complaints_location_ids"])
        self.assertEqual(rel["unmatched_complaints_count"], 1)


class TestDataQualityAndAnomalies(unittest.TestCase):
    """Tests for semantic anomaly detection, timestamp verification, and quality metrics."""

    def setUp(self):
        self.datasets = load_all_datasets(DATA_DIR)

    def test_timestamp_ranges_clean(self):
        """Verify timestamps parse without invalid values across 2025."""
        quality = inspect_data_quality(
            self.datasets["locations"],
            self.datasets["incidents"],
            self.datasets["public_complaints"],
        )
        inc_ts = quality["timestamp_ranges"]["incidents"]
        comp_ts = quality["timestamp_ranges"]["public_complaints"]
        self.assertEqual(inc_ts["invalid_timestamps"], 0)
        self.assertEqual(comp_ts["invalid_timestamps"], 0)
        self.assertTrue(inc_ts["min_timestamp"].startswith("2025"))
        self.assertTrue(inc_ts["max_timestamp"].startswith("2025"))

    def test_semantic_anomalies_flagged(self):
        """Verify that unresolved resolution hours anomaly is captured."""
        quality = inspect_data_quality(
            self.datasets["locations"],
            self.datasets["incidents"],
            self.datasets["public_complaints"],
        )
        anom = quality["semantic_anomalies"]
        # Unresolved incidents with resolution_hours
        self.assertEqual(
            anom["incidents_unresolved_with_resolution_hours"]["unresolved_with_resolution_hours_count"],
            2874,
        )
        # Non-resolved complaints with days_to_resolution
        self.assertEqual(
            anom["complaints_non_resolved_with_days_to_resolution"]["non_resolved_complaints_count"],
            3438,
        )
        self.assertGreater(len(quality["unresolved_questions"]), 0)


class TestFullPipelineAndReport(unittest.TestCase):
    """Integration test for end-to-end pipeline execution and report output."""

    def test_full_pipeline_run(self):
        """Verify run_validation_pipeline executes and returns PASSED status."""
        results = run_validation_pipeline(DATA_DIR)
        self.assertEqual(results["overall_status"], "PASSED")
        self.assertIn("schemas", results)
        self.assertIn("relationships", results)
        self.assertIn("quality", results)

    def test_report_formatting_and_export(self):
        """Verify formatting and disk export of the markdown validation report."""
        results = run_validation_pipeline(DATA_DIR)
        report_text = format_validation_report(results)
        self.assertIn("# CityFix AI — Data Inspection & Validation Report", report_text)
        self.assertIn("Join Cardinality Distribution", report_text)
        self.assertIn("Data Quality Concerns & Unresolved Questions", report_text)

        with tempfile.TemporaryDirectory() as tmp_dir:
            out_file = Path(tmp_dir) / "test_report.md"
            saved_path = export_validation_report(results, out_file)
            self.assertTrue(saved_path.is_file())
            content = saved_path.read_text(encoding="utf-8")
            self.assertEqual(content, report_text)


if __name__ == "__main__":
    unittest.main()
