# Analysis notebooks

| Notebook | Purpose |
|---|---|
| [Watch-history exploration](01_initial_eda.ipynb) | Describes viewing coverage, ratings, genre and cast associations, and completion patterns. |
| [Recommendation baseline comparison](02_baseline_recommender.ipynb) | Compares public-quality and content-based ranking using held-out feedback. |
| [Personal-rating prediction](03_rating_prediction.ipynb) | Compares mean-rating prediction with Ridge using nested cross-validation and held-out rating errors. |

These notebooks document executable analysis workflows. Personal datasets and saved results are not included. They call reusable functions in `src/dr_drama/` and make no network requests.

## Running locally

1. Follow the repository [setup and data preparation instructions](../../README.md).
2. Prepare `data/processed/watch_history_enriched.csv`. The baseline notebook also requires `data/processed/candidate_catalog.csv`.
3. Copy the notebooks into `notebooks/local/`, which is ignored by Git.
4. Select the project's Python kernel and run all cells in order.

The baseline evaluation requires at least five completed ratings on each side of the 8+ threshold under the default five-fold configuration. Sparse or empty groups can limit exploratory plots; inspect dataset coverage before interpreting comparisons.

Keep tracked copies free of personal data, outputs, attachments and dataset-specific findings. Clearing outputs alone is insufficient if personal findings have been added to Markdown. Original personal notebooks remain separate and ignored.
