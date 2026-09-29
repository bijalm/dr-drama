"""Descriptive aggregation checks for overlapping memberships and denominators."""
import unittest
import pandas as pd
from dr_drama.analysis.eda import memberships, grouped_summary, correlations

class EdaTests(unittest.TestCase):
    def fixture(self):
        return pd.DataFrame({'external_api_id':['1','2','3'], 'genres':['["Drama", "Comedy", "Drama"]','["Drama"]','[]'], 'my_rating':[8.,4.,9.], 'high_rating':[True,False,True], 'completed':[True,False,False], 'dropped':[False,True,False]})
    def test_memberships_deduplicate_within_drama(self):
        expanded=memberships(self.fixture(),'genres')
        self.assertEqual(len(expanded),3)
        summary=grouped_summary(expanded,'genres')
        self.assertEqual(summary.loc['Drama','dramas'],2)
        self.assertEqual(summary.loc['Comedy','dramas'],1)
        self.assertEqual(summary.loc['Drama','high_rating_pct'],50)
        self.assertEqual(summary.loc['Drama','drop_pct'],50)
    def test_missing_rating_excluded_from_rating_denominator(self):
        frame=self.fixture()
        frame.loc[1,'my_rating']=float('nan')
        summary=grouped_summary(memberships(frame,'genres'),'genres')
        self.assertEqual(summary.loc['Drama','rated'],1)
        self.assertEqual(summary.loc['Drama','high_rating_pct'],100)
        self.assertEqual(summary.loc['Drama','dramas'],2)
    def test_correlations_skip_small_sample_and_constants(self):
        frame=self.fixture().assign(public_rating=8.)
        result=correlations(frame,'public_rating')
        self.assertEqual(result.paired_n,3)
        self.assertTrue(pd.isna(result.pearson))
        larger=pd.concat([frame]*5,ignore_index=True)
        self.assertTrue(pd.isna(correlations(larger,'public_rating').spearman))
