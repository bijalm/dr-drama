"""Build a provisional, metadata-only starter catalog from existing MDL caches."""

import argparse
from datetime import date
import hashlib
import json
from pathlib import Path

import pandas as pd

from dr_drama.data.watch_history import EXTERNAL_FIELDS


def build_catalog(cache_dir: Path, history_path: Path, output: Path, *, as_of: date) -> dict:
    """Reuse cached details without requests or changes to history/raw responses.

    Conservative eligibility requires prior-year Korean multi-episode entries,
    complete ranking metadata, and a real synopsis. Missing media type remains
    provisional. This selection is search-biased and is not a discovery API.
    """
    if output.resolve() == history_path.resolve():
        raise ValueError('Catalog output cannot overwrite history')
    original_hash = hashlib.sha256(history_path.read_bytes()).hexdigest()
    watched = set(pd.read_csv(history_path, dtype=str).external_api_id)
    rows, review = {}, []
    for path in sorted(cache_dir.glob('*.json')):
        document = json.loads(path.read_text(encoding='utf-8'))
        if document.get('kind') != 'details':
            continue
        item, raw, warnings = document['response']
        identifier = item['external_api_id']
        reason = ''
        media_type = str(raw['details'].get('type') or raw['details'].get('content_type') or '').casefold()
        if identifier in watched:
            reason = 'already_in_history'
        elif item.get('country') != ['KR'] or (item.get('number_of_episodes') or 0) <= 1:
            reason = 'country_or_episode_scope'
        elif any(term in media_type for term in ['movie', 'special', 'variety']):
            reason = 'ineligible_media_type'
        elif not item.get('release_year') or item['release_year'] >= as_of.year:
            reason = 'release_requires_review'
        elif any(not item.get(field) for field in ['genres', 'main_cast', 'public_rating', 'public_vote_count']):
            reason = 'incomplete_ranking_metadata'
        elif not item.get('synopsis') or item['synopsis'].strip().casefold() == 'edit translation':
            reason = 'missing_synopsis'
        if reason:
            review.append({'external_api_id': identifier, 'reason': reason})
            continue
        row = {field: json.dumps(item.get(field), ensure_ascii=False) if isinstance(item.get(field), list)
               else item.get(field) for field in EXTERNAL_FIELDS}
        row.update(catalog_status='provisional_tv_candidate', catalog_origin='cached_title_search',
                   cache_file=path.name, cache_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        if identifier not in rows or str(row['metadata_retrieved_at']) > str(rows[identifier]['metadata_retrieved_at']):
            rows[identifier] = row
    if not rows:
        raise ValueError('No eligible cached candidates; supply a reviewed catalog')
    output.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows.values()).sort_values('external_api_id').to_csv(output, index=False)
    assert hashlib.sha256(history_path.read_bytes()).hexdigest() == original_hash
    report = {'as_of': as_of.isoformat(), 'candidates': len(rows), 'history_sha256': original_hash,
              'selection': 'Cached alternative title matches; small biased starter catalog, no completeness claim.',
              'identity': 'Media type provisional; absent from history does not prove never watched.',
              'excluded': review}
    output.with_suffix('.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', type=Path, default=Path('data/raw/mdl_enrichment'))
    parser.add_argument('--history', type=Path, default=Path('data/processed/watch_history_enriched.csv'))
    parser.add_argument('--output', type=Path, default=Path('data/processed/candidate_catalog.csv'))
    parser.add_argument('--as-of', type=date.fromisoformat, default=date.today())
    args = parser.parse_args()
    report = build_catalog(args.cache, args.history, args.output, as_of=args.as_of)
    print(f"Saved {report['candidates']} provisional candidates to {args.output}")


if __name__ == '__main__':
    main()
