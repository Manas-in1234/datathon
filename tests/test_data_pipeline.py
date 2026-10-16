"""Automated tests for data pipeline and data quality rules."""

import csv
import gzip
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "03_smart_city_where_fix_first"


class TestDataPipeline(unittest.TestCase):

    def setUp(self):
        with (RAW / "locations.csv").open(encoding="utf-8-sig") as f:
            self.locations = list(csv.DictReader(f))
        with (RAW / "incidents.csv").open(encoding="utf-8-sig") as f:
            self.incidents = list(csv.DictReader(f))
        with (RAW / "public_complaints.csv").open(encoding="utf-8-sig") as f:
            self.complaints = list(csv.DictReader(f))

    def test_dataset_record_counts(self):
        """Expected dataset sizes: 1,000 locations, 10,000 incidents, 8,000 complaints."""
        self.assertEqual(len(self.locations), 1000)
        self.assertEqual(len(self.incidents), 10000)
        self.assertEqual(len(self.complaints), 8000)

    def test_location_ids_and_relationships(self):
        """All location IDs must be unique and match across files."""
        loc_ids = [l["location_id"] for l in self.locations]
        self.assertEqual(len(loc_ids), len(set(loc_ids)))

        inc_loc_ids = {i["location_id"] for i in self.incidents}
        comp_loc_ids = {c["location_id"] for c in self.complaints}

        self.assertTrue(inc_loc_ids.issubset(set(loc_ids)))
        self.assertTrue(comp_loc_ids.issubset(set(loc_ids)))

    def test_unresolved_incidents_turnaround_exclusion(self):
        """Unresolved incidents with populated resolution_hours must not contaminate completed turnaround time."""
        unresolved_with_hours = [
            i for i in self.incidents
            if i["resolved"] == "0" and i.get("resolution_hours") and float(i["resolution_hours"]) > 0
        ]
        self.assertEqual(len(unresolved_with_hours), 2874)

        # Check records.json.gz
        records_path = ROOT / "records.json.gz"
        self.assertTrue(records_path.exists())
        with gzip.open(records_path, "rt", encoding="utf-8") as f:
            records_by_loc = json.load(f)

        for loc_id, recs in records_by_loc.items():
            for rec in recs:
                if rec["kind"] == "Incident" and rec["status"] == "Open":
                    self.assertIsNone(
                        rec["resolutionHours"],
                        f"Unresolved incident {rec['id']} has non-null resolutionHours!"
                    )

    def test_open_complaints_turnaround_exclusion(self):
        """Complaints with Open/In progress/Assigned status must not contaminate completed turnaround time."""
        open_with_days = [
            c for c in self.complaints
            if c["status"] in {"Open", "In progress", "Assigned"}
            and c.get("days_to_resolution") and float(c["days_to_resolution"]) >= 0
        ]
        self.assertEqual(len(open_with_days), 3438)

        # Check records.json.gz
        with gzip.open(ROOT / "records.json.gz", "rt", encoding="utf-8") as f:
            records_by_loc = json.load(f)

        for loc_id, recs in records_by_loc.items():
            for rec in recs:
                if rec["kind"] == "Complaint" and rec["status"] in {"Open", "In progress", "Assigned"}:
                    self.assertIsNone(
                        rec["resolutionDays"],
                        f"Open complaint {rec['id']} has non-null resolutionDays!"
                    )

    def test_data_js_bundle(self):
        """data.js must exist, define window.CITYFIX_DATA, and contain 1000 locations."""
        data_js_path = ROOT / "data.js"
        self.assertTrue(data_js_path.exists())
        content = data_js_path.read_text(encoding="utf-8")
        self.assertTrue(content.startswith("window.CITYFIX_DATA = "))

        json_str = content.replace("window.CITYFIX_DATA = ", "").rstrip(";\n")
        bundle = json.loads(json_str)

        self.assertEqual(len(bundle["locations"]), 1000)
        self.assertEqual(bundle["summary"]["locations"], 1000)
        self.assertEqual(bundle["summary"]["incidents"], 10000)
        self.assertEqual(bundle["summary"]["complaints"], 8000)
        self.assertEqual(bundle["summary"]["openIncidents"], 2874)
        self.assertEqual(bundle["summary"]["openComplaints"], 3438)
        self.assertEqual(bundle["summary"]["excludedUnresolvedTurnaroundRecords"], 2874 + 3438)


if __name__ == "__main__":
    unittest.main()
