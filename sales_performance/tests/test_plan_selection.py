"""Regression coverage for independent plans sharing header dimensions."""

import unittest
from unittest.mock import patch

import frappe

from sales_performance.services.analysis_engine import selected_target_item_codes
from sales_performance.services.incentive_engine import combine_plan_months
from sales_performance.services.plan_selection import applicable_plans


class TestPlanSelection(unittest.TestCase):
	def plan(self, name, status="Approved", version=1):
		return frappe._dict(name=name, status=status, planning_version=version,
			sales_person="Alex", territory="North", target_source="Manual")

	def test_independent_approved_plans_are_additive(self):
		plans = [self.plan("First"), self.plan("Second"),
			self.plan("Old revision", "Superseded"), self.plan("Draft revision", "Calculated", 3)]
		selected = applicable_plans(plans)
		self.assertEqual([p.name for p in selected], ["First", "Second"])
		rows = [dict(parent=p.name, row_key="row", sales_person="Alex", item_code="Item")
			for p in selected]
		months = {(p.name, "row"): {7: {"target_qty": qty, "target_amount": qty * 10}}
			for p, qty in zip(selected, (20, 30))}
		combined = combine_plan_months(rows, months)
		self.assertEqual(len(combined), 1)
		self.assertEqual(combined[("Alex", "", "Item", "")]["months"][7],
			{"target_qty": 50, "target_amount": 500})

	def test_item_scope_includes_both_approved_plans(self):
		plans = [self.plan("First"), self.plan("Second")]
		def get_all(doctype, **kwargs):
			if doctype == "Sales Target Planning":
				return plans
			self.assertEqual(set(kwargs["filters"]["parent"][1]), {"First", "Second"})
			if doctype == "Item Group Growth Rule":
				return []
			return [frappe._dict(parent=p.name, item_code=p.name, item_group="Group") for p in plans]
		with patch.object(frappe, "get_all", side_effect=get_all):
			self.assertEqual(selected_target_item_codes("Company", "2026"), ["First", "Second"])

	def test_provisional_fallback_keeps_latest_per_scope(self):
		plans = [self.plan("Old", "Calculated"), self.plan("New", "Under Review", 2),
			self.plan("Cancelled", "Cancelled", 4)]
		self.assertEqual([p.name for p in applicable_plans(plans)], ["New"])
		self.assertEqual(applicable_plans([]), [])
