"""Offline checks for provider normalization, transport, selection, and saving."""

import csv
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx

from dr_drama.tools.mydramalist import MetadataError, MyDramaListClient, normalize_metadata
from dr_drama.data.watch_history import save_metadata
from dr_drama.tools.metadata_cli import main


class MetadataTests(unittest.TestCase):
    def metadata(self):
        return normalize_metadata({"title": "Fixture (2020)", "aired": "Dec 1, 2020 - Jan 2, 2021", "country": "South Korea", "episodes": "16", "rating": "8.1", "score_details": "8.1 (scored by 1,234 users)", "popularity": "#82", "watchers": "99999", "ranked": "#1"}, {"cast": {"Main Role": [{"name": f"Actor {i}"} for i in range(7)], "Director": [{"name": "Director"}]}}, "123-fixture")

    def test_normalization_and_missing_language(self):
        data = self.metadata()
        self.assertEqual(data['canonical_title'], 'Fixture')
        self.assertEqual(data['release_year'], 2020)
        self.assertEqual(data['public_vote_count'], 1234)
        self.assertEqual(data['popularity'], 82)
        self.assertEqual(data['country'], ['KR'])
        self.assertIsNone(data['original_language'])
        self.assertEqual(len(data['main_cast']), 5)
        self.assertEqual(data['external_api_id'], '123')

    def test_missing_fields_and_unrated(self):
        data = normalize_metadata({'title': 'Fixture', 'rating': '0', 'episodes': '?', 'score_details': '0 (scored by 0 users)'}, {}, '123-fixture')
        self.assertIsNone(data['public_rating'])
        self.assertIsNone(data['number_of_episodes'])
        self.assertIsNone(data['main_cast'])
        self.assertIsNone(data['genres'])

    def test_no_results_and_multiple_results_preserved(self):
        payloads = [{'results': []}, {'results': [{'title': 'A', 'slug': '1-mr.-a'}, {'title': 'B', 'slug': '2-b'}]}]
        client = MyDramaListClient('https://fixture.example', transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payloads.pop(0))), sleep=lambda _: None)
        try:
            self.assertEqual(client.search('nothing'), [])
            self.assertEqual(len(client.search('ambiguous')), 2)
        finally:
            client.close()

    def test_rate_limit_retries_and_honors_delay(self):
        waits = []
        responses = [httpx.Response(429, headers={'Retry-After': '3'}), httpx.Response(200, json={'results': []})]
        client = MyDramaListClient('https://fixture.example', transport=httpx.MockTransport(lambda request: responses.pop(0)), sleep=waits.append)
        try:
            self.assertEqual(client.search('fixture'), [])
            self.assertIn(3, waits)
        finally:
            client.close()

    def test_provider_errors(self):
        for response in [httpx.Response(403), httpx.Response(200, text='not JSON'), httpx.Response(200, json={'error': True}), httpx.Response(200, json={})]:
            with self.subTest(response=response):
                client = MyDramaListClient('https://fixture.example', transport=httpx.MockTransport(lambda request: response), sleep=lambda _: None)
                try:
                    with self.assertRaises(MetadataError):
                        client.search('fixture')
                finally:
                    client.close()

    def test_retries_are_bounded(self):
        calls = []
        def handler(request):
            calls.append(request)
            return httpx.Response(503)
        client = MyDramaListClient('https://fixture.example', transport=httpx.MockTransport(handler), sleep=lambda _: None)
        try:
            with self.assertRaises(MetadataError):
                client.search('fixture')
            self.assertEqual(len(calls), 3)
        finally:
            client.close()

    def test_partial_cast_failure(self):
        def handler(request):
            return httpx.Response(404) if request.url.path.endswith('/cast') else httpx.Response(200, json={'title': 'Fixture'})
        client = MyDramaListClient('https://fixture.example', transport=httpx.MockTransport(handler), sleep=lambda _: None)
        try:
            data, raw, warnings = client.fetch('123-fixture')
            self.assertIsNone(data['main_cast'])
            self.assertTrue(any('Cast unavailable' in warning for warning in warnings))
        finally:
            client.close()

    def test_refresh_preserves_personal_fields_and_rejects_conflicting_id(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'history.csv'
            metadata = self.metadata()
            save_metadata(path, 'My title', metadata, 'watching')
            with path.open(newline='', encoding='utf-8') as stream:
                reader = csv.DictReader(stream)
                fields, rows = reader.fieldnames, list(reader)
            rows[0].update(my_rating='6.7', favorite='yes', personal_notes='A note, with punctuation')
            with path.open('w', newline='', encoding='utf-8') as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)
            save_metadata(path, 'Different title', {**metadata, 'public_rating': 8.5}, 'completed')
            with path.open(newline='', encoding='utf-8') as stream:
                row = list(csv.DictReader(stream))[0]
            self.assertEqual(row['my_rating'], '6.7')
            self.assertEqual(row['status'], 'watching')
            self.assertEqual(row['title'], 'My title')
            self.assertEqual(row['public_rating'], '8.5')
            before = path.read_bytes()
            with self.assertRaises(ValueError):
                save_metadata(path, 'My title', {**metadata, 'external_api_id': '999'})
            self.assertEqual(path.read_bytes(), before)

    def test_cli_preview_decline_does_not_save(self):
        with patch('sys.argv', ['metadata_cli', 'Fixture']), patch('builtins.input', side_effect=['1', 'n']), patch('sys.stdout', new_callable=io.StringIO) as output, patch('dr_drama.tools.metadata_cli.MyDramaListClient.from_env') as factory, patch('dr_drama.tools.metadata_cli.save_metadata') as save:
            client = factory.return_value
            client.search.return_value = [{'title': 'Fixture', 'year': 2020, 'slug': '123-fixture', 'url': 'https://example.test'}]
            client.fetch.return_value = (self.metadata(), {}, [])
            self.assertEqual(main(), 0)
            self.assertIn('canonical_title', output.getvalue())
            client.fetch.assert_called_once_with('123-fixture')
            save.assert_not_called()

    def test_optional_authentication_requires_explicit_header(self):
        with self.assertRaises(MetadataError):
            MyDramaListClient('https://fixture.example', api_key='synthetic-test-key')
        seen = []
        def handler(request):
            seen.append(request.headers.get('X-Test-Key'))
            return httpx.Response(200, json={'results': []})
        client = MyDramaListClient('https://fixture.example', api_key='synthetic-test-key', key_header='X-Test-Key', transport=httpx.MockTransport(handler), sleep=lambda _: None)
        try:
            client.search('fixture')
            self.assertEqual(seen, ['synthetic-test-key'])
        finally:
            client.close()

    def test_duplicate_rows_rejected_without_modification(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'history.csv'
            save_metadata(path, 'Fixture', self.metadata(), 'watching')
            with path.open(newline='', encoding='utf-8') as stream:
                rows = list(csv.reader(stream))
            with path.open('a', newline='', encoding='utf-8') as stream:
                csv.writer(stream).writerow(rows[1])
            before = path.read_bytes()
            with self.assertRaises(ValueError):
                save_metadata(path, 'Fixture', self.metadata())
            self.assertEqual(path.read_bytes(), before)

    def test_cli_cancel_does_not_fetch_or_save(self):
        with patch('sys.argv', ['metadata_cli', 'Fixture']), patch('builtins.input', return_value=''), patch('sys.stdout', new_callable=io.StringIO), patch('dr_drama.tools.metadata_cli.MyDramaListClient.from_env') as factory, patch('dr_drama.tools.metadata_cli.save_metadata') as save:
            client = factory.return_value
            client.search.return_value = [{'title': 'Fixture', 'year': 2020, 'slug': '123-fixture', 'url': 'https://example.test'}]
            self.assertEqual(main(), 0)
            client.fetch.assert_not_called()
            save.assert_not_called()


if __name__ == '__main__':
    unittest.main()
