# Personal-rating prediction contract

## Target and inputs

Predict numerical personal rating on a 1–10 scale among completed, rated dramas. Unfinished, dropped, watching and unrated records are excluded from supervised fitting, but all history IDs are excluded from candidate suggestions. The model does not predict completion or dropping.

Inputs are JSON-array genres and public rating only. IDs are used for identity and exclusion, never as predictors. Candidate rating, favorite, rewatch, notes, cast, release year and episode count do not enter scoring.

## Preprocessing and model

`RatingFeatures` learns a genre vocabulary from training metadata. Genres use binary memberships; whitespace, case and repeated labels are normalized in memory. Missing/unknown memberships activate no known indicators. Candidate outputs flag unknown genres and missing genre lists.

Missing public scores use the training median (5.5 if all are missing). Public rating is standardized using the imputed training mean and population standard deviation; a constant column uses unit scale. Genre indicators remain unscaled. The transformer and Ridge estimator are fitted together in a scikit-learn pipeline.

Ridge minimizes squared residuals plus alpha times the squared coefficient norm, with an unpenalized intercept and deterministic SVD solver. Alpha candidates are fixed at `[0.1, 1, 10, 100]`. Coefficients describe conditional fitted associations, not causal preference effects.

## Evaluation

Five shuffled outer KFold splits (seed 42) compare Ridge against `DummyRegressor(strategy="mean")` on identical held-out records. Each outer training set runs three inner shuffled folds (seed 42 + outer fold number) to select alpha by mean absolute error. Preprocessing is refitted in each inner fit and the selected pipeline is refitted on the complete outer training set before prediction.

Report pooled out-of-fold MAE and RMSE, individual fold metrics, selected alphas and inner search scores. Pooled metrics weight each drama equally. Predictions are raw and unclipped for tuning and evaluation; no rounding is applied before scoring. Rating errors are not classification accuracy or ranking Precision@k.

This is a retrospective development experiment using previously explored history. Nested validation separates alpha selection from outer assessment, but does not remove prior feature-selection influence, selection bias, franchise overlap or temporal hindsight in public metrics. Fold variability is not a confidence interval. A public-rating-only regression ablation has not been performed, so any improvement cannot be attributed specifically to genre features.

## Final refit and outputs

After evaluation, inner validation on all eligible history selects alpha for a separate full-history refit (seed 42). Its coefficients and optional candidate estimates are not performance evidence. `predict_unwatched` returns raw predicted ratings and separate display values clipped to 1–10, with a clipping flag. Estimates are conditional on completed viewing and are not calibrated probabilities or guaranteed ratings.

The personal notebook saves private fold membership, held-out predictions, tuning scores, final coefficients, optional candidate estimates and a manifest of settings, versions and source/code hashes under `data/processed/rating_prediction/`. Original data remains unchanged. Public notebooks contain no saved personal results. No deployed model service or serialized serving artifact is provided.

## Execution

Install the declared project dependencies, including scikit-learn. Run the local personal notebook or copy [the public workflow](../notebooks/public/03_rating_prediction.ipynb) into ignored `notebooks/local/` and select the project kernel. The local enriched history is required; a candidate catalog is optional. No network requests occur during fitting or evaluation.

References: [scikit-learn Ridge](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.Ridge.html), [nested cross-validation](https://scikit-learn.org/stable/auto_examples/model_selection/plot_nested_cross_validation_iris.html).
