"""Conservative MDL enrichment with cached evidence and field-level provenance."""

import argparse
import csv
from datetime import datetime, timezone
from difflib import SequenceMatcher
import hashlib
import json
from pathlib import Path
import re
import unicodedata

from dr_drama.data.watch_history import EXTERNAL_FIELDS
from dr_drama.tools.mydramalist import MyDramaListClient, MetadataError


def key(value: str) -> str:
    return re.sub(r"[^\w]", "", unicodedata.normalize("NFKC", value).casefold())


def serialized(value) -> str:
    if value is None:
        return ''
    return json.dumps(value, ensure_ascii=False) if isinstance(value, list) else str(value)


def equivalent(a: str, b: str) -> bool:
    if a == b:
        return True
    try:
        left, right = json.loads(a), json.loads(b)
        if isinstance(left, list) and isinstance(right, list):
            return sorted(str(x).casefold() for x in left) == sorted(str(x).casefold() for x in right)
        return isinstance(left, (int, float)) and isinstance(right, (int, float)) and left == right
    except (ValueError, TypeError):
        return False


def merge(row: dict, metadata: dict | None) -> tuple[dict, list[dict]]:
    """Preserve populated input values and retain MDL alternatives on conflicts."""
    result, conflicts = dict(row), []
    for field in EXTERNAL_FIELDS:
        source, mdl = row.get(field, ''), serialized((metadata or {}).get(field))
        result[field + '__spreadsheet'] = source
        result[field + '__mdl'] = mdl
        if source:
            result[field] = source
            result[field + '__provenance'] = 'spreadsheet'
            result[field + '__comparison'] = 'agrees' if mdl and equivalent(source, mdl) else 'conflict' if mdl else 'mdl_missing'
            if mdl and not equivalent(source, mdl):
                conflicts.append({'field': field, 'spreadsheet': source, 'mdl': mdl})
        else:
            result[field] = mdl
            result[field + '__provenance'] = 'mdl' if mdl else 'missing'
            result[field + '__comparison'] = 'filled_missing' if mdl else 'both_missing'
    return result, conflicts


class Cache:
    """Persist successful responses with provider identity; retries can resume."""
    def __init__(self, folder: Path, client: MyDramaListClient):
        self.folder, self.client = folder, client
        folder.mkdir(parents=True, exist_ok=True)

    def get(self, kind: str, value: str):
        digest = hashlib.sha256((self.client.base_url + kind + value).encode()).hexdigest()
        path = self.folder / (digest + '.json')
        if path.exists():
            return json.loads(path.read_text(encoding='utf-8'))['response']
        response = self.client.search(value) if kind == 'search' else self.client.fetch(value)
        path.write_text(json.dumps({'provider': self.client.base_url, 'kind': kind, 'query': value, 'retrieved_at': datetime.now(timezone.utc).isoformat(), 'response': response}, ensure_ascii=False, indent=2), encoding='utf-8')
        return response


def match_title(title: str, cache: Cache) -> dict:
    """Accept unique exact normalized titles/aliases only; fuzzy results need review.

    A Korean multi-episode record is provisional when the API omits media type.
    This is entity matching, not a prediction of user preference.
    """
    queries = [q.strip() for q in title.split('/') if q.strip()]
    candidates = {}
    for query in queries:
        for candidate in cache.get('search', query):
            candidates[candidate['slug']] = candidate
    target_keys = {key(q) for q in queries}
    exact = [c for c in candidates.values() if key(c['title']) in target_keys]
    def score(candidate):
        names = [candidate['title'], candidate['slug'].split('-', 1)[-1]]
        return max(SequenceMatcher(None, key(q), key(name)).ratio() for q in queries for name in names)
    ranked = sorted(candidates.values(), key=score, reverse=True)
    result = {'status': 'needs_review' if candidates else 'no_results', 'candidates': ranked[:5], 'metadata': None, 'warnings': [], 'method': ''}
    if len(exact) > 5:
        result['warnings'].append('More than five exact-title records; choose the intended year/series.')
        return result
    # Alias lookup is permitted only for a small shortlist; fuzzy similarity alone never accepts a match.
    shortlist = exact or [c for c in ranked[:2] if score(c) >= 0.72]
    accepted = []
    for candidate in shortlist:
        metadata, raw, warnings = cache.get('details', candidate['slug'])
        aliases = raw['details'].get('also_known_as') or []
        aliases = aliases if isinstance(aliases, list) else []
        names = [metadata['canonical_title'], candidate['title'], *[a for a in aliases if isinstance(a, str)]]
        if not any(key(name) in target_keys for name in names):
            continue
        result['warnings'].extend(warnings)
        media_type = str(raw['details'].get('type') or raw['details'].get('content_type') or '').casefold()
        if metadata.get('country') != ['KR'] or (metadata.get('number_of_episodes') or 0) <= 1 or any(term in media_type for term in ['movie', 'special', 'variety']) or 'special' in candidate['title'].casefold():
            result['warnings'].append('Country, episode count, or media type needs manual verification.')
            continue
        accepted.append((metadata, 'exact_title' if key(candidate['title']) in target_keys else 'exact_provider_alias', media_type in {'drama', 'tv series', 'tv show'}))
    if len(accepted) == 1:
        result['metadata'], result['method'], typed = accepted[0]
        result['status'] = 'matched' if typed else 'provisional_tv_match'
        if not typed:
            result['warnings'].append('Media type not supplied: Korean origin and multiple episodes support, but do not prove, TV-series identity.')
    return result


