import copy
import unittest
from accounting import ttm_income, debt_accounts, company_type, income
from postprocess_valuation import process


def row(account='ifrs-full_Revenue', value='1000', **kw):
    r={'sj_div':'IS','account_id':account,'account_nm':'', 'thstrm_amount':value, 'currency':'KRW'}
    r.update(kw)
    return r


def bridge(current, annual=None, **kw):
    return ttm_income(current, annual or [row()], kw.get('year',2026), kw.get('label','H1'), kw.get('fs','CFS'), kw.get('ay',2025), kw.get('afs','CFS'))


class IncomeTests(unittest.TestCase):
    def test_h1_cumulative_not_quarter(self):
        b=bridge([row(value='300',thstrm_add_amount='650',frmtrm_add_amount='500',frmtrm_amount='9999',frmtrm_q_amount='200')])
        self.assertEqual(b['revenue']['ttm'],1150)
        self.assertEqual(b['revenue']['current_cumulative']['source']['field'],'thstrm_add_amount')

    def test_q3_cumulative(self):
        self.assertEqual(bridge([row(value='50',thstrm_add_amount='900',frmtrm_add_amount='700')],label='Q3')['revenue']['ttm'],1200)

    def test_missing_cumulative_never_uses_three_month_amount(self):
        b=bridge([row(value='300',frmtrm_add_amount='500')])['revenue']
        self.assertIsNone(b['ttm'])
        self.assertEqual(b['used'],1000)
        self.assertEqual(b['basis'],'FY2025 fallback')

    def test_zero_and_loss_are_values(self):
        self.assertEqual(bridge([row(thstrm_add_amount='0',frmtrm_add_amount='1200')])['revenue']['ttm'],-200)

    def test_basis_mismatch(self):
        b=bridge([row(thstrm_add_amount='650',frmtrm_add_amount='500')],afs='OFS')['revenue']
        self.assertIsNone(b['ttm'])
        self.assertIsNone(b['used'])

    def test_wrong_year(self):
        self.assertIsNone(bridge([row(thstrm_add_amount='650',frmtrm_add_amount='500')],ay=2024)['revenue']['ttm'])

    def test_currency_mismatch(self):
        self.assertIsNone(bridge([row(thstrm_add_amount='650',frmtrm_add_amount='500',currency='USD')])['revenue']['ttm'])

    def test_cf_and_sce_cannot_supply_income(self):
        self.assertIsNone(income([row(sj_div='CF'),row(sj_div='SCE')],'thstrm_amount')['revenue']['value'])

    def test_conflicting_duplicate_is_rejected(self):
        self.assertIsNone(income([row(),row(value='2000',sj_div='CIS')],'thstrm_amount')['revenue']['value'])

    def test_parent_never_mixed_with_total(self):
        annual=[row('ifrs-full_ProfitLossAttributableToOwnersOfParent','100'),row('ifrs-full_ProfitLoss','120')]
        current=[row('ifrs-full_ProfitLossAttributableToOwnersOfParent','10',thstrm_add_amount='60'),row('ifrs-full_ProfitLoss','15',thstrm_add_amount='70',frmtrm_add_amount='50')]
        b=bridge(current,annual)
        self.assertIsNone(b['pni']['ttm'])
        self.assertEqual(b['earnings_key'],'pni')
        self.assertEqual(b['pni']['used'],100)
        self.assertEqual(b['ni']['ttm'],140)

    def test_fy_uses_full_year(self):
        self.assertEqual(bridge([row(value='1200')],label='FY',year=2025)['revenue']['ttm'],1200)


class DebtTests(unittest.TestCase):
    def debt(self,account,value,**kw):
        return row(account,value,sj_div='BS',**kw)

    def test_absent_is_unknown(self):
        d=debt_accounts([])
        self.assertIsNone(d['value'])
        self.assertEqual(d['status'],'unknown')

    def test_single_zero_is_not_proof(self):
        self.assertIsNone(debt_accounts([self.debt('ifrs-full_ShorttermBorrowings','0')])['value'])

    def test_explicit_zero_total(self):
        d=debt_accounts([self.debt('ifrs-full_Borrowings','0')])
        self.assertEqual(d['value'],0)
        self.assertEqual(d['status'],'explicit_zero')

    def test_leases_included(self):
        d=debt_accounts([self.debt('ifrs-full_ShorttermBorrowings','100'),self.debt('ifrs-full_LeaseLiabilitiesCurrent','20'),self.debt('ifrs-full_LeaseLiabilitiesNoncurrent','30')])
        self.assertEqual(d['value'],150)

    def test_aggregates_not_double_counted(self):
        d=debt_accounts([self.debt('ifrs-full_CurrentBorrowings','100'),self.debt('ifrs-full_ShorttermBorrowings','80'),self.debt('ifrs-full_CurrentPortionOfLongtermBorrowings','20')])
        self.assertEqual(d['value'],100)

    def test_unrecognized_positive_debt_suppresses_total(self):
        d=debt_accounts([self.debt('ifrs-full_ShorttermBorrowings','100'),self.debt('custom','30',account_nm='전환사채')])
        self.assertIsNone(d['value'])
        self.assertEqual(d['identified_sum'],100)
        self.assertEqual(d['status'],'unrecognized_accounts')

    def test_missing_candidate_amount_is_unresolved(self):
        self.assertIsNone(debt_accounts([self.debt('custom','-',account_nm='차입부채')])['value'])


class QualityTests(unittest.TestCase):
    def test_financial_classification(self):
        for t,n in [('323410','카카오뱅크'),('055550','신한지주'),('139130','iM금융지주')]:
            self.assertEqual(company_type(t,n)[0],'financial')
        self.assertEqual(company_type('999999','Some Corp','64992')[0],'financial')
        self.assertEqual(company_type('058650','세아홀딩스')[0],'holding')

    def test_postprocessing_is_idempotent(self):
        d={'engine_version':'1.2-ttm','results':[{'ticker':'323410','company':'카카오뱅크','fundamentals':{'debt_latest':None,'debt_status':'unknown'},'ratios':{'ex_net_cash_pe':10},'warnings':[]}]}
        a=process(copy.deepcopy(d))
        self.assertEqual(a,process(copy.deepcopy(a)))
        self.assertIsNone(a['results'][0]['ratios']['ex_net_cash_pe'])
        self.assertEqual(a['engine_version'],'1.2-ttm')

    def test_unknown_debt_not_zero(self):
        d={'results':[{'ticker':'003240','company':'태광산업','fundamentals':{'debt_latest':0,'debt_status':'no_standard_accounts_found','net_cash_latest':100},'ratios':{'ex_net_cash_pe':1},'wacc':{},'dcf':{}}]}
        r=process(d)['results'][0]
        self.assertIsNone(r['fundamentals']['debt_latest'])
        self.assertIsNone(r['fundamentals']['net_cash_latest'])
        self.assertIsNone(r['ratios']['ex_net_cash_pe'])

if __name__=='__main__':unittest.main()
