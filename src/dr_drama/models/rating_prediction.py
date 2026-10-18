"""Training-only preprocessing and nested evaluation for personal-rating Ridge."""

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.dummy import DummyRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.model_selection import GridSearchCV, KFold
from sklearn.pipeline import Pipeline
from sklearn.utils.validation import check_is_fitted

from dr_drama.models.baseline import labels


ALPHAS = (0.1, 1.0, 10.0, 100.0)
FEATURE_COLUMNS = ['genres', 'public_rating']


def feature_inputs(frame: pd.DataFrame) -> pd.DataFrame:
    """Select metadata only, validate observed scores and preserve missing values."""
    missing = set(FEATURE_COLUMNS) - set(frame)
    if missing:
        raise ValueError(f'Missing rating features: {sorted(missing)}')
    result = frame[FEATURE_COLUMNS].copy()
    result['public_rating'] = pd.to_numeric(result.public_rating.replace('', np.nan), errors='raise')
    observed = result.public_rating.dropna()
    if not np.isfinite(observed).all() or not observed.between(0, 10, inclusive='right').all():
        raise ValueError('Public ratings must be finite and greater than 0 through 10')
    result.genres.map(labels)  # Validate arrays without changing their source representation.
    return result


def _check_ids(frame: pd.DataFrame) -> None:
    ids = frame.external_api_id
    if ids.isna().any() or ids.astype(str).str.strip().eq('').any() or ids.astype(str).duplicated().any():
        raise ValueError('Unique nonempty drama IDs are required')


def completed_history(history: pd.DataFrame) -> pd.DataFrame:
    """Return validated completed ratings in stable ID order; leave input unchanged."""
    _check_ids(history)
    if not history.status.isin(['completed', 'dropped', 'unfinished', 'watching']).all():
        raise ValueError('Unknown viewing status')
    ratings = pd.to_numeric(history.my_rating.replace('', np.nan), errors='raise')
    observed = ratings.dropna()
    if not observed.between(1, 10).all() or not np.isclose(observed * 10, np.round(observed * 10), rtol=0, atol=1e-9).all():
        raise ValueError('Personal ratings must be 1–10 in 0.1 increments')
    result = history.assign(my_rating=ratings, external_api_id=history.external_api_id.astype(str))
    result = result[result.status.eq('completed') & result.my_rating.notna()].copy()
    feature_inputs(result)
    return result.sort_values('external_api_id').reset_index(drop=True)


class RatingFeatures(TransformerMixin, BaseEstimator):
    """Binary genre indicators plus training-standardized, median-imputed public score.

    Missing genres have no memberships; unknown labels are ignored. If every
    training public score is missing, use fixed 5.5 and unit scale. Genre columns
    stay binary; only the continuous public score is standardized. No labels or
    personal fields are read, even when supplied alongside metadata.
    """

    def fit(self, X: pd.DataFrame, y=None):
        features = feature_inputs(X)
        if features.empty:
            raise ValueError('Cannot fit features on empty training data')
        self.genres_ = sorted(set().union(*features.genres.map(labels)))
        scores = features.public_rating
        self.public_median_ = float(scores.median()) if scores.notna().any() else 5.5
        filled = scores.fillna(self.public_median_).to_numpy(dtype=float)
        self.public_mean_ = float(filled.mean())
        self.public_scale_ = float(filled.std()) or 1.0
        return self

    def transform(self, X: pd.DataFrame) -> np.ndarray:
        check_is_fitted(self, 'genres_')
        features = feature_inputs(X)
        matrix = np.zeros((len(features), len(self.genres_) + 1))
        for row, entries in enumerate(features.genres.map(labels)):
            matrix[row, :-1] = [name in entries for name in self.genres_]
        matrix[:, -1] = (features.public_rating.fillna(self.public_median_) - self.public_mean_) / self.public_scale_
        return matrix

    def get_feature_names_out(self, input_features=None) -> np.ndarray:
        check_is_fitted(self, 'genres_')
        return np.array([f'genre:{name}' for name in self.genres_] + ['public_rating_standardized'], dtype=object)


