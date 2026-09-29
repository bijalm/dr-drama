# Watch-history CSV contract

The initial local dataset is `data/raw/watch_history.csv`. It contains one row per user's drama/series record, not one row per episode or rewatch. It is excluded from Git. The initial file contains headers only.

## Representation

- UTF-8, comma-delimited CSV with a header row and standard CSV quoting. Quote cells containing commas, quotes, or line breaks; escape embedded double quotes by doubling them.
- `title` and `status` are required for populated rows. External fields can remain empty until a match is confirmed.
- Empty cells mean unknown or not supplied. Do not substitute zero, `no`, or an empty list for missing information.
- Boolean values are lowercase `yes` or `no`.
- Multi-value fields contain JSON arrays of strings within a properly quoted CSV cell. `[]` means a confirmed empty list; a blank cell means unknown. Country values use ISO 3166-1 alpha-2 codes; languages use ISO 639-1 codes when available. Do not infer language from country.
- Preserve external IDs as strings, including leading zeroes. Identify matched records by `(metadata_source, external_api_id)` rather than title alone. Resolve duplicate matches before processing.
- The metadata retrieval timestamp uses ISO 8601 UTC, such as `2026-09-26T12:00:00Z`. Viewing and feedback dates are not collected.
- The metadata CLI enforces CSV headers, source-ID consistency, new-row status, and metadata conversion. Full validation of manually edited personal data is not yet implemented.

## User-provided fields

| Field | Type | Contract |
|---|---|---|
| title | string | Original user-entered title; never overwritten by metadata refresh. |
| my_rating | nullable decimal | 1 through 10 inclusive, with at most one decimal place (increments of 0.1, such as 6.7). |
| status | enum | `completed`, `dropped`, `unfinished`, or `watching`. Unfinished means started but paused/incomplete; dropped means intentionally stopped; watching means actively in progress. |
| favorite | nullable boolean | Explicit favorite designation. |
| would_rewatch | nullable boolean | Explicit willingness to watch again. |
| personal_notes | nullable string | User's free-text observations. |

## External metadata fields

| Field | Type | Contract |
|---|---|---|
| canonical_title | nullable string | Provider's canonical display title. |
| original_title | nullable string | Original-language title, preserving Unicode. |
| release_year | nullable integer | Initial release year; may be derived from the provider's first-air date. |
| country | nullable JSON string array | Production-origin countries, including co-productions. |
| original_language | nullable JSON string array | Original languages if explicitly available. |
| genres | nullable JSON string array | Provider genres. |
| main_cast | nullable JSON string array | Main-role actor names only; not all crew or supporting roles. |
| number_of_episodes | nullable positive integer | Provider series episode total at retrieval time; scope may include multiple seasons. |
| public_rating | nullable decimal | MDL score on its 0–10 scale. No votes/unrated is missing, not zero. Do not combine provider scales without an explicit transformation. |
| public_vote_count | nullable nonnegative integer | Number of votes contributing to the public rating; not watchers. |
| popularity | nullable number | Provider popularity value. Use only with a known popularity_metric. |
| popularity_metric | nullable enum | `rank`, `score`, or `count`. MDL popularity rank uses `rank` (positive integer, lower is more popular). Never substitute watchers or rating rank for popularity rank. |
| synopsis | nullable string | Provider description, including source attribution when present. |
| keywords | nullable JSON string array | Provider keywords/tags; not user-authored reactions. |
| external_api_id | nullable string | Stable MDL/provider record ID; do not use a mutable display title as an identifier. |
| metadata_source | nullable string | Source namespace, initially `mydramalist`. |
| source_url | nullable URL | Canonical source page for the matched drama. |
| metadata_retrieved_at | nullable UTC timestamp | Time this metadata snapshot was retrieved, not its historical publication time. |

## Data lifecycle

User fields and external fields share this initial flat-file representation but have separate ownership. Metadata refresh must not change user-provided columns. This file is a raw collection ledger with agreed serialization; preserve exact external response payloads separately when ingestion is implemented. Numeric parsing and year extraction are transformations even when stored in this ledger.

Write cleaned/validated outputs to `data/processed/` without overwriting the raw source. The EDA notebook reads the processed file and uses `my_rating`. The Excel importer produces `data/processed/watch_history_clean.csv` and quality reports. Processed rows add `source_sheet` and `source_excel_row` for provenance; invalid values or unmapped source columns are retained in explicit additional columns. The metadata CLI writes the separate raw collection CSV and does not automatically enrich the processed Excel import. Move to related PostgreSQL tables when persistence and refresh requirements justify it.

## Prediction boundaries

For a target drama, exclude its rating, favorite flag, rewatch response, final viewing status, post-watch notes from predictive inputs. A like label is derived from the rating only after its threshold is explicitly defined. Historical preference features may use only feedback available before the prediction time.

Public ratings, vote counts, popularity, final episode counts, and edited text retrieved today are not necessarily valid inputs for a historical prediction. Retrieval timestamps establish when data was collected; they do not prove that the same values were available earlier. This initial CSV stores current records, not an event history. Viewing and feedback dates are not collected, so this dataset cannot support a verified chronological split. Future evaluation must document that limitation and avoid claiming historical availability of feedback or metadata. IDs and titles are matching fields rather than baseline model features. Fit learned preprocessing using training data only.
