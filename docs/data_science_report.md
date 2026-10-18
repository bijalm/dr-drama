# Dr Drama: Data Science Development Report

**Current phase:** recommendation baselines and exploratory personal-rating prediction
**Last reviewed:** 2026-10-16

## Project objective

Rank unwatched K-dramas using public metadata and an individual's viewing history. The current research question is whether content-based personalization improves recovery of known preferences compared with public-quality ranking.

The implemented system produces ranked candidates and exploratory numerical personal-rating estimates. Calibrated probabilities of enjoyment remain future work.

## Pipeline status

| Stage | Status | Current deliverable |
|---|---|---|
| Problem definition | Completed for baseline scope | Ranking objective and provisional relevance definition |
| Data collection | Implemented | Excel import and MyDramaList metadata acquisition |
| Cleaning and standardization | Implemented | Reproducible transformations and separate processed datasets |
| Data validation | Implemented; review remains open | Quality reports, identity checks and discrepancy tracking |
| Observation and exploratory analysis | Completed for the initial snapshot | Descriptive statistics, grouped analysis and visualizations |
| Feature engineering | Initial implementation complete | Genre/cast representations and training-only preference profiles |
| Candidate generation | Preliminary | Provisional catalog derived from cached metadata |
| Baseline modeling | Implemented | Public-quality, genre, and genre-plus-cast ranking |
| Offline evaluation | Initial comparison complete | Fixed-fold ranking metrics and experiment records |
| Model selection and optimization | Initial implementation | Nested alpha selection for Ridge; no production-selected model |
| Recommendation scoring | Implemented | Ranked candidates with explicit score types |
| Personal-rating prediction | Exploratory implementation | Ridge versus a training-mean predictor |
| Enjoyment-probability prediction | Not done yet | No classifier or calibration assessment |
| Deployment and monitoring | Not done yet | No serving application or live feedback evaluation |

## 1. Data collection

Personal feedback is imported from an existing Excel watch history. The schema separates user-entered titles, ratings, status, favorites, rewatch preferences and notes from externally sourced drama metadata.

The MyDramaList adapter retrieves identifiers, titles, release year, country, genres, episode counts, public ratings, vote counts, popularity rank, synopsis and main cast where available. The current integration uses a temporary unofficial provider; official API migration remains planned.

Original workbook snapshots and API responses are retained locally. Metadata records include source identifiers, source links and retrieval timestamps. Personal datasets and credentials are excluded from Git.

**Remaining work:** broaden the candidate catalog, improve metadata coverage, and resolve provisional identities. Current collection is based on one user's selected history rather than a representative audience sample.

## 2. Cleaning and standardization

The reusable import pipeline maps source columns to a consistent schema, normalizes known categorical variants, converts numerical fields and serializes multi-value metadata consistently. Personal ratings retain the 1–10 scale with 0.1 increments.

Source files remain unchanged. Cleaned and enriched datasets are written separately. Unrecognized or invalid entries are flagged rather than silently assigned plausible values. Missing information is not treated as zero, dislike or a negative preference.

External enrichment preserves existing spreadsheet values and retains provider alternatives. Field-level provenance and comparison labels distinguish source agreement, missing values and conflicts.

**Implementation:** [Excel import](../src/dr_drama/data/import_excel.py), [metadata enrichment](../src/dr_drama/data/enrich_mdl.py), and [schema contract](watch_history_schema.md).

## 3. Data validation and quality review

The initial audit examined record counts, unique identities, duplicate records, missingness, data types, numerical ranges, categorical values and suspicious entries. Ranking code additionally rejects duplicate candidate IDs and validates relevant public-score fields.

Outstanding limitations include provisional title/media-type matches, incomplete cast coverage, actor-name aliases, missing language information and inconsistent episode-count scope across parts or broadcast formats. Viewing dates are not collected, so release year cannot substitute for viewing order.

**Status:** validation tooling is implemented; complete metadata verification is not done yet.

## 4. Observation and exploratory analysis

The initial analysis covered:

