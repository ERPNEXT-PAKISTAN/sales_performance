import unittest
from unittest.mock import patch
from datetime import date

import frappe
from sales_performance.services import access
from sales_performance.services.analysis_engine import summarize_payout_details
from sales_performance.services.incentive_engine import apply_scheme_payout
from sales_performance.services.payout_guard import overlaps
from sales_performance.services.personal_sales import pace


class TestPersonalScope(unittest.TestCase):
    def setUp(self):
        translate = patch.object(access, "_", side_effect=lambda text: text)
        translate.start()
        self.addCleanup(translate.stop)

    def test_self_scope_and_cross_person_and_company_requests(self):
        links = [frappe._dict(company='One', sales_person='Alice', include_team=0)]
        def reject(message, exception):
            raise exception(message)
        with patch.object(access, 'is_admin', return_value=False), patch.object(access, 'assignments', return_value=links), patch.object(access.frappe, 'throw', side_effect=reject):
            self.assertEqual(access.scope('One', user='alice'), ['Alice'])
            self.assertEqual(access.scope('One', 'Alice', user='alice'), ['Alice'])
            with self.assertRaises(frappe.PermissionError):
                access.scope('One', 'Bob', user='alice')
            with self.assertRaises(frappe.PermissionError):
                access.scope('Two', user='alice')

    def test_unmapped_user_has_no_fallback_to_all(self):
        with patch.object(access, 'is_admin', return_value=False), patch.object(access, 'assignments', return_value=[]), patch.object(access.frappe, 'throw', side_effect=frappe.PermissionError):
            with self.assertRaises(frappe.PermissionError):
                access.scope('One', user='unmapped')

    def test_admin_all_and_requested_scope(self):
        with patch.object(access, 'is_admin', return_value=True):
            self.assertIsNone(access.scope('One', user='admin'))
            self.assertEqual(access.scope('One', 'Alice', user='admin'), ['Alice'])


class TestPayoutAggregation(unittest.TestCase):
    def test_more_than_100_documents_are_in_totals(self):
        docs = [dict(name=f'P{i}', docstatus=1, payment_status='Paid', period='Monthly') for i in range(120)]
        items = [dict(parent=d['name'], sales_person='Alice', period='January', incentive_amount=5) for d in docs]
        result = summarize_payout_details(docs, items, {'month':1}, ['Alice'])
        self.assertEqual(result['totals']['paid'], 600)
        self.assertEqual(result['totals']['count'], 120)
        self.assertEqual(len(result['documents']), 100)
        self.assertTrue(result['has_more'])

    def test_mixed_payout_never_exposes_other_person_amounts(self):
        docs=[dict(name='Mixed', docstatus=1, payment_status='Not Paid', period='Monthly', total_incentive_amount=999)]
        items=[dict(parent='Mixed', sales_person='Alice', period='January', customer_group='Market', incentive_amount=10),
               dict(parent='Mixed', sales_person='Bob', period='January', customer_group='Market', incentive_amount=90),
               dict(parent='Mixed', sales_person='Alice', period='February', customer_group='Market', incentive_amount=20)]
        result=summarize_payout_details(docs,items,{'month':1,'customer_groups':{'Market'}},['Alice'])
        self.assertEqual(result['totals']['accrued'],10)
        self.assertEqual(result['documents'][0]['total_incentive_amount'],10)
        self.assertEqual(result['by_sales_person'][0]['dimension'],'Alice')

    def test_no_matching_rows_returns_no_document_metadata(self):
        result=summarize_payout_details([dict(name='Other',docstatus=1)], [dict(parent='Other',sales_person='Bob',incentive_amount=90)],allowed=['Alice'])
        self.assertEqual(result['documents'],[])
        self.assertEqual(result['totals']['accrued'],0)


class TestEntitlementAndPace(unittest.TestCase):
    def test_overlap_quarter_month_and_wildcard_item(self):
        left=dict(sales_person='Alice',period='Q1',customer_group='Market')
        right=dict(sales_person='Alice',period='February',customer_group='Market',item_code='A')
        self.assertTrue(overlaps(left,right))
        self.assertFalse(overlaps(left,dict(right,period='April')))
        self.assertFalse(overlaps(left,dict(right,sales_person='Bob')))
        self.assertFalse(overlaps(dict(left,item_code='B'),right))

    def test_rounding_cannot_unlock_incentive(self):
        result=apply_scheme_payout(100,99.96,100,200,[{'min_achievement_percent':100,'min_incentive_percent':5}], 'Qty Achievement','Amount')
        self.assertEqual(result['qty_achievement_percent'],100)
        self.assertEqual(result['incentive_amount'],0)

    def test_pace_and_ended_month(self):
        with patch('sales_performance.services.personal_sales.getdate',return_value=date(2026,1,16)):
            result=pace({'target_amount':3100,'actual_amount':1000},date(2026,1,1),date(2026,1,31))
            self.assertEqual(result['status'],'Behind pace')
            self.assertEqual(result['remaining_days'],16)
            self.assertEqual(result['remaining'],2100)
        with patch('sales_performance.services.personal_sales.getdate',return_value=date(2026,2,1)):
            result=pace({'target_amount':100,'actual_amount':0},date(2026,1,1),date(2026,1,31))
            self.assertIsNone(result['daily_needed'])

class TestDocumentAccess(unittest.TestCase):
    def test_controller_allows_scoped_reads_but_denies_salesperson_writes(self):
        doc=frappe._dict(doctype='Sales Performance Update',company='One',sales_person='Alice')
        with patch.object(access,'is_admin',return_value=False), patch.object(access,'scope',return_value=['Alice']), patch.object(access.frappe,'get_roles',return_value=['Sales User']):
            self.assertTrue(access.document_permission(doc,user='alice',ptype='read'))
            self.assertFalse(access.document_permission(doc,user='alice',ptype='write'))
            self.assertFalse(access.document_permission(frappe._dict(doc,sales_person='Bob'),user='alice',ptype='read'))

    def test_combined_documents_require_every_child_to_be_authorized(self):
        doc=frappe._dict(doctype='Sales Target Planning',company='One',sales_person='Alice',proposal_details=[frappe._dict(sales_person='Bob')])
        with patch.object(access,'is_admin',return_value=False), patch.object(access,'scope',return_value=['Alice']):
            self.assertFalse(access.document_permission(doc,user='alice',ptype='read'))
        with patch.object(access,'is_admin',return_value=False), patch.object(access,'scope',return_value=['Alice','Bob']):
            self.assertTrue(access.document_permission(doc,user='manager',ptype='read'))
