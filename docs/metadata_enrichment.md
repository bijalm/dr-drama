# MDL enrichment

Run from the repository root:

```powershell
.\.venv\Scripts\python.exe -m dr_drama.data.enrich_mdl
```

Input: `data/processed/watch_history_clean.csv`. Output: `data/processed/watch_history_enriched.csv`. Input files and personal columns are preserved. Review outputs are `mdl_match_review.csv` and `mdl_enrichment_review.json` beside the enriched file. All contain personal dataset information and remain ignored by Git.

Every external field has companion `__spreadsheet`, `__mdl`, `__provenance`, and `__comparison` columns. Populated spreadsheet values take precedence and conflicting MDL values are retained separately for review. Missing input values can be filled from MDL. Provenance is `spreadsheet`, `mdl`, or `missing`; `resolved_combination` is reserved for future explicit conflict resolution and is never assigned automatically. Representation cleanup of an MDL value does not imply a combination of sources. MDL retrieval timestamps and cached responses identify the source snapshot.

Match decisions use unique exact normalized titles or provider-declared aliases. Similarity only selects candidates to inspect, never proves identity. Multiple exact matches, spelling differences, missing results, and API failures remain unresolved. Korean multi-episode matches with missing media type are explicitly provisional; verify their source links before treating identity as confirmed. Duplicate IDs across source rows are flagged.

The temporary unofficial provider can omit language and media type. No values are inferred from personal ratings or notes. Only search titles are sent externally. Successful responses are cached under `data/raw/mdl_enrichment/`, keyed by provider and query. Reruns reuse evidence; use a separate cache directory to request a new snapshot. Public scores and popularity reflect retrieval time, not historical viewing time. The provider will be replaced when official MyDramaList access becomes available.


## Reviewed title mappings

The optional `--resolutions` argument defaults to the ignored `data/processed/mdl_title_resolutions.json`. Reviewed mappings contain the original input title, selected MDL slug, decision reason, reviewer, and source evidence. Reruns apply these mappings before automatic title matching. Assistant-reviewed title matches and user-confirmed matches have distinct status labels. They do not imply that the API supplied a verified media-type field.

Resolving title identity does not turn MDL metadata into mixed-source values. Original spreadsheet titles remain unchanged; canonical titles and retrieved metadata retain MDL provenance. Explicit field-level conflict resolution is separate.