- Viewing-status counts and the distribution of personal ratings.
- The proportion of completed, rated dramas receiving 8+.
- Genre frequency, average ratings, high-rating proportions and drop rates.
- Public-versus-personal rating associations, including a completed-only comparison.
- Release-year and episode-count relationships with ratings and completion.
- Recurring main cast and cast appearances in highly rated dramas.
- Characteristics of favorite and dropped dramas.

Genres and cast are expanded independently, retaining one contribution per drama within each group. Group counts accompany aggregates. Pearson and Spearman correlations are descriptive; no causal or statistical-significance claims are made.

These analyses informed the initial feature scope without establishing that every available attribute improves recommendation quality. Snapshot-specific findings remain in local analysis artifacts.

**Workflow:** [public EDA notebook](../notebooks/public/01_initial_eda.ipynb).
**Implementation:** [descriptive analysis functions](../src/dr_drama/analysis/eda.py).

## 5. Feature engineering

| Signal | Representation or treatment | Current use |
|---|---|---|
| Genres | Separate binary memberships; normalized drama vectors | Primary content feature |
| Main cast | Separate memberships using normalized names | Exploratory content variant |
| Positive preference history | Normalized average of completed training items rated 8+ | Content preference profile |
| Public rating and vote count | Vote-adjusted ranking; standardized public rating for regression | Public-quality baseline and Ridge (votes are not a Ridge feature) |
| Popularity | Ascending MDL rank | Public-score tie-breaker |
| Release year | Retained as metadata | Display and analysis only |
| Episode count | Retained as metadata | Display and analysis only; scope requires review |
| Favorite, rewatch and personal notes | Excluded from candidate scoring | Avoid post-watch outcome leakage |
| Viewing status | Eligibility and watched exclusion | Not a candidate similarity feature |

Feature vocabularies and preference profiles are fitted within training folds. Duplicate labels do not increase weight. Unknown candidate labels provide no overlap but remain in the candidate vector length.

Ridge additionally learns from the full numerical range of completed ratings, using binary genres and training-standardized public score. Its alpha is selected through inner cross-validation.

**Not done yet:** explicit negative-preference profiles, verified actor-ID features, text representations, embeddings, or systematic feature selection.

## 6. Candidate generation

A separate metadata-only catalog supplies items absent from recorded history. The initial catalog filters previously cached search alternatives for basic country, release, episode and metadata eligibility, retaining source evidence and provisional classification.

This catalog supports integration examples but is small and search-biased. Absence from history does not prove that a title has never been watched. Broad discovery, availability checks, sequel prerequisites and comprehensive catalog validation are not implemented.

Live candidate suggestions and offline evaluation use different pools: evaluation ranks held-out history items with known feedback, not the unlabeled starter catalog.

**Implementation:** [candidate catalog builder](../src/dr_drama/data/candidate_catalog.py).

## 7. Models chosen

| Method | Scoring approach | Role |
|---|---|---|
| A: Public quality | `(votes × rating + 1000 × prior) / (votes + 1000)` | Non-personalized reference and cold-start fallback |
| B: Genre similarity | Cosine similarity to the positive genre profile | Initial personalized baseline |
| B: Genres and cast | `0.8 × genre similarity + 0.2 × cast similarity` | Fixed exploratory feature comparison |

The public prior is the mean available public rating among training items. It reflects a selected history, not a population estimate. Missing rating/vote evidence receives the prior with an explicit flag. Content ranking falls back to public ranking when no usable positive profile exists.

These ranking methods were chosen for transparent scoring and compatibility with a single-user dataset. Collaborative filtering has not been implemented because cross-user interaction histories are unavailable. A separate supervised Ridge rating predictor is now implemented; its validation and target are distinct from the ranking experiment.

**Implementation:** [baseline models](../src/dr_drama/models/baseline.py).
**Specification:** [baseline ranking contract](baseline_recommender.md).

## 8. Evaluation and performance measurement

### Ranking evaluation protocol

