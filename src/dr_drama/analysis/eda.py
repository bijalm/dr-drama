"""Descriptive summaries with explicit denominators and list membership handling."""

import json
from pathlib import Path

import numpy as np
import pandas as pd


def load_history(path: Path) -> pd.DataFrame:
    """Load only analysis fields and validate values without changing source data."""
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    required = ['external_api_id', 'canonical_title', 'my_rating', 'status', 'favorite',
                'would_rewatch', 'genres', 'main_cast', 'release_year',
                'number_of_episodes', 'public_rating', 'public_vote_count', 'popularity']
    missing = set(required) - set(frame)
    if missing:
        raise ValueError(f'Missing analysis columns: {sorted(missing)}')
    if frame['external_api_id'].eq('').any() or frame['external_api_id'].duplicated().any():
        raise ValueError('Unique nonempty drama IDs are required for this notebook')
    for field in ['my_rating', 'release_year', 'number_of_episodes', 'public_rating', 'public_vote_count', 'popularity']:
        frame[field] = pd.to_numeric(frame[field].replace('', np.nan), errors='raise')
    ratings = frame['my_rating'].dropna()
    if not ratings.between(1, 10).all() or not np.isclose(ratings * 10, np.round(ratings * 10), rtol=0, atol=1e-9).all():
        raise ValueError('Personal ratings violate the 1–10 one-decimal contract')
    if not frame['status'].isin(['completed','dropped','unfinished','watching']).all():
        raise ValueError('Unknown viewing status')
    for field in ['favorite', 'would_rewatch']:
        if not frame[field].isin(['yes','no','']).all():
            raise ValueError(f'Unexpected {field} category')
    frame['high_rating'] = frame['my_rating'].ge(8).where(frame['my_rating'].notna())
    frame['completed'] = frame['status'].eq('completed')
    frame['dropped'] = frame['status'].eq('dropped')
    return frame


def memberships(frame: pd.DataFrame, field: str) -> pd.DataFrame:
    """One row per drama/member, never a genre-by-actor Cartesian product.

    Collapse name whitespace and repeated labels within one drama for counting;
    original data remains unchanged. These labels are not verified person IDs.
    """
    result = frame.copy()
    def parse(value):
        entries = json.loads(value) if value else []
        if not isinstance(entries, list) or any(not isinstance(x, str) for x in entries):
            raise ValueError(f'{field} must contain JSON string arrays')
        return list(dict.fromkeys(' '.join(x.split()) for x in entries if x.strip()))
    result[field] = result[field].map(parse)
    return result.explode(field).dropna(subset=[field]).drop_duplicates(['external_api_id', field])


def grouped_summary(frame: pd.DataFrame, group: str) -> pd.DataFrame:
    """Rates use all rated/group records; unfinished is not equivalent to dropped."""
    result = frame.groupby(group, observed=True).agg(
        dramas=('external_api_id','nunique'), rated=('my_rating','count'),
        mean_rating=('my_rating','mean'), median_rating=('my_rating','median'),
        high_rated=('high_rating','sum'), completed=('completed','sum'),
        dropped=('dropped','sum'))
    result['high_rating_pct'] = result['high_rated'] / result['rated'].replace(0,np.nan) * 100
    result['completion_pct'] = result['completed'] / result['dramas'].replace(0,np.nan) * 100
    result['drop_pct'] = result['dropped'] / result['dramas'].replace(0,np.nan) * 100
    result['small_sample'] = result['dramas'] < 5
    return result


def correlations(frame: pd.DataFrame, x: str, y: str = 'my_rating') -> pd.Series:
    """Pearson and rank correlation for complete pairs; no significance claim."""
    pairs = frame[[x,y]].dropna()
    eligible = len(pairs) >= 10 and pairs[x].nunique() > 1 and pairs[y].nunique() > 1
    return pd.Series({'paired_n': len(pairs),
                      'pearson': pairs[x].corr(pairs[y]) if eligible else np.nan,
                      'spearman': pairs[x].rank().corr(pairs[y].rank()) if eligible else np.nan})
