"""Rating regression validation, leakage boundaries and out-of-fold accounting."""

import unittest

import numpy as np
import pandas as pd
from sklearn.exceptions import NotFittedError

from dr_drama.models.rating_prediction import (
    RatingFeatures, completed_history, evaluate_rating_model, fit_rating_model, predict_unwatched,
)


def fixture(n=24):
    return pd.DataFrame([{
        'external_api_id': f'{i:03}', 'canonical_title': f'Synthetic {i}',
        'genres': '["Comedy", "Drama"]' if i % 2 else '["Thriller"]',
        'public_rating': 6 + (i % 7) * .5, 'my_rating': float(3 + i % 8),
        'status': 'completed',
    } for i in range(n)])


class RatingPredictionTests(unittest.TestCase):
    def test_transformer_only_learns_training_vocabulary_and_statistics(self):
        train = fixture(2).assign(public_rating=[6., 8.])
        transform = RatingFeatures().fit(train)
        test = fixture(1).assign(genres='["Unseen"]', public_rating=10.)
        matrix = transform.transform(test)
        self.assertNotIn('unseen', transform.genres_)
        np.testing.assert_array_equal(matrix[0, :-1], 0)
        self.assertEqual(matrix[0, -1], 3.)
        self.assertEqual(transform.public_mean_, 7.)
        self.assertEqual(transform.public_scale_, 1.)

    def test_missing_public_score_uses_training_median(self):
        transform = RatingFeatures().fit(fixture(3).assign(public_rating=[6., 8., np.nan]))
        transformed = transform.transform(fixture(1).assign(public_rating=np.nan))
        self.assertEqual(transform.public_median_, 7.)
        self.assertAlmostEqual(transformed[0, -1], 0.)
        all_missing = RatingFeatures().fit(fixture(3).assign(public_rating=np.nan, genres=''))
        self.assertEqual(all_missing.public_median_, 5.5)
        self.assertTrue(np.isfinite(all_missing.transform(fixture(1))).all())

    def test_unfitted_transformer_and_malformed_features_fail(self):
        with self.assertRaises(NotFittedError):
            RatingFeatures().transform(fixture())
        with self.assertRaises(ValueError):
            RatingFeatures().fit(fixture().assign(genres='[4]'))
        with self.assertRaises(ValueError):
            RatingFeatures().fit(fixture().assign(public_rating=np.inf))

    def test_candidate_outcome_columns_do_not_affect_predictions(self):
        train = fixture()
        model = fit_rating_model(train, alphas=(1.,), inner_folds=2)
        candidate = fixture(2).assign(external_api_id=['new1', 'new2'])
        original = predict_unwatched(model, candidate, train)
        changed = candidate.assign(my_rating=[1., 10.], status='dropped', favorite='yes', personal_notes='private')
        pd.testing.assert_frame_equal(original, predict_unwatched(model, changed, train))
        self.assertNotIn('personal_notes', original)

    def test_all_seen_statuses_excluded(self):
        train = fixture()
        model = fit_rating_model(train, alphas=(1.,), inner_folds=2)
        history = train.copy()
        history.loc[:3, 'status'] = ['completed', 'watching', 'dropped', 'unfinished']
        result = predict_unwatched(model, history, history)
        self.assertTrue(result.empty)

    def test_training_eligibility_and_input_preservation(self):
        history = fixture()
        history.loc[0, 'status'] = 'dropped'
        history.loc[1, 'my_rating'] = np.nan
        original = history.copy(deep=True)
        self.assertEqual(len(completed_history(history)), len(history) - 2)
        pd.testing.assert_frame_equal(history, original)
        with self.assertRaises(ValueError):
            completed_history(pd.concat([history, history]))
        with self.assertRaises(ValueError):
            completed_history(fixture().assign(my_rating=6.75))

    def test_out_of_fold_predictions_and_mean_baseline(self):
        history = fixture()
        metrics, predictions, tuning = evaluate_rating_model(history, outer_folds=3, inner_folds=2, alphas=(1., 10.))
        self.assertEqual(len(predictions), len(history))
        self.assertEqual(predictions.external_api_id.nunique(), len(history))
        for fold, rows in predictions.groupby('fold'):
            training = history[~history.external_api_id.isin(rows.external_api_id)]
            np.testing.assert_allclose(rows.mean_prediction, training.my_rating.mean())
            self.assertAlmostEqual(metrics.query('fold == @fold and model == "ridge"').mae.iloc[0], rows.ridge_absolute_error.mean())
        self.assertEqual(len(tuning), 6)

    def test_outer_test_labels_cannot_change_own_predictions_or_alpha(self):
        history = fixture()
        m1, p1, _ = evaluate_rating_model(history, outer_folds=3, inner_folds=2, alphas=(1., 10.))
        ids = p1.loc[p1.fold.eq(1), 'external_api_id']
        changed = history.copy()
        changed.loc[changed.external_api_id.isin(ids), 'my_rating'] = 1.
        m2, p2, _ = evaluate_rating_model(changed, outer_folds=3, inner_folds=2, alphas=(1., 10.))
        np.testing.assert_allclose(p1.loc[p1.fold.eq(1), 'ridge_prediction'], p2.loc[p2.fold.eq(1), 'ridge_prediction'])
        self.assertEqual(m1.query('fold == 1 and model == "ridge"').selected_alpha.iloc[0],
                         m2.query('fold == 1 and model == "ridge"').selected_alpha.iloc[0])

    def test_reproducibility(self):
        first = evaluate_rating_model(fixture(), outer_folds=3, inner_folds=2, alphas=(1.,))
        second = evaluate_rating_model(fixture(), outer_folds=3, inner_folds=2, alphas=(1.,))
        for a, b in zip(first, second):
            pd.testing.assert_frame_equal(a, b)


if __name__ == '__main__':
    unittest.main()