- Population: completed dramas with observed personal ratings.
- Relevance: personal rating of at least 8/10; this is a provisional experiment definition.
- Split: five stratified folds with random seed 42.
- Comparison: identical held-out candidates for each method, ranked at a cutoff of five.
- Leakage controls: training-only profiles, vocabularies and public priors; candidate feedback removed before scoring.
- Reporting: per-fold metrics, aggregate metrics, configuration, dataset hashes and code hashes in local experiment artifacts.

### Accuracy and ranking metrics

| Measure | Status | Assessment |
|---|---|---|
| Precision@5 | Implemented and evaluated | Relevant items among the first five recommendations |
| Recall@5 | Implemented and evaluated | Share of held-out relevant items recovered |
| NDCG@5 | Implemented and evaluated | Position-sensitive relevance compared with ideal ordering |
| Random expected precision | Implemented | Reference based on candidate relevance prevalence |
| Classification accuracy | Not applicable to current rankers | No liked/disliked classifier is implemented |
| Rating MAE/RMSE | Implemented and evaluated | Raw out-of-fold Ridge and mean-baseline rating errors |
| Brier score, log loss and calibration | Not done yet | No enjoyment probabilities exist |
| Prospective user evaluation | Not done yet | No live recommendation feedback study |

The initial retrospective comparison has been executed. Numerical results and personal findings are retained in ignored local experiment artifacts rather than embedded in this public report. The public notebook documents the executable comparison without saved personal outputs.

This evaluation is a development comparison, not an untouched final test after model selection. Training folds overlap; their variability is not a confidence interval. Current public scores, franchise overlap, selected viewing history and missing viewing dates limit claims about future performance.

**Workflow:** [public baseline notebook](../notebooks/public/02_baseline_recommender.ipynb).
**Implementation:** [ranking evaluation](../src/dr_drama/models/evaluation.py).

### Personal-rating evaluation

Ridge uses five outer shuffled folds and three inner folds to select alpha from a predefined grid by MAE. Genre vocabulary, public-score imputation and scaling are fitted within each training split. A mean-rating predictor uses the same outer training data. Primary performance is pooled out-of-fold MAE; RMSE and per-fold scores provide additional context. No test predictions are clipped or rounded for evaluation.

The final full-history refit is separate from performance assessment. This remains retrospective development evidence; a fresh prospective test and a public-rating-only regression comparison have not been completed. See [rating prediction](rating_prediction.md) and the [public notebook](../notebooks/public/03_rating_prediction.ipynb).

## 9. Recommendation outputs and prediction

Implemented outputs are ordered candidate IDs/titles, ranking scores, score types and shared content attributes. All recorded history IDs are excluded from live suggestions, regardless of viewing status. Shared attributes describe score construction, not a causal explanation of enjoyment.

**Personal-rating prediction: exploratory implementation.** Ridge estimates a numerical personal rating from metadata, conditional on completed viewing. Raw estimates are retained; a separate clipped display value is flagged. Public scores alone remain external inputs, not personal-rating predictions.

**Enjoyment-probability prediction: not done yet.** Similarity scores, including values between zero and one, are not calibrated probabilities. Probability estimation requires a defined target population, sufficient feedback, a supervised model and independent calibration assessment.

## 10. Reproducibility, deployment and next milestones

Reusable Python modules separate acquisition, transformation, analysis and ranking. Automated tests cover important transformations, API behavior, ranking exclusions, score calculations and evaluation boundaries. Public notebooks document methods; personal data, results and learning notes remain local.

| Next milestone | Status |
|---|---|
| Broader reviewed candidate catalog and metadata verification | Not done yet |
| Improved preference features evaluated under a fresh validation plan | Not done yet |
| Final independent or prospective model assessment | Not done yet |
| Supervised numerical rating prediction | Exploratory Ridge implementation complete |
| Enjoyment-probability prediction and calibration | Not done yet |
| Supabase storage integration | Not done yet |
| Recommendation serving, web interface and feedback collection | Not done yet |
| Production monitoring and retraining policy | Not done yet |
| Agent orchestration, MCP integration and RAG | Not done yet; separate future application phase |

Current work establishes an offline recommendation foundation. Production deployment and validated enjoyment prediction remain outside the implemented scope.
