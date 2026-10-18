# Dr Drama

Dr Drama is a personalized K-drama recommendation application under development.

## Problem

Public ratings summarize audience opinion but do not describe an individual's preferences. Dr Drama will combine viewing history and personal ratings with drama metadata to recommend unwatched titles and, when supported by evaluation, estimate enjoyment.

## Current phase

See the [data science development report](docs/data_science_report.md) for pipeline stages, implemented methods, evaluation scope and outstanding work.

Phase 2: recommendation baselines and retrospective evaluation. The Python package provides metadata retrieval, reproducible import and analysis, a vote-adjusted public-rating baseline, and content-based ranking. Local, Git-ignored notebooks analyze personal snapshots and compare ranking metrics without network requests.

Metadata lookup and confirmed CSV saving are available. Existing Excel watch history is imported through a reproducible cleaning command. An exploratory Ridge model predicts numerical personal ratings and is evaluated against a training-mean baseline. Supabase, enjoyment-probability prediction, probability calibration, MCP tools, RAG, agents, and a web interface remain planned.

## Planned architecture

- **Metadata:** a configurable adapter for an unofficial MyDramaList API, with validation and source timestamps. Availability and field coverage must be checked before ingestion. See the [provider project](https://github.com/B1PL0B/MyDramaList-Unofficial-API).
- **Storage:** Supabase PostgreSQL, separating drama metadata from user ratings, preferences, and history. Database changes will use versioned migrations.
- **Analysis:** Python modules and notebooks operating on reproducible local snapshots.
- **Recommendations:** filtering and content-based baselines, followed by models evaluated on withheld outcomes. Match scores will remain distinct from calibrated probabilities.
- **Agent:** one orchestration agent calling bounded application tools through MCP. RAG will retrieve supporting evidence for explanations; model code will produce predictions.
- **Application:** a later web interface with user-scoped access to personal records.

## Setup

Use Python 3.11 or newer. Run commands from the repository root.

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[notebook]"
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m jupyterlab
```

### macOS / Linux

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[notebook]'
cp .env.example .env
.venv/bin/python -m jupyterlab
```

If pip reports a certificate verification error on Windows and `uv` is available, use the system certificate store:

```powershell
uv --native-tls pip install --python .venv/Scripts/python.exe -e ".[notebook]"
```

Open `notebooks/01_initial_eda.ipynb` using the environment's Python kernel. Initial EDA requires no API key or database connection. Metadata CLI settings are described below; the notebook makes no network connection. DATABASE_URL remains reserved for the planned database integration.

The personal EDA notebook reads `data/processed/watch_history_enriched.csv` and reports descriptive rating, genre, cast and completion patterns. Excel import produces a cleaned dataset, and metadata enrichment produces the enriched snapshot. The initial collection file is `data/raw/watch_history.csv`; see [the CSV contract](docs/watch_history_schema.md). Keep missing ratings blank and use the 1–10 scale with at most one decimal place.

Dependencies are declared in `pyproject.toml`. JupyterLab provides the notebook interface. HTTPX is the metadata HTTP client. Scikit-learn provides Ridge regression, pipelines and nested cross-validation. Database drivers and agent libraries are not required yet.

## Checks

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

On macOS/Linux use `.venv/bin/python` in place of the Windows executable. Tests run offline.

## Repository layout

```text
data/raw/              Original local inputs
data/processed/        Derived local datasets
notebooks/             Initial EDA and reproducible analyses
src/dr_drama/data/     Ingestion, validation, persistence
src/dr_drama/analysis/ Reusable analysis code
src/dr_drama/models/   Baseline ranking and retrospective evaluation
src/dr_drama/agents/   Future orchestration
src/dr_drama/tools/    Future application tools and integrations
tests/                Automated behavior checks
```

## Data and configuration

Raw and processed datasets, local environments, credentials, and private notes are ignored by Git. Retain original inputs unchanged and write derived datasets separately. The personal `notebooks/01_initial_eda.ipynb` is ignored because it contains private findings and explanatory commentary. Any separately published notebook must have personal data and findings removed, not merely its outputs cleared. Use `notebooks/local/` for notebooks containing private inputs or saved results.

Supabase and metadata credentials must remain in environment variables. Do not expose privileged database credentials in browser code. Public datasets or examples require a separate review of provenance and permission to distribute.

## Roadmap

1. Repository foundation and initial EDA scaffold — available.
2. Metadata retrieval and confirmed CSV updates — available; database schema and dedicated personal-data entry interface — planned.
3. Provisional starter catalog and evaluated recommendation baselines — available; broader catalog acquisition remains pending.
4. Exploratory personal-rating prediction — available; enjoyment probabilities and calibration — planned.
5. Evidence retrieval, MCP tools, and orchestration agent.
6. Web interface, access controls, and feedback collection.

## Metadata lookup

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m dr_drama.tools.metadata_cli "Run On"
```

Omit the title to enter it at a prompt. Select a result by number, inspect its details and source link, then enter `y` only if the match is correct and should be saved. Enter a viewing status for a new record; an existing record retains its status and all other personal fields. Press Enter at selection or answer anything except `y` at confirmation to cancel.

The CLI uses `.env` and defaults to `data/raw/watch_history.csv`. `--env-file` and `--dataset` accept alternate paths. Run from the repository root unless supplying explicit paths.

- `MDL_API_BASE_URL`: temporary unofficial API deployment URL.
- `MDL_API_KEY`: optional credential, left empty for the currently unauthenticated deployment.
- `MDL_API_KEY_HEADER`: exact authentication header name required by your deployment, only if a key is configured. No official authentication scheme is assumed. The value is sent verbatim; never use an MDL account password here.

The adapter is temporary. Replace it with the official MyDramaList API when official developer access becomes available, preserving the normalized field contract. The current provider is not affiliated with MyDramaList; its documentation requests your own deployment for ongoing use.

Search results can include movies, specials, and non-Korean titles. The provider does not consistently expose media type, so users must verify the selected record before saving. Original language remains missing when not explicitly provided; country is not used to infer it. The country/language mappings currently cover common supported values; unfamiliar labels remain missing with a warning and are retained in raw response snapshots.

Requests have a 30-second timeout, at least one second between starts, and up to three attempts for transient network/HTTP failures. `Retry-After` is respected for short waits; delays over 30 seconds are reported for a later retry. A failed cast lookup permits an explicitly flagged partial preview.

Normalization maps the provider's rating to `public_rating`, score vote count to `public_vote_count`, and popularity rank to `popularity` with `popularity_metric=rank`. It retains up to five actors labeled Main Role in provider order. Missing data is represented by Python `None` and empty CSV cells. No language, cast member, or personal rating is invented.

Saving matches by source/ID or an exact case-insensitive entered title. Duplicate rows and conflicting IDs are rejected. Refreshes preserve personal fields and previously stored metadata where the new response is missing a value; a refreshed row may therefore include older values. The retrieval timestamp describes the latest request, not the age of every retained field. Timestamped raw response snapshots are saved under `data/raw/api_responses/`. CSV replacement is atomic and assumes a single local writer. Close spreadsheet applications that lock the CSV before saving.

Saved responses, local settings, and watch history are ignored by Git. Tests use mocked HTTP responses and temporary CSVs; live requests are not part of the offline test suite.

## Import existing Excel history

```powershell
.\.venv\Scripts\python.exe -m dr_drama.data.import_excel "path/to/watch-history.xlsx"
```

The command inspects all sheets and imports populated sheets with a recognized title column. It preserves the original workbook and saves a content-hashed byte-for-byte snapshot under `data/raw/excel/`. It writes `data/processed/watch_history_clean.csv` plus Markdown and JSON quality reports alongside it. These outputs are ignored by Git.

Known headers map to the watch-history schema; unknown columns are retained with a `source_` prefix. Header collisions require review. Blank worksheet rows are skipped and counted. Source sheet and Excel row are retained as provenance columns. Categories are normalized using explicit mappings. Invalid numbers are reported, represented as missing in typed columns, and retained in `original_<field>` columns. Unknown categories are preserved and flagged. Titles and personal notes are not spell-corrected or stripped. Duplicate title groups are reported without removing rows.

External metadata already supplied in a workbook is retained; missing metadata stays empty. Lists use JSON arrays; plain-text lists accept commas, semicolons, or pipes as delimiters. Review lists containing literal delimiter characters. Numeric types are applied in Python and recorded in the report; CSV itself does not store type information. Formula text is inspected but not executed. No API requests are made during import.

## Enrich imported history

```powershell
.\.venv\Scripts\python.exe -m dr_drama.data.enrich_mdl
```

Creates a separate enriched dataset and review files without modifying the cleaned input. Successful API responses are cached so interrupted work can resume. See [metadata enrichment](docs/metadata_enrichment.md) for matching rules, provisional TV classification, field provenance, discrepancy handling, and cache behavior. No personal ratings or notes are sent to the metadata provider.

## Descriptive analysis

Public analysis workflows are available in [notebooks/public](notebooks/public/README.md): watch-history exploration and recommendation baseline comparison. They document methods, outputs and limitations without saved personal findings. Copy them to `notebooks/local/` before running against local datasets.

`src/dr_drama/analysis/eda.py` provides schema-aware loading, separate genre/cast membership expansion, group summaries with explicit denominators, and descriptive correlations. It performs no network requests or model fitting. The personal local notebook covers viewing counts, ratings, genre and actor summaries, completion/drop patterns, favorites, and limitations. Original datasets are not modified.

## Recommendation baselines

`src/dr_drama/models/baseline.py` implements vote-adjusted public quality and content similarity from completed, highly rated history. Every recorded ID is excluded from recommendation results regardless of viewing status. Candidate scoring uses an explicit metadata whitelist, never personal feedback. Scores are not calibrated probabilities or predicted personal ratings.

`src/dr_drama/models/evaluation.py` fits profiles inside fixed stratified folds and reports Precision@k, Recall@k and NDCG@k on held-out completed dramas. It compares public quality, genres, and a fixed genre-plus-cast variant. This retrospective comparison does not reproduce historical public ratings or establish prospective performance. See [baseline behavior and evaluation](docs/baseline_recommender.md).

A provisional catalog can be built from existing local MDL detail caches:

```powershell
.venv/Scripts/python.exe -m dr_drama.data.candidate_catalog
```

The catalog is a search-biased starter set, not a full discovery feed. The command makes no network requests and preserves source history. Review identity, coverage, sequel requirements and availability before relying on suggestions. A fresh clone needs its own local data and caches.

The local `notebooks/02_baseline_recommender.ipynb` presents examples and evaluation, and saves results under `data/processed/baseline/`. Both personal notebooks and their output datasets are ignored by Git and are not distributed with a fresh clone. No additional dependencies are required for these baselines.

## Personal-rating prediction

`src/dr_drama/models/rating_prediction.py` compares a training-mean predictor with Ridge using binary genres and standardized public rating. Five outer folds assess raw out-of-fold predictions; three inner folds select alpha with preprocessing fitted inside each training split. Primary evaluation is MAE in rating points, with RMSE as a secondary measure. Scores are not enjoyment probabilities.

See the [rating prediction contract](docs/rating_prediction.md) and [public workflow](notebooks/public/03_rating_prediction.ipynb). The ignored personal notebook `notebooks/03_rating_prediction.ipynb` includes local results and saves reproducibility artifacts to `data/processed/rating_prediction/`. No new metadata requests are required. Candidate predictions are optional and do not constitute validation on unseen outcomes.
