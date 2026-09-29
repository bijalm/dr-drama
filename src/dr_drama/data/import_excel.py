"""Read-only Excel import with traceable normalization and local quality reports."""

import argparse
from collections import Counter
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
import unicodedata

import openpyxl
import pandas as pd

from dr_drama.data.watch_history import USER_FIELDS, EXTERNAL_FIELDS

ALIASES = {
    "title": "title", "drama title": "title", "name": "title",
    "my rating": "my_rating", "personal rating": "my_rating",
    "status": "status", "favorite": "favorite", "favourite": "favorite",
    "would rewatch": "would_rewatch", "rewatch": "would_rewatch",
    "personal notes": "personal_notes", "notes": "personal_notes",
    "canonical title": "canonical_title", "original title": "original_title",
    "year": "release_year", "release year": "release_year",
    "country": "country", "original language": "original_language",
    "genre": "genres", "genres": "genres", "cast": "main_cast", "main cast": "main_cast",
    "episodes": "number_of_episodes", "number of episodes": "number_of_episodes",
    "public rating": "public_rating", "vote average": "public_rating",
    "public vote count": "public_vote_count", "vote count": "public_vote_count",
    "popularity": "popularity", "popularity metric": "popularity_metric",
    "synopsis": "synopsis", "overview": "synopsis", "keywords": "keywords", "tags": "keywords",
    "external api id": "external_api_id", "mydramalist id": "external_api_id",
    "metadata source": "metadata_source", "source url": "source_url",
    "metadata retrieved at": "metadata_retrieved_at",
}
STATUS = {"completed": "completed", "complete": "completed", "dropped": "dropped", "unfinished": "unfinished", "watching": "watching"}
BOOLEAN = {"yes": "yes", "y": "yes", "true": "yes", "no": "no", "n": "no", "false": "no"}
NUMERIC = {"my_rating": "Float64", "public_rating": "Float64", "popularity": "Float64", "release_year": "Int64", "number_of_episodes": "Int64", "public_vote_count": "Int64"}
LISTS = {"genres", "main_cast", "keywords", "country", "original_language"}


def empty(value) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def header_key(value) -> str:
    return re.sub(r"\s+", " ", str(value).replace("_", " ").strip()).casefold()


def title_key(value) -> str:
    """Comparison key only; the original display title is never replaced."""
    return re.sub(r"[^\w]+", " ", unicodedata.normalize("NFKC", str(value)).casefold()).strip()


def number(value, field: str):
    """Parse explicit numeric values without rounding or imputing invalid input."""
    if isinstance(value, bool):
        raise ValueError("Boolean is not a numeric measurement")
    try:
        result = Decimal(str(value).strip().replace(",", ""))
    except InvalidOperation:
        raise ValueError("Not a numeric value") from None
    if not result.is_finite():
        raise ValueError("Non-finite number")
    if field == "my_rating" and (not 1 <= result <= 10 or result * 10 != (result * 10).to_integral_value()):
        raise ValueError("Personal rating must be 1–10 in 0.1 increments")
    if field == "public_rating" and not 0 <= result <= 10:
        raise ValueError("Public rating outside the expected 0–10 scale; verify source")
    if field == "release_year" and not 1900 <= result <= 2100:
        raise ValueError("Release year outside expected range")
    if field == "number_of_episodes" and result <= 0:
        raise ValueError("Episode count must be positive")
    if field in {"public_vote_count", "popularity"} and result < 0:
        raise ValueError("Count/score cannot be negative")
    if NUMERIC[field] == "Int64":
        if result != result.to_integral_value():
            raise ValueError("Expected a whole number")
        return int(result)
    return float(result)


def list_value(value) -> str:
    """Encode lists as JSON; plain text uses comma, semicolon, or pipe delimiters."""
    if isinstance(value, list):
        items = value
    elif str(value).strip().startswith("["):
        items = json.loads(str(value))
        if not isinstance(items, list):
            raise ValueError("Expected a JSON array")
    else:
        items = re.split(r"[,;|]", str(value))
    if any(not isinstance(item, str) for item in items):
        raise ValueError("List entries must be text")
    return json.dumps([item.strip() for item in items if item.strip()], ensure_ascii=False)


