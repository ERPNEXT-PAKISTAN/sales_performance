"""Proposal allocations must scope actuals as well as target totals."""
import unittest
from unittest.mock import patch

import frappe
from sales_performance.services.plan_selection import target_rows, target_sales_condition
from sales_performance.services.personal_sales import get_people
from sales_performance.services.analysis_engine import fetch_sales_by_dimension, fetch_monthly_sales


class TestProposalScope(unittest.TestCase):
    def test_saved_rows_inherit_missing_dimensions_only(self):
        plan = frappe._dict(name='Plan', status='Approved', sales_person='Parent', territory='North', customer_group='Market')
        rows = [frappe._dict(parent='Plan', sales_person='Alice', item_code='A'),
                frappe._dict(parent='Plan', sales_person='', territory='South', customer_group='Export', item_code='B')]
        with patch.object(frappe, 'get_all', side_effect=[[plan], rows]):
            result = target_rows('Company', '2026')
        self.assertEqual(result[0].sales_person, 'Alice')
        self.assertEqual(result[0].territory, 'North')
        self.assertEqual(result[1].sales_person, 'Parent')
        self.assertEqual(result[1].customer_group, 'Export')

    def test_scope_keeps_person_item_group_pairs_and_deduplicates(self):
        rows = [dict(sales_person='Alice', item_code='A', customer_group='Market'),
                dict(sales_person='Bob', item_code='B', customer_group='Export')]
        values = {}
        condition = target_sales_condition(rows + rows, values)
        self.assertEqual(condition.count('sii.item_code in'), 2)
        self.assertEqual(values['target_items_0'], ('A',))
        self.assertEqual(values['target_person_0'], 'Alice')
        self.assertEqual(values['target_group_1'], 'Export')
        self.assertEqual(target_sales_condition([], {}), '1=0')

    def test_all_dimensions_and_trends_apply_allocated_scope(self):
        db = unittest.mock.Mock()
        rows = [dict(sales_person='Alice', item_code='A', customer_group='Market')]
        with patch.object(frappe, 'db', db, create=True):
            fetch_sales_by_dimension('Company', '2026-01-01', '2026-12-31', 'territory', _target_rows=rows)
            fetch_monthly_sales('Company', '2026-01-01', '2026-12-31', _target_rows=rows)
        for call in db.sql.call_args_list:
            sql, values = call.args
            self.assertIn('st.sales_person = %(target_person_0)s', sql)
            self.assertIn('allocated_percentage', sql)
            self.assertEqual(values['target_person_0'], 'Alice')

    def test_personal_options_intersect_targets_and_access(self):
        rows = [frappe._dict(sales_person=p) for p in ('Alice', 'Bob')]
        with patch('sales_performance.services.personal_sales.scope', return_value=['Alice', 'Unplanned']), \
             patch('sales_performance.services.plan_selection.target_rows', return_value=rows), \
             patch.object(frappe, 'get_all', return_value=['Alice']) as get_all:
            self.assertEqual(get_people('Company', '2026'), ['Alice'])
        self.assertEqual(get_all.call_args.kwargs['filters']['name'], ['in', ['Alice']])
