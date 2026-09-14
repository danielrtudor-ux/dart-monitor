import json
import unittest
from datetime import date
from pathlib import Path

from valuation_adjustments import applicable_review, apply_note_balance, owner_accounts, parse_fx_csv

ROOT=Path(__file__).parent.parent
DATA=json.loads((Path(__file__).parent/'fixtures'/'dart_2026_h1.json').read_text())
REVIEWS=json.loads((ROOT/'note_review_facts.json').read_text())


class NoteAdjustmentTests(unittest.TestCase):
    def test_review_requires_exact_receipt_and_statement_basis(self):
        d=DATA['024830']
        self.assertEqual(applicable_review('024830',d['current'],d['fs_div'],REVIEWS)['debt_total'],0)
        self.assertEqual(applicable_review('024830',d['current'],'CFS',REVIEWS),{})
        changed=[dict(r,rcept_no='99999999999999') for r in d['current']]
        self.assertEqual(applicable_review('024830',changed,d['fs_div'],REVIEWS),{})

    def test_pledged_deposit_reduces_net_cash(self):
        current={'cash_like':185076227734,'debt':None,'debt_evidence':{'status':'unknown','identified_sum':0}}
        adjusted=apply_note_balance(current,REVIEWS['024830'])
        self.assertEqual(adjusted['debt'],0)
        self.assertEqual(adjusted['net_cash'],149776227734)
        self.assertEqual(adjusted['face_net_cash']-adjusted['net_cash'],35300000000)

    def test_noncontrolling_interest_is_included_as_ev_proxy(self):
        rows=[{'sj_div':'BS','account_id':'ifrs-full_NoncontrollingInterests','account_nm':'비지배지분','thstrm_amount':'33,387,668,189'}]
        self.assertEqual(owner_accounts(rows,'CFS')['nci_ev_proxy'],33387668189)

    def test_fx_observation_must_be_recent(self):
        csv='observation_date,DEXKOUS\n2026-09-04,1346.51\n'
        self.assertTrue(parse_fx_csv(csv,date(2026,9,15))['supported'])
        self.assertFalse(parse_fx_csv(csv,date(2026,9,20))['supported'])


if __name__=='__main__':unittest.main()