def fit_rating_model(history: pd.DataFrame, *, alphas=ALPHAS,
                     inner_folds: int = 3, seed: int = 42) -> GridSearchCV:
    """Choose alpha by inner-fold MAE, then refit the complete pipeline on input history."""
    frame = completed_history(history)
    if inner_folds < 2 or len(frame) < inner_folds * 2:
        raise ValueError('Need at least two records per inner fold')
    if not alphas or any(not np.isfinite(a) or a <= 0 for a in alphas):
        raise ValueError('Alpha candidates must be positive and finite')
    pipeline = Pipeline([('features', RatingFeatures()), ('ridge', Ridge(solver='svd'))])
    search = GridSearchCV(pipeline, {'ridge__alpha': list(alphas)},
                          scoring='neg_mean_absolute_error',
                          cv=KFold(inner_folds, shuffle=True, random_state=seed),
                          refit=True, n_jobs=1, error_score='raise')
    search.fit(feature_inputs(frame), frame.my_rating.to_numpy())
    return search


def evaluate_rating_model(history: pd.DataFrame, *, outer_folds: int = 5,
                          inner_folds: int = 3, seed: int = 42,
                          alphas=ALPHAS) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Compare raw out-of-fold Ridge predictions with each training fold's mean.

    Returns fold metrics, one prediction row per eligible drama, and inner search
    scores. Outer test outcomes never choose alpha or preprocessing statistics.
    Predictions are not clipped for either tuning or primary evaluation.
    """
    frame = completed_history(history)
    if outer_folds < 2 or len(frame) < 2 * outer_folds:
        raise ValueError('Need at least two records per outer fold')
    metrics, predictions, tuning = [], [], []
    outer = KFold(outer_folds, shuffle=True, random_state=seed)
    for fold, (train_index, test_index) in enumerate(outer.split(frame), 1):
        train, test = frame.iloc[train_index], frame.iloc[test_index]
        search = fit_rating_model(train, alphas=alphas, inner_folds=inner_folds, seed=seed + fold)
        actual = test.my_rating.to_numpy()
        mean_model = DummyRegressor(strategy='mean').fit(np.zeros((len(train), 1)), train.my_rating)
        mean_pred = mean_model.predict(np.zeros((len(test), 1)))
        ridge_pred = search.predict(feature_inputs(test))
        for name, predicted in [('mean', mean_pred), ('ridge', ridge_pred)]:
            metrics.append({'fold': fold, 'model': name, 'train_n': len(train), 'test_n': len(test),
                            'mae': mean_absolute_error(actual, predicted),
                            'rmse': float(np.sqrt(mean_squared_error(actual, predicted))),
                            'selected_alpha': search.best_params_['ridge__alpha'] if name == 'ridge' else np.nan})
        for row, mean, ridge in zip(test.itertuples(), mean_pred, ridge_pred):
            predictions.append({'external_api_id': row.external_api_id,
                                'canonical_title': getattr(row, 'canonical_title', row.external_api_id),
                                'fold': fold, 'actual_rating': row.my_rating,
                                'mean_prediction': mean, 'ridge_prediction': ridge,
                                'mean_absolute_error': abs(row.my_rating - mean),
                                'ridge_absolute_error': abs(row.my_rating - ridge)})
        for params, score in zip(search.cv_results_['params'], search.cv_results_['mean_test_score']):
            tuning.append({'outer_fold': fold, 'alpha': params['ridge__alpha'], 'inner_mean_mae': -score})
    return pd.DataFrame(metrics), pd.DataFrame(predictions), pd.DataFrame(tuning)


def predict_unwatched(model: GridSearchCV, candidates: pd.DataFrame,
                      history: pd.DataFrame) -> pd.DataFrame:
    """Predict only IDs absent from all recorded history; expose clipping and coverage."""
    _check_ids(candidates)
    eligible = candidates[~candidates.external_api_id.astype(str).isin(history.external_api_id.astype(str))].copy()
    result = eligible.reindex(columns=['external_api_id', 'canonical_title', 'source_url']).copy()
    inputs = feature_inputs(eligible)
    raw = model.predict(inputs) if len(inputs) else np.array([])
    result['predicted_rating_raw'] = raw
    result['predicted_rating_display'] = np.clip(raw, 1, 10)
    result['display_clipped'] = (raw < 1) | (raw > 10)
    result['public_rating_imputed'] = inputs.public_rating.isna()
    vocabulary = set(model.best_estimator_.named_steps['features'].genres_)
    result['unknown_genre_count'] = inputs.genres.map(lambda x: len(labels(x) - vocabulary))
    result['missing_genres'] = inputs.genres.map(lambda x: not labels(x))
    return result.sort_values(['predicted_rating_raw', 'external_api_id'], ascending=[False, True]).reset_index(drop=True)
