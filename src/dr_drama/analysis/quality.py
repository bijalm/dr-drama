"""Data quality summaries for tabular datasets."""

import pandas as pd


def missingness_report(frame: pd.DataFrame) -> pd.DataFrame:
    """Return missing counts and percentages per column without changing input.

    Empty strings must be normalized by ingestion before using this report.
    Percentages are undefined (NaN) when there are no rows.
    """
    counts = frame.isna().sum()
    percentages = counts / len(frame) * 100 if len(frame) else counts * float("nan")
    return pd.DataFrame({"missing_count": counts, "missing_percent": percentages})
