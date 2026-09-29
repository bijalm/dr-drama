"""Regression checks for non-destructive spreadsheet cleaning."""

import json
import unittest
import pandas as pd

from dr_drama.data.import_excel import clean_records, number, list_value


class ExcelCleaningTests(unittest.TestCase):
    def record(self, **changes):
        return {'title': 'Example', 'my_rating': 6.7, 'status': 'Complete', 'favorite': 'Y', 'would_rewatch': ' No ', 'personal_notes': 'Keep spacing.  ', 'source_sheet': 'Fixture', 'source_excel_row': 2, **changes}

    def test_personal_values_preserved_and_categories_normalized(self):
        frame, report = clean_records([self.record()])
        self.assertEqual(frame.loc[0, 'my_rating'], 6.7)
        self.assertEqual(frame.loc[0, 'personal_notes'], 'Keep spacing.  ')
        self.assertEqual(frame.loc[0, 'status'], 'completed')
        self.assertEqual(frame.loc[0, 'favorite'], 'yes')
        self.assertEqual(frame.loc[0, 'would_rewatch'], 'no')
        self.assertTrue(pd.isna(frame.loc[0, 'public_rating']))

    def test_invalid_rating_is_not_rounded_or_lost(self):
        frame, report = clean_records([self.record(my_rating='6.75')])
        self.assertTrue(pd.isna(frame.loc[0, 'my_rating']))
        self.assertEqual(frame.loc[0, 'original_my_rating'], '6.75')
        self.assertTrue(any(i['field'] == 'my_rating' for i in report['issues']))

    def test_missing_and_unknown_categories_are_not_guessed(self):
        frame, report = clean_records([self.record(favorite=None, status='Maybe')])
        self.assertTrue(pd.isna(frame.loc[0, 'favorite']))
        self.assertEqual(frame.loc[0, 'status'], 'Maybe')
        self.assertTrue(any(i['field'] == 'status' for i in report['issues']))

    def test_duplicate_detection_does_not_remove_rows(self):
        frame, report = clean_records([self.record(title='Example!'), self.record(title=' example ', source_excel_row=3)])
        self.assertEqual(len(frame), 2)
        self.assertEqual(len(report['duplicate_title_groups']), 1)
        self.assertEqual(frame.loc[1, 'title'], ' example ')

    def test_external_values_and_unknown_columns_preserved(self):
        frame, report = clean_records([self.record(genres='Romance; Comedy', main_cast='["A", "B"]', number_of_episodes='16', public_rating='8.2', source_extra='unchanged')])
        self.assertEqual(json.loads(frame.loc[0, 'genres']), ['Romance', 'Comedy'])
        self.assertEqual(json.loads(frame.loc[0, 'main_cast']), ['A', 'B'])
        self.assertEqual(frame.loc[0, 'number_of_episodes'], 16)
        self.assertEqual(frame.loc[0, 'public_rating'], 8.2)
        self.assertEqual(frame.loc[0, 'source_extra'], 'unchanged')

    def test_numeric_validation(self):
        self.assertEqual(number('1,234', 'public_vote_count'), 1234)
        for value in ['nan', 'inf', '-1', '6.75', '11']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                number(value, 'my_rating')
        with self.assertRaises(ValueError):
            number('16.5', 'number_of_episodes')


if __name__ == '__main__':
    unittest.main()
