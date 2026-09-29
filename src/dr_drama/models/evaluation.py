"""Fixed-fold retrospective evaluation; held-out outcomes are used only to score."""

import numpy as np
import pandas as pd

from dr_drama.models.baseline import ContentProfile, metadata, rank_public


def ranking_metrics(ranked_ids: list[str], relevant_ids: set[str], k: int = 5) -> dict:
    """Binary relevance metrics; Precision uses min(k, available candidates)."""
    if k < 1 or len(set(ranked_ids)) != len(ranked_ids):
        raise ValueError('k must be positive and ranked IDs unique')
    if not relevant_ids.issubset(ranked_ids):
        raise ValueError('Relevant IDs must belong to the evaluation candidates')
    cutoff = min(k, len(ranked_ids))
    hits = np.array([item in relevant_ids for item in ranked_ids[:cutoff]], dtype=float)
    discounts = 1 / np.log2(np.arange(2, cutoff + 2))
    ideal = discounts[:min(len(relevant_ids), cutoff)].sum()
    return {'precision_at_k': float(hits.mean()) if cutoff else np.nan,
            'recall_at_k': float(hits.sum() / len(relevant_ids)) if relevant_ids else np.nan,
            'ndcg_at_k': float((hits * discounts).sum() / ideal) if ideal else np.nan,
            'effective_k': cutoff}


def evaluate_baselines(history: pd.DataFrame, *, folds: int = 5,
                       seed: int = 42, k: int = 5, threshold: float = 8,
                       cast_weight: float = .2, prior_votes: float = 1000) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Stratify completed dramas by 8+ label; fit a new profile in each fold.

    Defaults are fixed before results are inspected. Cast weight is an exploratory
    ablation, not a tuned winner. Random expected Precision@k is relevance prevalence.
    Fold variability is descriptive, not a confidence interval.
    """
    metadata(history)  # Reject ambiguous or duplicated identities before splitting.
    frame = history[history.status.eq('completed') & history.my_rating.notna()].copy()
    frame['my_rating'] = pd.to_numeric(frame.my_rating, errors='raise')
    frame = frame.sort_values('external_api_id').reset_index(drop=True)
    target = frame.my_rating.ge(threshold).to_numpy()
    if folds < 2 or k < 1 or min(int(target.sum()), int((~target).sum())) < folds:
        raise ValueError('Need at least one positive and negative in every fold')
    rng = np.random.default_rng(seed)
    assignments = np.empty(len(frame), dtype=int)
    for label in [False, True]:
        indices = rng.permutation(np.flatnonzero(target == label))
        assignments[indices] = np.arange(len(indices)) % folds
    metrics, predictions = [], []
    for fold in range(folds):
        train = frame[assignments != fold].copy()
        test = frame[assignments == fold].copy()
        candidates = metadata(test)  # Personal feedback removed before any ranking.
        relevant = set(test.loc[test.my_rating.ge(threshold), 'external_api_id'])
        rankings = {'A_public': rank_public(candidates, train, prior_votes=prior_votes),
                    'B_genres': ContentProfile.fit(train, threshold=threshold).rank(candidates, train),
                    'B_genres_cast': ContentProfile.fit(train, threshold=threshold, cast_weight=cast_weight).rank(candidates, train)}
        for model, ranking in rankings.items():
            values = ranking_metrics(ranking.external_api_id.tolist(), relevant, k)
            metrics.append({'fold': fold + 1, 'model': model, 'train_n': len(train),
                            'test_n': len(test), 'relevant_n': len(relevant),
                            'random_expected_precision': len(relevant) / len(test), **values})
            predictions.extend({'fold': fold + 1, 'model': model, 'rank': rank,
                                'external_api_id': row.external_api_id, 'score': row.score,
                                'relevant': row.external_api_id in relevant}
                               for rank, row in enumerate(ranking.itertuples(), 1))
    return pd.DataFrame(metrics), pd.DataFrame(predictions)
