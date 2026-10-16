"""Automated tests for the 5-factor Priority Engine."""

import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent.parent


class TestPriorityEngine(unittest.TestCase):

    def setUp(self):
        data_js_path = ROOT / "data.js"
        content = data_js_path.read_text(encoding="utf-8")
        json_str = content.replace("window.CITYFIX_DATA = ", "").rstrip(";\n")
        self.bundle = json.loads(json_str)
        self.locations = self.bundle["locations"]

    def compute_priority(self, loc, ceilings):
        weights = [0.30, 0.25, 0.20, 0.15, 0.10]
        road_risk = {"Good": 0.20, "Fair": 0.45, "Poor": 0.75, "Critical": 1.00}
        ped_risk = {"Low": 0.35, "Medium": 0.65, "High": 1.00}

        def scale(val, ceil):
            return min(1.0, max(0.0, val / max(1, ceil)))

        exposure = (0.5 if loc.get("school") else 0.0) + (0.5 if loc.get("hospital") else 0.0)
        context = (
            (road_risk.get(loc.get("condition"), 0.40)) * 0.40
            + (ped_risk.get(loc.get("pedestrian"), 0.50)) * 0.30
            + exposure * 0.20
            + scale(loc.get("density", 0), ceilings["density"]) * 0.10
        )

        values = [
            scale(loc.get("incidentCount", 0), ceilings["incidents"]),
            min(1.0, loc.get("avgSeverity", 0) / 4.0),
            scale(loc.get("complaintCount", 0), ceilings["complaints"]),
            scale(loc.get("unresolved", 0) + loc.get("openComplaints", 0), ceilings["backlog"]),
            min(1.0, max(0.0, context)),
        ]

        factor_points = [round(val * weights[i] * 100) for i, val in enumerate(values)]
        priority = min(100, max(0, sum(factor_points)))
        return priority, factor_points, values

    def get_ceilings(self):
        def p95(vals):
            s = sorted(vals)
            idx = max(0, int(len(s) * 0.95) - 1)
            return s[idx] or 1

        return {
            "incidents": p95([l["incidentCount"] for l in self.locations]),
            "complaints": p95([l["complaintCount"] for l in self.locations]),
            "backlog": p95([l["unresolved"] + l["openComplaints"] for l in self.locations]),
            "density": p95([l["density"] for l in self.locations]),
        }

    def test_priority_score_bounds(self):
        """Every location's priority index must strictly be in [0, 100]."""
        ceilings = self.get_ceilings()
        for loc in self.locations:
            priority, points, _ = self.compute_priority(loc, ceilings)
            self.assertGreaterEqual(priority, 0)
            self.assertLessEqual(priority, 100)
            self.assertEqual(priority, sum(points))

    def test_edge_case_zero_values(self):
        """Zero values must not crash and produce 0 or minimum contextual points."""
        ceilings = self.get_ceilings()
        empty_loc = {
            "id": "LTEST", "zone": "ZONE_01", "road": "Local", "condition": "Good",
            "density": 0, "school": False, "hospital": False, "pedestrian": "Low",
            "incidentCount": 0, "avgSeverity": 0, "complaintCount": 0, "unresolved": 0,
            "openComplaints": 0
        }
        priority, points, values = self.compute_priority(empty_loc, ceilings)
        self.assertGreaterEqual(priority, 0)
        self.assertLessEqual(priority, 100)
        # Incident, severity, complaint, and backlog factors should be 0
        self.assertEqual(points[0], 0)
        self.assertEqual(points[1], 0)
        self.assertEqual(points[2], 0)
        self.assertEqual(points[3], 0)

    def test_monotonicity(self):
        """Increasing risk or incidents must never reduce the priority score."""
        ceilings = self.get_ceilings()
        base_loc = {
            "id": "LTEST", "zone": "ZONE_01", "road": "Local", "condition": "Fair",
            "density": 5000, "school": False, "hospital": False, "pedestrian": "Medium",
            "incidentCount": 5, "avgSeverity": 2.0, "complaintCount": 4, "unresolved": 2,
            "openComplaints": 1
        }
        p_base, _, _ = self.compute_priority(base_loc, ceilings)

        more_inc = dict(base_loc, incidentCount=10)
        p_inc, _, _ = self.compute_priority(more_inc, ceilings)
        self.assertGreaterEqual(p_inc, p_base)

        more_sev = dict(base_loc, avgSeverity=3.8)
        p_sev, _, _ = self.compute_priority(more_sev, ceilings)
        self.assertGreaterEqual(p_sev, p_base)

        more_comp = dict(base_loc, complaintCount=12)
        p_comp, _, _ = self.compute_priority(more_comp, ceilings)
        self.assertGreaterEqual(p_comp, p_base)


if __name__ == "__main__":
    unittest.main()
