"""Deterministic public-rating and content-based recommendation baselines."""

import json
from dataclasses import dataclass

import numpy as np
import pandas as pd


METADATA_FIELDS = [
    'external_api_id', 'canonical_title', 'genres', 'main_cast', 'release_year',
    'number_of_episodes', 'public_rating', 'public_vote_count', 'popularity',
    'popularity_metric', 'source_url', 'metadata_retrieved_at', 'catalog_status',
]


def labels(value: object) -> set[str]:
    """Read JSON string arrays, normalizing whitespace and case in memory only."""
    if value is None or (isinstance(value, float) and np.isnan(value)) or value == '':
        return set()
    items = json.loads(value) if isinstance(value, str) else value
    if not isinstance(items, list) or any(not isinstance(x, str) for x in items):
        raise ValueError('Expected a JSON array of strings')
    return {' '.join(x.split()).casefold() for x in items if x.strip()}


def metadata(frame: pd.DataFrame) -> pd.DataFrame:
    """Whitelist item attributes: personal outcomes never enter candidate scoring."""
    result = frame.reindex(columns=METADATA_FIELDS).copy().reset_index(drop=True)
    ids = result.external_api_id
    if ids.isna().any() or ids.astype(str).str.strip().eq('').any():
        raise ValueError('Nonempty MDL IDs are required')
    result['external_api_id'] = ids.astype(str)
    if result.external_api_id.duplicated().any():
        raise ValueError('Duplicate MDL IDs must be resolved before ranking')
    for field in ['public_rating', 'public_vote_count', 'popularity']:
        result[field] = pd.to_numeric(result[field].replace('', np.nan), errors='raise')
        present = result[field].dropna()
        if not np.isfinite(present).all():
            raise ValueError(f'{field} must be finite')
    if not result.public_rating.dropna().between(0, 10, inclusive='right').all():
        raise ValueError('Public ratings must be greater than 0 and at most 10')
    for field in ['public_vote_count', 'popularity']:
        values = result[field].dropna()
        if (values < 0).any() or (values % 1 != 0).any():
            raise ValueError(f'{field} must be a nonnegative integer')
    return result


def unwatched(candidates: pd.DataFrame, history: pd.DataFrame) -> pd.DataFrame:
    """Exclude every history ID, including dropped, unfinished, and watching."""
    items = metadata(candidates)
    return items[~items.external_api_id.isin(history.external_api_id.astype(str))].copy()


def public_prior(training: pd.DataFrame) -> float:
    """Mean available training-item public score; fixed neutral fallback is 5.5."""
    ratings = metadata(training).public_rating.dropna()
    return float(ratings.mean()) if len(ratings) else 5.5


def rank_public(candidates: pd.DataFrame, history: pd.DataFrame, *,
                prior: float | None = None, prior_votes: float = 1000) -> pd.DataFrame:
    """Vote-shrunk public rating, then ascending MDL popularity rank and ID.

    Missing rating or votes receives the prior only and is explicitly flagged.
    This is a public-quality ranking score, not a personal rating prediction.
    """
    if not np.isfinite(prior_votes) or prior_votes <= 0:
        raise ValueError('prior_votes must be positive and finite')
    prior = public_prior(history) if prior is None else prior
    if not np.isfinite(prior) or not 0 < prior <= 10:
        raise ValueError('prior must be on the public 0–10 scale')
    result = unwatched(candidates, history)
    supported = result.public_rating.notna() & result.public_vote_count.gt(0)
    votes = result.public_vote_count.where(supported, 0)
    result['prior_only'] = ~supported
    result['score'] = (votes * result.public_rating.fillna(prior) + prior_votes * prior) / (votes + prior_votes)
    result['score_kind'] = 'shrunk_public_rating'
    result['popularity_tiebreak'] = result.popularity.where(
        result.popularity_metric.eq('rank') & result.popularity.gt(0), np.inf)
    return result.sort_values(['score', 'popularity_tiebreak', 'external_api_id'],
                             ascending=[False, True, True]).reset_index(drop=True)


