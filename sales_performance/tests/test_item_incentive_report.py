"""Regression coverage for item display versus payable incentive entitlement."""

import unittest
from copy import deepcopy
from unittest.mock import patch

from sales_performance.services.achievement_engine import compute_metrics
from sales_performance.services.incentive_engine import (
	allocate_item_incentives, dashboard_totals, group_dashboard_rows, grouped_incentive_rows,
)
from sales_performance.sales_performance.report.sales_target_achievement import sales_target_achievement as report
from sales_performance.sales_performance.report.sales_target_monthly_performance import sales_target_monthly_performance as monthly_report


class TestItemIncentiveReport(unittest.TestCase):
	slabs = [{"min_achievement_percent": 100, "min_incentive_percent": 2}]

	def row(self, item, target, actual, **scope):
		return {
			**compute_metrics(target, actual, target * 10, actual * 10),
			"item_code": item, "sales_person": "Kashif", "period": "January",
			"month_number": 1, "customer_group": "Market", "territory": "Faisalabad",
			**scope,
		}

	def test_zero_sales_reference_gets_no_payout_and_item_metrics_are_preserved(self):
		rows = [self.row("Eye Pad", 100, 0), self.row("A", 1000, 6100), self.row("B", 1000, 6021)]
		original = deepcopy(rows)
		out = allocate_item_incentives(rows, self.slabs, "Qty Achievement", "Qty")
		self.assertEqual(rows, original)
		self.assertEqual(out[0]["incentive_amount"], 0)
		self.assertEqual(sum(row["incentive_amount"] for row in out), 200)
		for before, after in zip(rows, out):
			for field in ("target_qty", "actual_qty", "variance_qty", "qty_achievement_percent", "target_amount", "actual_amount"):
				self.assertEqual(before[field], after[field])

	def test_418_scope_and_each_salespersons_total_are_preserved(self):
		rows = [
			self.row("Zero", 100, 0), self.row("A", 1000, 6100), self.row("B", 1000, 6021),
			self.row("C", 915, 11054, sales_person="Yasir"),
			self.row("D", 2553, 3310, sales_person="Sufian"),
		]
		out = allocate_item_incentives(rows, self.slabs, "Qty Achievement", "Qty")
		self.assertEqual(sum(row["incentive_amount"] for row in out), 418)
		for group in grouped_incentive_rows(rows, self.slabs, "Qty Achievement", "Qty"):
			self.assertEqual(sum(row["incentive_amount"] for row in out if row["sales_person"] == group["sales_person"]), group["incentive_amount"])

	def test_item_surplus_does_not_pay_when_salesperson_misses(self):
		out = allocate_item_incentives([self.row("A", 100, 200), self.row("B", 300, 0)], self.slabs, "Qty Achievement", "Qty")
		self.assertEqual(sum(row["incentive_amount"] for row in out), 0)

	def test_amount_basis_and_rounding_are_stable_when_rows_reordered(self):
		rows = [self.row("A", 10, 17), self.row("B", 10, 17), self.row("C", 10, 17)]
		forward = allocate_item_incentives(rows, self.slabs, "Amount Achievement", "Amount")
		reverse = allocate_item_incentives(rows[::-1], self.slabs, "Amount Achievement", "Amount")
		self.assertEqual({r["item_code"]: r["incentive_amount"] for r in forward}, {r["item_code"]: r["incentive_amount"] for r in reverse})
		self.assertEqual(sum(r["incentive_amount"] for r in forward), 4)
		self.assertTrue(all(r["incentive_on_qty"] == 0 for r in forward))

	def test_customer_groups_and_periods_do_not_offset_each_other(self):
		rows = [self.row("A", 100, 200), self.row("B", 1000, 0, customer_group="Other"), self.row("C", 1000, 0, period="February")]
		out = allocate_item_incentives(rows, self.slabs, "Qty Achievement", "Qty")
		self.assertEqual([r["incentive_amount"] for r in out], [2, 0, 0])

	def test_report_has_only_item_rows_and_one_set_of_performance_columns(self):
		rows = [self.row("Eye Pad", 100, 0), self.row("A", 1000, 11121)]
		with patch.object(report, "_", side_effect=lambda text: text), patch.object(report, "collect_period_incentive_rows", return_value=rows), patch.object(report, "scheme_settings", return_value=(self.slabs, "Qty Achievement", "Qty")):
			columns, result, message, _, _, skip_total = report.execute({"company": "Test", "fiscal_year": "2026"})
		data = result[:-1]
		self.assertTrue(skip_total)
		self.assertEqual(result[-1]["actual_qty"], 11121)
		self.assertEqual(result[-1]["qty_achievement_percent"], 1011.0)
		self.assertAlmostEqual(result[-1]["incentive_amount"], 202.42, places=2)
		self.assertEqual(len(data), 2)
		self.assertTrue(all(row.get("item_code") for row in data))
		self.assertFalse(any("group" in col["fieldname"] and col["fieldname"] not in ("item_group", "customer_group") for col in columns))
		self.assertAlmostEqual(sum(row["incentive_amount"] for row in data), 202.42, places=2)
		self.assertIn("item", message.lower())
		self.assertEqual(allocate_item_incentives([], self.slabs, "Qty Achievement", "Qty"), [])

	def test_band_filter_preserves_allocations_and_totals_only_visible_rows(self):
		slabs = [{"min_achievement_percent": 100, "max_achievement_percent": 150,
			"min_incentive_percent": 2, "max_incentive_percent": 4}]
		rows = [
			self.row("Min item", 1000, 1250, sales_person="Min person"),
			self.row("Max item", 1000, 1700, sales_person="Max person"),
			self.row("Missed item", 100, 0, sales_person="Max person"),
		]
		with patch.object(report, "_", side_effect=lambda text: text), patch.object(report, "collect_period_incentive_rows", return_value=rows), patch.object(report, "scheme_settings", return_value=(slabs, "Qty Achievement", "Qty")):
			for band, items, payout, target, rate in (
				("All", 3, 33, 2100, None),
				("Min", 1, 5, 1000, 2),
				("Max", 1, 28, 1000, 4),
				("Not Achieve", 1, 0, 100, 0),
			):
				with self.subTest(band=band):
					columns, result, *_ = report.execute({"company": "Test", "fiscal_year": "2026", "incentive_band": band})
					self.assertIn("incentive_rate_percent", [col["fieldname"] for col in columns])
					self.assertEqual(len(result) - 1, items)
					self.assertEqual(result[-1]["incentive_amount"], payout)
					self.assertEqual(result[-1]["target_qty"], target)
					self.assertNotIn("incentive_rate_percent", result[-1])
					if rate is not None:
						self.assertEqual(result[0]["incentive_rate_percent"], rate)

	def test_dashboard_item_groups_and_band_cards_reconcile_with_item_report(self):
		slabs = [{"min_achievement_percent": 100, "max_achievement_percent": 150,
			"min_incentive_percent": 2, "max_incentive_percent": 4}]
		rows = [
			self.row("Unrelated", 100, 0, sales_person="Max person", item_group="Other"),
			self.row("Max item", 1000, 1700, sales_person="Max person", item_group="Products"),
			self.row("Min item", 1000, 1250, sales_person="Min person", item_group="Products"),
		]
		report_rows = allocate_item_incentives(rows, slabs, "Qty Achievement", "Qty")
		items = group_dashboard_rows(rows, "item", slabs, "Qty Achievement", "Qty")
		groups = group_dashboard_rows(rows, "item_group", slabs, "Qty Achievement", "Qty")
		totals = dashboard_totals(rows, slabs, "Qty Achievement", "Qty")
		self.assertEqual(next(r for r in items if r["dimension"] == "Unrelated")["incentive_amount"], 0)
		self.assertEqual(sum(r["incentive_amount"] for r in items), sum(r["incentive_amount"] for r in report_rows))
		self.assertEqual(sum(r["incentive_amount"] for r in groups), totals["incentive_amount"])
		self.assertEqual(totals["min_incentive_amount"] + totals["max_incentive_amount"], totals["incentive_amount"])

	def test_quarterly_monthly_report_scores_combined_period_once(self):
		from datetime import date
		rows = [
			self.row("A", 100, 200, period="January", month_number=1),
			self.row("A", 100, 0, period="February", month_number=2),
		]
		with patch.object(monthly_report, "collect_period_incentive_rows", return_value=rows), patch.object(monthly_report, "scheme_settings", return_value=(self.slabs, "Qty Achievement", "Qty")), patch.object(monthly_report, "fiscal_year_dates", return_value=(date(2026, 1, 1), date(2026, 12, 31))), patch.object(monthly_report, "getdate", side_effect=lambda value=None: value if isinstance(value, date) else date.fromisoformat(value) if value else date(2026, 3, 1)):
			result = monthly_report.get_data(monthly_report.frappe._dict({"company": "Test", "fiscal_year": "2026", "period": "Quarterly", "quarter": 1}))
		self.assertEqual(result[0]["target_qty"], 200)
		self.assertEqual(result[0]["actual_qty"], 200)
		self.assertEqual(result[0]["incentive_amount"], 2)
