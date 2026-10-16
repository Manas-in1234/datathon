"""Automated tests for machine learning model training, prediction, and holdout evaluation."""

import json
import math
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent.parent


class TestMLModel(unittest.TestCase):

    def setUp(self):
        model_path = ROOT / "forecast-model.json"
        self.assertTrue(model_path.exists())
        self.model = json.loads(model_path.read_text(encoding="utf-8"))

    def test_model_structure(self):
        """Model artifact must contain trees, features, metrics, predictions, and actuals."""
        self.assertEqual(self.model["model"], "CityFix Random Forest Regressor")
        self.assertEqual(self.model["target"], "Q4 incident count (Oct–Dec 2025)")
        self.assertEqual(self.model["trainLocations"], 800)
        self.assertEqual(self.model["testLocations"], 200)
        self.assertEqual(len(self.model["trees"]), 36)
        self.assertEqual(len(self.model["predictions"]), 1000)
        self.assertEqual(len(self.model["actuals"]), 1000)
        self.assertEqual(len(self.model["holdoutLocationIds"]), 200)

    def test_holdout_evaluation_metrics(self):
        """MAE and RMSE must be genuinely calculated from predictions and actuals on the holdout set."""
        test_ids = self.model["holdoutLocationIds"]
        self.assertEqual(len(test_ids), 200)

        preds = [self.model["predictions"][lid] for lid in test_ids]
        actuals = [self.model["actuals"][lid] for lid in test_ids]

        errors = [p - a for p, a in zip(preds, actuals)]
        calculated_mae = sum(abs(e) for e in errors) / len(errors)
        calculated_rmse = math.sqrt(sum(e * e for e in errors) / len(errors))

        # Check against reported metrics
        reported_mae = self.model["metrics"]["mae"]
        reported_rmse = self.model["metrics"]["rmse"]

        self.assertAlmostEqual(calculated_mae, reported_mae, delta=0.01)
        self.assertAlmostEqual(calculated_rmse, reported_rmse, delta=0.01)

    def test_baseline_comparison(self):
        """Metrics must accurately compare against mean baseline and historical Q-average."""
        metrics = self.model["metrics"]
        self.assertIn("baselineMae", metrics)
        self.assertIn("historicalBaselineMae", metrics)

        # In this synthetic educational dataset, Mean Baseline is ~1.255
        self.assertAlmostEqual(metrics["baselineMae"], 1.255, delta=0.02)
        # Historical Q-average is ~1.382
        self.assertAlmostEqual(metrics["historicalBaselineMae"], 1.382, delta=0.05)
        # Random Forest beats historical baseline
        self.assertTrue(metrics["beatsHistoricalBaseline"])

    def test_tree_walk_prediction(self):
        """Walking the decision tree nodes directly must produce valid non-negative float predictions."""
        def walk(t, x):
            while "v" not in t:
                t = t["l"] if x[t["f"]] <= t["t"] else t["r"]
            return t["v"]

        dummy_features = [2.0, 3.0, 2.0, 1.0, 2.0, 1.0, 1, 1, 0, 0, 5.0]
        preds = [walk(t, dummy_features) for t in self.model["trees"]]
        ensemble_pred = sum(preds) / len(preds)
        self.assertGreater(ensemble_pred, 0.0)
        self.assertLess(ensemble_pred, 10.0)


if __name__ == "__main__":
    unittest.main()
