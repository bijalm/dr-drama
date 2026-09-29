import unittest
from dr_drama.data.enrich_mdl import merge, match_title, reviewed_match

class FakeCache:
    def __init__(self, candidates, details=None):
        self.candidates, self.details = candidates, details
    def get(self, kind, value):
        if kind == 'search':
            return self.candidates
        return self.details

class EnrichmentTests(unittest.TestCase):
    def test_conflict_preserves_input_and_both_sources(self):
        result, conflicts = merge({'title':'Fixture','my_rating':'6.7','release_year':'2020'}, {'release_year':2021,'genres':['Drama']})
        self.assertEqual(result['release_year'], '2020')
        self.assertEqual(result['release_year__mdl'], '2021')
        self.assertEqual(result['release_year__provenance'], 'spreadsheet')
        self.assertEqual(result['my_rating'], '6.7')
        self.assertEqual(result['genres__provenance'], 'mdl')
        self.assertEqual(len(conflicts), 1)
    def test_equivalent_numbers_not_conflicts(self):
        result, conflicts = merge({'public_rating':'8.0'}, {'public_rating':8})
        self.assertEqual(conflicts, [])
        self.assertEqual(result['public_rating__comparison'], 'agrees')
    def test_multiple_exact_matches_remain_unresolved(self):
        cache=FakeCache([{'title':'Fixture','slug':'1-a'},{'title':'Fixture','slug':'2-a'}], ({'canonical_title':'Fixture','country':['KR'],'number_of_episodes':16}, {'details':{}}, []))
        self.assertIsNone(match_title('Fixture',cache)['metadata'])
    def test_fuzzy_match_is_not_accepted(self):
        cache=FakeCache([{'title':'Fixtures','slug':'1-a'}], ({'canonical_title':'Fixtures','country':['KR'],'number_of_episodes':16}, {'details':{}}, []))
        self.assertIsNone(match_title('Fixture',cache)['metadata'])
    def test_missing_media_type_marked_provisional(self):
        cache=FakeCache([{'title':'Fixture','slug':'1-a'}], ({'canonical_title':'Fixture','country':['KR'],'number_of_episodes':16}, {'details':{}}, []))
        self.assertEqual(match_title('Fixture',cache)['status'],'provisional_tv_match')

    def test_reviewed_mapping_records_decision(self):
        cache=FakeCache([], ({'canonical_title':'Fixture','country':['KR'],'number_of_episodes':16}, {'details':{}}, []))
        resolution={'slug':'1-fixture','status':'user_confirmed_match','reason':'User confirmed year'}
        result=reviewed_match('Original spelling',resolution,cache)
        self.assertEqual(result['status'],'user_confirmed_match')
        self.assertEqual(result['resolution']['reason'],'User confirmed year')
        self.assertEqual(result['method'],'reviewed_mapping')