def inspect_workbook(path: Path) -> tuple[list[dict], list[dict]]:
    """Inspect every sheet without saving the workbook or executing formulas."""
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=False)
    sheets, records = [], []
    try:
        for sheet in workbook:
            values = list(sheet.iter_rows(values_only=True))
            populated = [(index + 1, row) for index, row in enumerate(values) if any(not empty(v) for v in row)]
            if not populated:
                sheets.append({"sheet": sheet.title, "rows": 0, "columns": [], "imported": False})
                continue
            header_row, headers = populated[0]
            if any(empty(header) for header in headers):
                raise ValueError(f"{sheet.title}: blank column headers require review")
            columns = [str(header) for header in headers]
            targets = [ALIASES.get(header_key(header), 'source_' + re.sub(r'[^a-z0-9]+', '_', header_key(header))) for header in headers]
            if len(set(targets)) != len(targets) or set(targets) & {'source_sheet', 'source_excel_row'}:
                raise ValueError(f"{sheet.title}: colliding column mappings require review")
            data = populated[1:]
            summary = {"sheet": sheet.title, "rows": len(data), "header_row": header_row, "blank_rows_skipped": len(values) - len(populated), "imported": 'title' in targets, "columns": [], "mapping": dict(zip(columns, targets))}
            for i, name in enumerate(columns):
                vals = [row[i] for _, row in data]
                summary['columns'].append({"name": name, "target": targets[i], "missing": sum(empty(v) for v in vals), "types": dict(Counter(type(v).__name__ for v in vals if not empty(v))), "categories": dict(Counter(str(v) for v in vals if not empty(v))) if targets[i] in {'status','favorite','would_rewatch'} else None})
            sheets.append(summary)
            if 'title' in targets:
                for row_number, row in data:
                    records.append({**dict(zip(targets, row)), 'source_sheet': sheet.title, 'source_excel_row': row_number})
    finally:
        workbook.close()
    return sheets, records


def clean_records(records: list[dict]) -> tuple[pd.DataFrame, dict]:
    """Standardize known categories and types, preserving source text and rows.

    Invalid numbers are retained in original_<field> and flagged, never rounded.
    Unknown categories are preserved and flagged rather than guessed.
    """
    cleaned, changes, issues = [], [], []
    for record in records:
        row = dict.fromkeys(USER_FIELDS + EXTERNAL_FIELDS)
        row.update(record)
        reference = {"sheet": record.get('source_sheet'), "excel_row": record.get('source_excel_row')}
        for field, value in list(row.items()):
            if empty(value):
                row[field] = None
                continue
            normalized = value
            if isinstance(value, str) and value.startswith('='):
                issues.append({**reference, 'field': field, 'issue': 'Formula text retained; no formula evaluation performed'})
            try:
                if field == 'status' or field in {'favorite', 'would_rewatch'}:
                    mapping = STATUS if field == 'status' else BOOLEAN
                    normalized = mapping.get(str(value).strip().casefold(), value)
                    if normalized not in mapping.values():
                        issues.append({**reference, 'field': field, 'issue': 'Unrecognized category retained', 'value': value})
                elif field in NUMERIC:
                    normalized = number(value, field)
                elif field in LISTS:
                    normalized = list_value(value)
                elif field == 'external_api_id':
                    normalized = str(value)
            except (ValueError, TypeError) as error:
                row['original_' + field] = str(value)
                normalized = None
                issues.append({**reference, 'field': field, 'issue': str(error), 'original_value': value})
            row[field] = normalized
            if str(normalized) != str(value) and not (isinstance(value, (int, float)) and normalized == value):
                changes.append({**reference, 'field': field, 'before': value, 'after': normalized})
            if field == 'personal_notes' and isinstance(value, str) and value != value.strip():
                issues.append({**reference, 'field': field, 'issue': 'Leading/trailing whitespace preserved'})
        if empty(row['title']):
            issues.append({**reference, 'field': 'title', 'issue': 'Missing title; row retained'})
        if empty(row['status']):
            issues.append({**reference, 'field': 'status', 'issue': 'Missing status; not inferred'})
        if isinstance(row['title'], str) and '/' in row['title']:
            issues.append({**reference, 'field': 'title', 'issue': 'Possible alternate titles; confirm identity before enrichment', 'value': row['title']})
        if row.get('popularity') is not None and not row.get('popularity_metric'):
            issues.append({**reference, 'field': 'popularity', 'issue': 'Popularity metric must be identified before modeling'})
        cleaned.append(row)
    frame = pd.DataFrame(cleaned)
    if frame.empty:
        frame = pd.DataFrame(columns=list(USER_FIELDS + EXTERNAL_FIELDS) + ['source_sheet', 'source_excel_row'])
    for field, dtype in NUMERIC.items():
        frame[field] = pd.array(frame[field], dtype=dtype)
    for field in frame.columns:
        if field not in NUMERIC and field != 'source_excel_row':
            frame[field] = frame[field].astype('string')
    frame['source_excel_row'] = pd.array(frame['source_excel_row'], dtype='Int64')
    groups = {}
    for record in records:
        if not empty(record.get('title')):
            groups.setdefault(title_key(record['title']), []).append({'title': record['title'], 'sheet': record.get('source_sheet'), 'excel_row': record.get('source_excel_row')})
    duplicates = [entries for entries in groups.values() if len(entries) > 1]
    report = {'rows': len(frame), 'changes': changes, 'issues': issues, 'duplicate_title_groups': duplicates,
              'missing_values': {key: int(value) for key, value in frame.isna().sum().items()},
              'processed_types': {key: str(value) for key,value in frame.dtypes.items()},
              'normalized_categories': {field: {str(k): int(v) for k,v in frame[field].value_counts(dropna=False).items()} for field in ['status','favorite','would_rewatch']},
              'unchanged': ['Original workbook bytes', 'All nonblank source rows retained in original order', 'Title text, valid rating values, and personal notes preserved', 'No external metadata fetched or inferred', 'No missing-value imputation or automatic deduplication'],
              'enrichment': {field: {'missing': int(frame[field].isna().sum()), 'present': int(frame[field].notna().sum())} for field in EXTERNAL_FIELDS}}
    return frame, report