def reviewed_match(title: str, resolution: dict, cache: Cache) -> dict:
    """Replay an explicit reviewed ID mapping and preserve its decision evidence."""
    metadata, raw, warnings = cache.get('details', resolution['slug'])
    if metadata.get('country') != ['KR'] or (metadata.get('number_of_episodes') or 0) <= 1:
        raise MetadataError('Reviewed record no longer passes country/episode checks.')
    return {'status': resolution['status'], 'metadata': metadata,
            'method': 'reviewed_mapping', 'candidates': [],
            'warnings': warnings, 'resolution': resolution}


def run(source: Path, output: Path, cache_dir: Path, resolutions_path: Path | None = None) -> dict:
    if source.resolve() == output.resolve():
        raise ValueError('Enrichment output must differ from input')
    original = source.read_bytes()
    with source.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        rows = list(reader)
    client = MyDramaListClient.from_env('.env')
    cache = Cache(cache_dir, client)
    resolutions = json.loads(resolutions_path.read_text(encoding='utf-8')) if resolutions_path and resolutions_path.exists() else {}
    results, reviews = [], []
    try:
        for index, row in enumerate(rows, 1):
            try:
                match = reviewed_match(row['title'], resolutions[row['title']], cache) if row['title'] in resolutions else match_title(row['title'], cache)
            except MetadataError as error:
                match = {'status': 'api_error', 'metadata': None, 'method': '', 'candidates': [], 'warnings': [str(error)]}
            enriched, conflicts = merge(row, match['metadata'])
            enriched.update(mdl_match_status=match['status'], mdl_match_method=match['method'], mdl_match_resolution=json.dumps(match.get('resolution', {}), ensure_ascii=False), mdl_match_warnings=json.dumps(match['warnings'], ensure_ascii=False), mdl_conflicting_fields=json.dumps([c['field'] for c in conflicts]))
            results.append(enriched)
            reviews.append({'row': index + 1, 'title': row['title'], **match, 'conflicts': conflicts})
            print(f"{index}/{len(rows)}: {match['status']}", flush=True)
    finally:
        client.close()
    # Flag collisions across source titles; never conceal possible duplicates.
    ids = {}
    for index, row in enumerate(results):
        identifier = row.get('external_api_id__mdl')
        if identifier:
            ids.setdefault(identifier, []).append(index)
    collisions = [indexes for indexes in ids.values() if len(indexes) > 1]
    for indexes in collisions:
        for index in indexes:
            results[index]['mdl_match_status'] = 'duplicate_id_review'
            reviews[index]['status'] = 'duplicate_id_review'
    if source.read_bytes() != original:
        raise ValueError('Input changed during enrichment; cached evidence is retained, rerun required')
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(results[0]))
        writer.writeheader()
        writer.writerows(results)
    counts = {status: sum(row['mdl_match_status'] == status for row in results) for status in sorted({r['mdl_match_status'] for r in results})}
    report = {'input_sha256': hashlib.sha256(original).hexdigest(), 'counts': counts, 'conflict_count': sum(len(r['conflicts']) for r in reviews), 'reviews': reviews}
    output.with_name('mdl_enrichment_review.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    with output.with_name('mdl_match_review.csv').open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=['title','status','method','candidates','warnings','conflicts'])
        writer.writeheader()
        for review in reviews:
            writer.writerow({k: json.dumps(review[k], ensure_ascii=False) if isinstance(review[k], list) else review[k] for k in writer.fieldnames})
    coverage = {field: sum(bool(row.get(field)) for row in results) for field in EXTERNAL_FIELDS}
    unresolved = [r['title'] for r in reviews if r['metadata'] is None]
    lines = ['# MDL enrichment results', '', f'Rows: {len(results)}.',
             f'Match statuses: {counts}.', f"Field conflicts: {report['conflict_count']}.", '',
             'Original personal fields and populated spreadsheet metadata are retained. A reviewed title mapping resolves entity identity; it does not change the source of an MDL field. Media type remains unverified where omitted by the temporary provider.', '',
             '## Field coverage', '', '| Field | Populated rows |', '|---|---|']
    lines += [f'| {field} | {count} |' for field, count in coverage.items()]
    lines += ['', '## Unresolved titles', ''] + (['- ' + title for title in unresolved] or ['None.'])
    lines += ['', 'See mdl_enrichment_review.json and mdl_match_review.csv for decisions, warnings, and conflicts. Reviewed mappings are stored in mdl_title_resolutions.json. Public metrics reflect collection time; missing language is not inferred.']
    output.with_name('mdl_enrichment_report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps(counts), flush=True)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path('data/processed/watch_history_clean.csv'))
    parser.add_argument('--output', type=Path, default=Path('data/processed/watch_history_enriched.csv'))
    parser.add_argument('--cache-dir', type=Path, default=Path('data/raw/mdl_enrichment'))
    parser.add_argument('--resolutions', type=Path, default=Path('data/processed/mdl_title_resolutions.json'))
    args = parser.parse_args()
    run(args.source, args.output, args.cache_dir, args.resolutions)
