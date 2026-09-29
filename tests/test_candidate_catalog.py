"""Catalog scope and preservation checks using synthetic cached responses."""

from datetime import date
import json
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from dr_drama.data.candidate_catalog import build_catalog


class CatalogTests(unittest.TestCase):
    def test_scope_exclusion_provenance_and_source_preservation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = root / 'cache'
            cache.mkdir()
            history = root / 'history.csv'
            history.write_text('external_api_id,my_rating\n1,9\n', encoding='utf-8')
            original = history.read_bytes()
            for identifier, changes in [
                ('1', {}), ('2', {}), ('3', {'country': ['JP']}),
                ('4', {'release_year': 2026}), ('5', {'main_cast': None}),
                ('6', {'synopsis': 'Edit Translation'}),
            ]:
                item = {'external_api_id': identifier, 'canonical_title': 'Synthetic',
                        'country': ['KR'], 'release_year': 2020, 'number_of_episodes': 12,
                        'genres': ['Comedy'], 'main_cast': ['Actor A'], 'public_rating': 8,
                        'public_vote_count': 1000, 'synopsis': 'Synthetic series synopsis.',
                        'metadata_retrieved_at': '2026-01-01T00:00:00Z', **changes}
                (cache / f'{identifier}.json').write_text(json.dumps(
                    {'kind': 'details', 'response': [item, {'details': {}}, []]}), encoding='utf-8')
            output = root / 'candidates.csv'
            report = build_catalog(cache, history, output, as_of=date(2026, 9, 28))
            result = pd.read_csv(output, dtype=str)
            self.assertEqual(result.external_api_id.tolist(), ['2'])
            self.assertEqual(report['candidates'], 1)
            self.assertEqual(history.read_bytes(), original)
            self.assertEqual(len(result.cache_sha256.iloc[0]), 64)
            self.assertNotIn('my_rating', result)
            self.assertEqual(result.catalog_status.iloc[0], 'provisional_tv_candidate')

    def test_rejects_history_overwrite(self):
        with self.assertRaises(ValueError):
            build_catalog(Path('cache'), Path('history.csv'), Path('history.csv'), as_of=date(2026, 9, 28))
