"""Behavior checks for data quality reporting."""

import unittest
import pandas as pd
from dr_drama.analysis.quality import missingness_report


class MissingnessReportTests(unittest.TestCase):
    def test_missing_values_are_distinct_from_zero(self):
        frame = pd.DataFrame({"rating": [0, None, 8], "title": ["A", "B", "C"]})
        original = frame.copy(deep=True)
        report = missingness_report(frame)
        self.assertEqual(report.loc["rating", "missing_count"], 1)
        self.assertAlmostEqual(report.loc["rating", "missing_percent"], 100 / 3)
        self.assertEqual(report.loc["title", "missing_count"], 0)
        pd.testing.assert_frame_equal(frame, original)

    def test_empty_dataset_has_undefined_percentages(self):
        report = missingness_report(pd.DataFrame(columns=["rating"]))
        self.assertEqual(report.loc["rating", "missing_count"], 0)
        self.assertTrue(pd.isna(report.loc["rating", "missing_percent"]))


if __name__ == "__main__":
    unittest.main()