def _unit_rows(matrix: np.ndarray) -> np.ndarray:
    lengths = np.linalg.norm(matrix, axis=1, keepdims=True)
    return np.divide(matrix, lengths, out=np.zeros_like(matrix), where=lengths > 0)


@dataclass
class ContentProfile:
    """Training-only vocabularies and average unit vectors for liked items."""

    vocabularies: dict[str, list[str]]
    vectors: dict[str, np.ndarray]
    positive_ids: tuple[str, ...]
    cast_weight: float = 0.0

    @classmethod
    def fit(cls, training: pd.DataFrame, *, threshold: float = 8,
            cast_weight: float = 0.0) -> 'ContentProfile':
        """Use completed, rated 8+ training dramas; no outcome-based weighting."""
        if not 0 <= cast_weight <= 1 or not 1 <= threshold <= 10:
            raise ValueError('Invalid cast weight or rating threshold')
        items = metadata(training)
        ratings = pd.to_numeric(training.my_rating, errors='raise').to_numpy()
        positive = (training.status.to_numpy() == 'completed') & (ratings >= threshold)
        vocabularies, vectors = {}, {}
        for field in ['genres', 'main_cast']:
            entries = items[field].map(labels).tolist()
            vocabulary = sorted(set().union(*entries))
            matrix = np.array([[float(label in entry) for label in vocabulary]
                               for entry in entries]).reshape(len(items), len(vocabulary))
            normalized = _unit_rows(matrix)
            vector = normalized[positive].mean(axis=0) if positive.any() else np.zeros(len(vocabulary))
            length = np.linalg.norm(vector)
            vocabularies[field] = vocabulary
            vectors[field] = vector / length if length else vector
        return cls(vocabularies, vectors, tuple(items.loc[positive, 'external_api_id']), cast_weight)

    @property
    def usable(self) -> bool:
        return bool(self.positive_ids) and bool(
            (1 - self.cast_weight) * np.linalg.norm(self.vectors['genres'])
            + self.cast_weight * np.linalg.norm(self.vectors['main_cast']))

    def rank(self, candidates: pd.DataFrame, history: pd.DataFrame) -> pd.DataFrame:
        """Weighted genre/cast cosine scores; fallback to public ranking if empty.

        Unseen labels contribute zero overlap but remain in candidate vector
        lengths, so unknown attributes cannot inflate similarity. Zero-overlap
        candidates stay at zero. Ties use IDs, not personal outcomes.
        """
        if not self.usable:
            result = rank_public(candidates, history)
            result['fallback_reason'] = 'No usable completed high-rating profile'
            return result
        result = unwatched(candidates, history)
        for field, prefix in [('genres', 'genre'), ('main_cast', 'cast')]:
            vocabulary = self.vocabularies[field]
            vector = self.vectors[field]
            lookup = dict(zip(vocabulary, vector))
            scores, shared, coverage = [], [], []
            for entry in result[field].map(labels):
                matched = sorted(x for x in entry if lookup.get(x, 0) > 0)
                scores.append(sum(lookup.get(x, 0) for x in entry) / np.sqrt(len(entry)) if entry else 0.0)
                shared.append(json.dumps(matched))
                coverage.append(len(entry.intersection(lookup)) / len(entry) if entry else 0.0)
            result[prefix + '_similarity'] = scores
            result['shared_' + field] = shared
            result[prefix + '_vocabulary_coverage'] = coverage
        result['score'] = ((1 - self.cast_weight) * result.genre_similarity
                           + self.cast_weight * result.cast_similarity)
        result['score_kind'] = 'content_similarity'
        result['fallback_reason'] = ''
        return result.sort_values(['score', 'external_api_id'], ascending=[False, True]).reset_index(drop=True)
