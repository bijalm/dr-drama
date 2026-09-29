"""Ranking, leakage boundaries, sparse features, and metric correctness."""

import json
import unittest

import numpy as np
import pandas as pd

from dr_drama.models.baseline import ContentProfile, metadata, rank_public
from dr_drama.models.evaluation import evaluate_baselines, ranking_metrics


def item(identifier, genres=('Comedy',), cast=('Actor A',), rating=8., status='completed', votes=1000):
    return {'external_api_id': str(identifier), 'canonical_title': f'Synthetic {identifier}',
            'genres': json.dumps(genres), 'main_cast': json.dumps(cast), 'my_rating': rating,
            'status': status, 'public_rating': 8., 'public_vote_count': votes,
            'popularity': 10, 'popularity_metric': 'rank'}


class BaselineTests(unittest.TestCase):
    def test_excludes_all_exposure_statuses(self):
        history = pd.DataFrame([item(i, status=s) for i, s in enumerate(
            ['completed', 'dropped', 'unfinished', 'watching'])])
        candidates = pd.concat([history, pd.DataFrame([item(9)])], ignore_index=True)
        for result in [rank_public(candidates, history), ContentProfile.fit(history).rank(candidates, history)]:
            self.assertEqual(result.external_api_id.tolist(), ['9'])

    def test_profile_uses_only_completed_high_ratings(self):
        history = pd.DataFrame([item(1), item(2, rating=7.9), item(3, status='dropped')])
        self.assertEqual(ContentProfile.fit(history).positive_ids, ('1',))

    def test_cosine_and_unseen_labels(self):
        profile = ContentProfile.fit(pd.DataFrame([item(1)]))
        history = pd.DataFrame([item(1)])
        candidates = pd.DataFrame([item(2, genres=('Comedy', 'Unknown')),
                                   item(3, genres=('Unknown',)), item(4, genres=())])
        result = profile.rank(candidates, history).set_index('external_api_id')
        self.assertAlmostEqual(result.loc['2', 'score'], 1 / np.sqrt(2))
        self.assertEqual(result.loc['3', 'score'], 0)
        self.assertEqual(result.loc['4', 'score'], 0)
        self.assertEqual(profile.vocabularies['genres'], ['comedy'])

    def test_duplicate_labels_do_not_inflate_score(self):
        history = pd.DataFrame([item(1)])
        candidates = pd.DataFrame([item(2, genres=('Comedy', ' comedy ', 'Comedy'))])
        self.assertAlmostEqual(ContentProfile.fit(history).rank(candidates, history).score.iloc[0], 1.)

    def test_candidate_feedback_cannot_change_scores(self):
        history = pd.DataFrame([item(1)])
        candidates = pd.DataFrame([item(2), item(3, genres=('Drama',))])
        changed = candidates.assign(my_rating=[1, 10], favorite=['no', 'yes'],
                                    personal_notes=['avoid', 'love'], status='dropped')
        profile = ContentProfile.fit(history)
        pd.testing.assert_frame_equal(profile.rank(candidates, history), profile.rank(changed, history))
        pd.testing.assert_frame_equal(rank_public(candidates, history), rank_public(changed, history))
        self.assertNotIn('my_rating', metadata(candidates))

    def test_vote_shrinkage_and_missing_support(self):
        history = pd.DataFrame([item(1)])
        candidates = pd.DataFrame([item(2, votes=1), item(3, votes=10000), item(4, votes=np.nan)])
        candidates['public_rating'] = [10., 8., 10.]
        result = rank_public(candidates, history, prior=7).set_index('external_api_id')
        self.assertGreater(result.loc['3', 'score'], result.loc['2', 'score'])
        self.assertEqual(result.loc['4', 'score'], 7.)
        self.assertTrue(result.loc['4', 'prior_only'])

    def test_popularity_is_ascending_rank(self):
        history = pd.DataFrame([item(1)])
        candidates = pd.DataFrame([item(2), item(3)])
        candidates['popularity'] = [100, 1]
        self.assertEqual(rank_public(candidates, history).external_api_id.tolist(), ['3', '2'])

    def test_no_positive_profile_falls_back_explicitly(self):
        history = pd.DataFrame([item(1, rating=3)])
        result = ContentProfile.fit(history).rank(pd.DataFrame([item(2)]), history)
        self.assertEqual(result.score_kind.iloc[0], 'shrunk_public_rating')
        self.assertTrue(result.fallback_reason.iloc[0])

    def test_duplicate_ids_rejected_and_empty_candidates_supported(self):
        history = pd.DataFrame([item(1)])
        with self.assertRaises(ValueError):
            metadata(pd.concat([history, history]))
        self.assertTrue(ContentProfile.fit(history).rank(history, history).empty)

    def test_metrics_known_order_and_short_list(self):
        result = ranking_metrics(['a', 'b', 'c'], {'a', 'c'}, k=2)
        self.assertEqual(result['precision_at_k'], .5)
        self.assertEqual(result['recall_at_k'], .5)
        self.assertAlmostEqual(result['ndcg_at_k'], 1 / (1 + 1 / np.log2(3)))
        self.assertEqual(ranking_metrics(['a'], {'a'}, 5)['precision_at_k'], 1.)

    def test_evaluation_reproducible_and_every_item_held_out_once(self):
        history = pd.DataFrame([item(i, rating=9 if i % 2 else 4) for i in range(20)])
        metrics, predictions = evaluate_baselines(history)
        again, _ = evaluate_baselines(history)
        pd.testing.assert_frame_equal(metrics, again)
        for _, rows in predictions.groupby('model'):
            self.assertEqual(len(rows), len(history))
            self.assertEqual(rows.external_api_id.nunique(), len(history))
        self.assertTrue(metrics.precision_at_k.between(0, 1).all())


if __name__ == '__main__':
    unittest.main()
