import json
import unittest
from pathlib import Path
from unittest.mock import patch
from accounting import debt_accounts, ttm_income
import valuation

DATA=json.loads((Path(__file__).parent/'fixtures'/'dart_2026_h1.json').read_text())

class FilingRegressions(unittest.TestCase):
    def test_debt_totals_against_reviewed_filing_rows(self):
        expected={'003240':5883881127,'066620':4051751090,'024830':None,'000590':1077164515,'029530':4918946040,'003960':717893820645,'053700':546647334390,'103140':1265188884673}
        for ticker,total in expected.items():
            with self.subTest(ticker=ticker):
                self.assertEqual(debt_accounts(DATA[ticker]['current'])['value'],total)

    def test_ttm_parent_or_standalone_income(self):
        expected={'003240':118699173246,'066620':110626936197,'024830':13610543294,'000590':23487443467,'029530':38830635540,'003960':-205695930709,'053700':9171008650,'323410':544655000000,'055550':5376891000000,'103140':201885939463}
        for ticker,total in expected.items():
            d=DATA[ticker]
            with self.subTest(ticker=ticker):
                b=ttm_income(d['current'],d['annual'],2026,'H1',d['fs_div'],2025,d['fs_div'])
                self.assertEqual(b[b['earnings_key']]['ttm'],total)

    def test_sajo_common_shares_exclude_preferred(self):
        with patch.object(valuation,'dart',return_value=DATA['003960']['shares']):
            self.assertEqual(valuation.shares('test','test',2026,'11012'),8940461)

if __name__=='__main__':unittest.main()
