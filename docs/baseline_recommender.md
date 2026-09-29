# Baseline ranking contract

Candidate rows use the existing MDL metadata schema, with unique string `external_api_id` values. JSON string arrays represent genres and cast. Keep provenance and retrieval times with each catalog snapshot. Candidate feedback fields are removed before scoring.

## Public ranking

The score is `(v * R + m * C) / (v + m)`, where `R` is public rating, `v` is vote count, `m=1000` is a fixed prior strength, and `C` is mean available public rating in the training history. A cold-start history without public scores uses 5.5. Missing rating/votes receives the prior and a `prior_only` flag. The history-based prior is selection-biased and is not a population estimate.

Equal scores use ascending MDL popularity rank when `popularity_metric=rank`, then ID. Popularity is not a cardinal quality feature. The score is neither a personal-rating estimate nor a probability.

## Content ranking

Genres are the default feature. Vocabulary is fit on training metadata; the profile averages unit vectors from completed training items rated at least 8, then normalizes the average. Candidate cosine similarity measures overlap. Unknown labels contribute zero overlap but count in candidate length. Duplicate/case/whitespace variants of labels are normalized in memory without editing data.

An exploratory variant combines 0.8 genre cosine and 0.2 main-cast cosine. Cast aliases are not resolved to person IDs. Missing components contribute zero; the weights are not automatically redistributed. Year, episode count, public score, personal notes and outcome flags are not content features. Ties use IDs. All history IDs, including incomplete and dropped records, are excluded.

With no usable liked-item profile, content ranking explicitly falls back to public ranking and returns `score_kind=shrunk_public_rating` and a reason. Clients must display the returned score kind and must not label fallback scores as similarity or probabilities. Overlapping attributes explain score construction, not causation.

## Evaluation

Default settings: five stratified folds, seed 42, k=5, completed rated records, relevance defined as rating >=8. Profiles and public priors are refit per fold. Both methods receive identical held-out metadata stripped of feedback. Metrics use binary relevance; effective k is capped at available candidates, and recall/NDCG are undefined when there are no relevant items.

Report every fold and mean Precision@k, Recall@k, NDCG@k. Random expected precision is the relevant fraction of each held-out pool. These are retrospective development results, not a final test after model selection. Training folds overlap; their spread is not a confidence interval. Current public metrics, franchise overlap, selection bias and unavailable viewing dates limit interpretation.

## Catalog and artifacts

`python -m dr_drama.data.candidate_catalog` filters cached MDL details into a separate provisional catalog and writes an exclusion report. It retains earlier-year Korean multi-episode entries with complete ranking metadata and a usable synopsis, excluding history IDs. Missing media type remains provisional. This restricted, search-derived catalog is unsuitable for claims of comprehensive discovery.

Personal notebooks and outputs are ignored. The baseline notebook records dataset/code hashes, library versions and settings alongside fold metrics, held-out rankings and candidate suggestions. Original history and cached responses are not modified. No network or agent dependency is required for ranking or evaluation.