def import_excel(source: Path, output: Path, raw_dir: Path) -> dict:
    """Snapshot original bytes, inspect/clean, and write CSV plus private reports."""
    source = source.resolve()
    if output.resolve() == source:
        raise ValueError('Output must not overwrite the original workbook')
    content = source.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    raw_dir.mkdir(parents=True, exist_ok=True)
    snapshot = raw_dir / f'{source.stem}-{digest[:12]}.xlsx'
    if not snapshot.exists():
        snapshot.write_bytes(content)
    elif snapshot.read_bytes() != content:
        raise ValueError('Existing raw snapshot does not match source bytes')
    sheets, records = inspect_workbook(snapshot)
    if not records:
        raise ValueError('No populated sheet with a recognized title column found')
    frame, report = clean_records(records)
    report.update(source_name=source.name, source_sha256=digest, raw_snapshot=str(snapshot), sheets=sheets)
    if source.read_bytes() != content:
        raise ValueError('Source changed during import; rerun against a stable workbook')
    output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output, index=False, encoding='utf-8', na_rep='')
    report_path = output.with_name('watch_history_quality_report.json')
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    lines = ['# Watch-history data quality report', '', f"Records: {len(frame)}. Source SHA-256: `{digest}`.", '', '## Source inspection', '']
    for sheet in sheets:
        lines += [f"### {sheet['sheet']}", '', f"Data rows: {sheet['rows']}; imported: {sheet['imported']}.", '', '| Source column | Standard column | Source types | Missing |', '|---|---|---|---|']
        for col in sheet['columns']:
            lines.append(f"| {col['name']} | {col['target']} | {col['types']} | {col['missing']} |")
    counts = Counter(change['field'] for change in report['changes'])
    lines += ['', '## Changes', '', f"Value normalization counts: {dict(counts)}.", 'Headers mapped to the schema; numeric columns assigned nullable numeric types. Source sheet and Excel row retained for tracing.', '', '## Preserved', ''] + ['- ' + item for item in report['unchanged']]
    lines += ['', '## Categories', '', json.dumps(report['normalized_categories'], ensure_ascii=False), '', '## Missing values and processed types', '', '| Field | Missing | Type |', '|---|---|---|']
    for field in frame.columns:
        lines.append(f"| {field} | {report['missing_values'][field]} | {report['processed_types'][field]} |")
    lines += ['', '## Duplicates', '', f"Potential duplicate title groups: {len(report['duplicate_title_groups'])}. No rows removed."]
    for group in report['duplicate_title_groups']:
        lines.append('- ' + json.dumps(group, ensure_ascii=False))
    lines += ['', '## Issues for review', '']
    lines += ['- ' + json.dumps(issue, ensure_ascii=False, default=str) for issue in report['issues']] or ['None detected.']
    lines += ['', '## External validation and enrichment', '', 'Existing external values are preserved after representation/type normalization. Missing metadata is not guessed. Titles, release year, cast, genres, episodes, country/language, synopsis, and source-specific public ratings could be checked against a selected MyDramaList or TMDB record. Do not replace MDL ratings/popularity with TMDB metrics without separate source-specific fields. Original source IDs cannot be reused across providers. No external requests were made.', '', 'See the adjacent JSON report for per-cell changes, original categorical values, full source mappings, and enrichment counts. CSV has no stored data types; the processed_types report specifies intended types for loading.']
    output.with_name('watch_history_quality_report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--output', type=Path, default=Path('data/processed/watch_history_clean.csv'))
    parser.add_argument('--raw-dir', type=Path, default=Path('data/raw/excel'))
    args = parser.parse_args()
    report = import_excel(args.source, args.output, args.raw_dir)
    print(json.dumps({'rows': report['rows'], 'sheets': [s['sheet'] for s in report['sheets']], 'changes': len(report['changes']), 'issues': len(report['issues']), 'duplicate_groups': len(report['duplicate_title_groups']), 'source_sha256': report['source_sha256']}, indent=2))


if __name__ == '__main__':
    main()
