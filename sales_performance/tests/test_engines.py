"""Engine and planning-rule tests. Pure functions do not touch production data."""

import unittest
from types import SimpleNamespace

from sales_performance.services.achievement_engine import achievement_percent, compute_metrics
from sales_performance.services.distribution_engine import (
	custom_percentage,
	equal_half_yearly,
	equal_monthly,
	equal_quarterly,
	reconcile_to_total,
	same_month_previous_year,
)
from sales_performance.services.growth_engine import (
	apply_growth,
	growth_rule_covers_item_group,
	item_group_in_subtree,
	resolve_growth_percent,
)
from sales_performance.services.historical_sales import rollup_monthly
from sales_performance.services.planning_engine import apply_row_override, complete_monthly_row
from sales_performance.services.pricing_engine import average_selling_price
from sales_performance.services.target_sync import _match_child, planning_key


class TestGrowth(unittest.TestCase):
	def test_positive_growth(self):
		self.assertEqual(apply_growth(100, 10, precision=2), 110)

	def test_negative_growth(self):
		self.assertEqual(apply_growth(100, -10, precision=2), 90)

	def test_zero_growth(self):
		self.assertEqual(apply_growth(100, 0, precision=2), 100)

	def test_rule_priority_and_children(self):
		rules = [
			{"item_group": "All", "growth_percent": 5, "apply_to_children": 1, "priority": 1},
			{"item_group": "GI Coil", "growth_percent": 15, "apply_to_children": 1, "priority": 10},
		]
		pct, src = resolve_growth_percent("GI Coil 0.6", rules, ["GI Coil 0.6", "GI Coil", "All"])
		self.assertEqual(pct, 15)
		self.assertEqual(src, "GI Coil")

	def test_item_group_subtree_and_rule_scope(self):
		ancestors = ["GI Coil 0.6", "GI Coil", "All"]
		self.assertTrue(item_group_in_subtree("GI Coil 0.6", "GI Coil", ancestors))
		self.assertTrue(item_group_in_subtree("GI Coil", "GI Coil", ancestors))
		self.assertFalse(item_group_in_subtree("CR Coil", "GI Coil", ["CR Coil", "All"]))
		rules = [{"item_group": "GI Coil", "growth_percent": 10, "apply_to_children": 1, "priority": 1}]
		self.assertTrue(growth_rule_covers_item_group("GI Coil 0.6", rules, ancestors))
		self.assertFalse(growth_rule_covers_item_group("CR Coil", rules, ["CR Coil", "All"]))
		exact_only = [{"item_group": "GI Coil", "growth_percent": 10, "apply_to_children": 0, "priority": 1}]
		self.assertFalse(growth_rule_covers_item_group("GI Coil 0.6", exact_only, ancestors))
		self.assertTrue(growth_rule_covers_item_group("GI Coil", exact_only, ["GI Coil", "All"]))


class TestHistoricalNetting(unittest.TestCase):
	def test_returns_reduce_qty_and_amount(self):
		rows = [
			{
				"sales_person": "SP",
				"territory": "T",
				"item_code": "GI",
				"item_name": "GI Coil",
				"item_group": "GI Coil",
				"customer_group": "Commercial",
				"uom": "Kg",
				"month_number": 1,
				"qty": 100,
				"amount": 24000,
			},
			{
				"sales_person": "SP",
				"territory": "T",
				"item_code": "GI",
				"item_name": "GI Coil",
				"item_group": "GI Coil",
				"customer_group": "Commercial",
				"uom": "Kg",
				"month_number": 1,
				"qty": -20,
				"amount": -4800,
			},
		]
		out = rollup_monthly(rows)
		grain = out[("SP", "T", "GI", "Commercial")]
		self.assertEqual(grain["qty"], 80)
		self.assertEqual(grain["amount"], 19200)
		self.assertEqual(grain["customer_group"], "Commercial")

	def test_item_only_grain_matches_sales_target_report(self):
		rows = [
			{
				"sales_person": "",
				"territory": "",
				"item_code": "GI",
				"item_name": "GI Coil",
				"item_group": "GI Coil",
				"customer_group": "Commercial",
				"uom": "Kg",
				"month_number": 0,
				"qty": 50,
				"amount": 10000,
			},
			{
				"sales_person": "",
				"territory": "",
				"item_code": "GI",
				"item_name": "GI Coil",
				"item_group": "GI Coil",
				"customer_group": "Commercial",
				"uom": "Kg",
				"month_number": 0,
				"qty": 30,
				"amount": 6000,
			},
		]
		out = rollup_monthly(rows)
		self.assertEqual(len(out), 1)
		grain = out[("", "", "GI", "Commercial")]
		self.assertEqual(grain["qty"], 80)
		self.assertEqual(grain["amount"], 16000)

	def test_sales_person_rows_stay_separate(self):
		rows = [
			{
				"sales_person": "Ali",
				"territory": "",
				"item_code": "GI",
				"item_name": "GI Coil",
				"item_group": "GI Coil",
				"customer_group": "Commercial",
				"uom": "Kg",
				"month_number": 0,
				"qty": 50,
				"amount": 10000,
			},
			{
				"sales_person": "Sara",
				"territory": "",
				"item_code": "GI",
				"item_name": "GI Coil",
				"item_group": "GI Coil",
				"customer_group": "Commercial",
				"uom": "Kg",
				"month_number": 0,
				"qty": 30,
				"amount": 6000,
			},
		]
		out = rollup_monthly(rows)
		self.assertEqual(len(out), 2)
		self.assertEqual(out[("Ali", "", "GI", "Commercial")]["qty"], 50)
		self.assertEqual(out[("Sara", "", "GI", "Commercial")]["qty"], 30)


class TestPricing(unittest.TestCase):
	def test_previous_year_average(self):
		result = average_selling_price(10000, 2400000)
		self.assertEqual(result["rate"], 240)
		self.assertEqual(result["price_source"], "Previous Year Average")

	def test_average_zero_qty(self):
		result = average_selling_price(0, 100)
		self.assertEqual(result["rate"], 0)
		self.assertTrue(result.get("error"))

	def test_target_amount_is_qty_times_rate(self):
		qty = apply_growth(10000, 15, precision=3)
		self.assertEqual(qty, 11500)
		self.assertEqual(qty * 260, 2990000)


class TestDistribution(unittest.TestCase):
	def test_previous_year_average_buckets(self):
		"""PY 12000 → monthly 1000, quarter 3000, year 12000."""
		rows = equal_monthly(12000, 240000, precision=3, amount_precision=2)
		self.assertEqual(len(rows), 12)
		self.assertAlmostEqual(rows[0]["target_qty"], 1000, places=3)
		self.assertAlmostEqual(sum(r["target_qty"] for r in rows[0:3]), 3000, places=3)
		self.assertAlmostEqual(sum(r["target_qty"] for r in rows), 12000, places=3)
		rows = equal_monthly(12000, 120000, precision=3, amount_precision=2)
		self.assertEqual(len(rows), 12)
		self.assertAlmostEqual(sum(r["target_qty"] for r in rows), 12000, places=3)
		self.assertAlmostEqual(sum(r["target_amount"] for r in rows), 120000, places=2)

	def test_equal_quarterly_sums(self):
		rows = equal_quarterly(12000, 120000, precision=3, amount_precision=2)
		self.assertAlmostEqual(sum(r["target_qty"] for r in rows), 12000, places=3)

	def test_equal_half_yearly_sums(self):
		rows = equal_half_yearly(12000, 120000, precision=3, amount_precision=2)
		self.assertAlmostEqual(sum(r["target_qty"] for r in rows), 12000, places=3)

	def test_custom_percent_must_be_100(self):
		with self.assertRaises(ValueError):
			custom_percentage(100, [10] * 12)

	def test_custom_percent_sums(self):
		percents = [5, 5, 10, 10, 10, 10, 10, 10, 10, 10, 5, 5]
		self.assertEqual(sum(percents), 100)
		rows = custom_percentage(1000, percents, 10000, precision=3, amount_precision=2)
		self.assertAlmostEqual(sum(r["target_qty"] for r in rows), 1000, places=3)

	def test_same_month_previous_year(self):
		prev = {i: 1000 if i == 1 else 0 for i in range(1, 13)}
		prev[1] = 10000
		rows = same_month_previous_year(11500, prev, 15, 11500 * 260, {}, 260, 3, 2)
		self.assertAlmostEqual(sum(r["target_qty"] for r in rows), 11500, places=3)

	def test_reconcile(self):
		self.assertEqual(sum(reconcile_to_total([1, 1, 1], 3.0, 2)), 3.0)


class TestZeroHistory(unittest.TestCase):
	def test_requires_review_reason_constant(self):
		from sales_performance.services.planning_engine import NO_HISTORY_REASON

		self.assertEqual(NO_HISTORY_REASON, "No previous-year sales history")


class TestOverride(unittest.TestCase):
	def test_calculated_unchanged_approved_changes(self):
		row = SimpleNamespace(
			calculated_target_qty=11500,
			approved_target_qty=12000,
			approved_target_rate=260,
			approved_target_amount=0,
			override_percent=0,
		)
		apply_row_override(row)
		self.assertEqual(row.calculated_target_qty, 11500)
		self.assertEqual(row.approved_target_amount, 3120000)
		self.assertAlmostEqual(row.override_percent, 4.3, places=1)


class TestMonthlyRowFields(unittest.TestCase):
	def test_fills_rate_previous_actual_and_variance(self):
		row = {
			"row_key": "abc",
			"sales_person": "Ali",
			"item_code": "GI",
			"item_group": "GI Coil",
			"customer_group": "Commercial",
			"approved_target_rate": 260,
		}
		month = {
			"month": "January",
			"month_number": 1,
			"target_qty": 100,
			"target_amount": 0,
			"target_rate": 0,
			"distribution_percent": 8.3,
		}
		grain = {"month_qty": {1: 90}, "month_amount": {1: 18000}}
		actual = {"month_qty": {1: 80}, "month_amount": {1: 20000}}
		out = complete_monthly_row(row, month, grain, actual)
		self.assertEqual(out["target_rate"], 260)
		self.assertEqual(out["target_amount"], 26000)
		self.assertEqual(out["previous_year_qty"], 90)
		self.assertEqual(out["previous_year_amount"], 18000)
		self.assertEqual(out["actual_qty"], 80)
		self.assertEqual(out["actual_amount"], 20000)
		self.assertEqual(out["qty_variance"], -20)
		self.assertEqual(out["amount_variance"], -6000)
		self.assertEqual(out["qty_achievement_percent"], 80.0)
		self.assertEqual(out["customer_group"], "Commercial")


class TestAchievement(unittest.TestCase):
	def test_percent(self):
		self.assertEqual(achievement_percent(8500, 10000), 85)
		self.assertIsNone(achievement_percent(10, 0))

	def test_metrics(self):
		m = compute_metrics(10000, 8500, 2600000, 2210000)
		self.assertEqual(m["variance_qty"], -1500)
		self.assertEqual(m["qty_achievement_percent"], 85)


class TestIncentiveBands(unittest.TestCase):
	def test_min_and_max_separate_rates(self):
		from sales_performance.services.incentive_engine import resolve_incentive_rate

		slabs = [
			{
				"min_achievement_percent": 80,
				"min_incentive_percent": 1,
				"max_achievement_percent": 100,
				"max_incentive_percent": 2,
			}
		]
		self.assertEqual(resolve_incentive_rate(79, slabs), (0.0, None))
		self.assertEqual(resolve_incentive_rate(80, slabs), (1.0, "Min"))
		self.assertEqual(resolve_incentive_rate(99, slabs), (1.0, "Min"))
		self.assertEqual(resolve_incentive_rate(100, slabs), (2.0, "Max"))
		self.assertEqual(resolve_incentive_rate(120, slabs), (2.0, "Max"))

	def test_surplus_payout(self):
		from sales_performance.services.incentive_engine import incentive_on_surplus

		payout = incentive_on_surplus(120, 100, 24000, 20000, 2, pay_on="Amount")
		self.assertEqual(payout["incentive_qty"], 0)
		self.assertEqual(payout["incentive_on_qty"], 0)
		self.assertEqual(payout["incentive_amount"], 80)
		self.assertEqual(payout["incentive_on_amount"], 80)
		qty_pay = incentive_on_surplus(120, 100, 30000, 20000, 2, pay_on="Qty")
		self.assertEqual(qty_pay["incentive_on_amount"], 0)
		self.assertEqual(qty_pay["incentive_on_qty"], 0.4)
		self.assertEqual(qty_pay["incentive_amount"], 0.4)
		self.assertEqual(qty_pay["pay_on"], "Qty")
		missed = incentive_on_surplus(80, 100, 16000, 20000, 2, pay_on="Amount")
		self.assertEqual(missed["incentive_amount"], 0)
		self.assertEqual(missed["incentive_on_amount"], 0)
		self.assertEqual(missed["incentive_on_qty"], 0)


class TestIncentivePayoutSummary(unittest.TestCase):
	def test_groups_by_sales_person(self):
		from sales_performance.services.incentive_engine import summarize_payout_by_sales_person

		rows = [
			{"sales_person": "Ali", "incentive_band": "Min", "incentive_rate_percent": 1, "incentive_qty": 1, "incentive_amount": 50},
			{"sales_person": "Ali", "incentive_band": "Max", "incentive_rate_percent": 2, "incentive_qty": 2, "incentive_amount": 80},
			{"sales_person": "Sara", "incentive_band": "Min", "incentive_rate_percent": 1, "incentive_qty": 1, "incentive_amount": 20},
			{"sales_person": "Ali", "incentive_band": "", "incentive_rate_percent": 0, "incentive_qty": 0, "incentive_amount": 0},
		]
		out = {r["sales_person"]: r for r in summarize_payout_by_sales_person(rows)}
		self.assertEqual(out["Ali"]["incentive_amount"], 130)
		self.assertEqual(out["Ali"]["incentive_band"], "Max")
		self.assertEqual(out["Sara"]["incentive_amount"], 20)


class TestPeriodBuckets(unittest.TestCase):
	def test_monthly_and_quarterly(self):
		from sales_performance.services.incentive_engine import period_buckets

		self.assertEqual(len(period_buckets("Monthly")), 12)
		self.assertEqual(period_buckets("Monthly", month=8), [("August", [8])])
		self.assertEqual(period_buckets("Quarterly", quarter=2), [("Q2", [4, 5, 6])])
		self.assertEqual(period_buckets("Annual"), [("Annual", list(range(1, 13)))])

	def test_period_total_must_beat_target(self):
		from sales_performance.services.incentive_engine import metrics_with_monthly_incentive

		slabs = [
			{
				"min_achievement_percent": 100,
				"min_incentive_percent": 5,
				"max_achievement_percent": 100,
				"max_incentive_percent": 5,
			}
		]
		month_target = {
			1: {"target_qty": 100, "target_amount": 10000},
			2: {"target_qty": 100, "target_amount": 10000},
		}
		# Month 1 beats target; month 2 is zero. Period total is not above target.
		row = metrics_with_monthly_incentive(
			month_target,
			{1: 200, 2: 0},
			{1: 20000, 2: 0},
			[1, 2],
			slabs,
			"Qty Achievement",
			"Amount",
		)
		self.assertEqual(row["actual_amount"], 20000)
		self.assertEqual(row["target_amount"], 20000)
		self.assertEqual(row["incentive_amount"], 0)
		self.assertEqual(row["incentive_on_qty"], 0)

		beat = metrics_with_monthly_incentive(
			month_target,
			{1: 200, 2: 100},
			{1: 20000, 2: 12000},
			[1, 2],
			slabs,
			"Qty Achievement",
			"Amount",
		)
		self.assertEqual(beat["incentive_amount"], 600)
		self.assertEqual(beat["incentive_on_qty"], 0)

	def test_grouped_row_uses_scheme_on_totals(self):
		from sales_performance.services.incentive_engine import group_dashboard_rows

		slabs = [
			{
				"min_achievement_percent": 100,
				"min_incentive_percent": 2,
				"max_achievement_percent": 100,
				"max_incentive_percent": 2,
			}
		]
		rows = [
			{
				"sales_person": "Ali",
				"target_qty": 100,
				"actual_qty": 150,
				"target_amount": 10000,
				"actual_amount": 15000,
				"incentive_amount": 100,
				"incentive_on_amount": 100,
				"incentive_on_qty": 1,
			},
			{
				"sales_person": "Ali",
				"target_qty": 100,
				"actual_qty": 40,
				"target_amount": 10000,
				"actual_amount": 4000,
				"incentive_amount": 0,
			},
		]
		grouped = group_dashboard_rows(rows, "sales_person", slabs, "Qty Achievement", "Amount")
		self.assertEqual(len(grouped), 1)
		self.assertEqual(grouped[0]["actual_qty"], 190)
		self.assertEqual(grouped[0]["target_qty"], 200)
		self.assertEqual(grouped[0]["incentive_amount"], 0)
		self.assertEqual(grouped[0]["incentive_on_qty"], 0)


class TestAchievementBoardSplit(unittest.TestCase):
	def test_qty_amount_and_both(self):
		from sales_performance.sales_performance.page.target_achievement.target_achievement import (
			row_achieved,
			split_rows,
		)

		over_qty = {"dimension": "A", "qty_achievement_percent": 110, "amount_achievement_percent": 90}
		over_both = {"dimension": "B", "qty_achievement_percent": 120, "amount_achievement_percent": 105}
		under = {"dimension": "C", "qty_achievement_percent": 80, "amount_achievement_percent": 70}
		self.assertTrue(row_achieved(over_qty, "Qty"))
		self.assertFalse(row_achieved(over_qty, "Amount"))
		self.assertFalse(row_achieved(over_qty, "Both"))
		self.assertTrue(row_achieved(over_both, "Both"))
		ok, miss = split_rows([over_qty, over_both, under], "Qty")
		self.assertEqual([r["dimension"] for r in ok], ["B", "A"])
		self.assertEqual([r["dimension"] for r in miss], ["C"])


class TestDuplicatePrevention(unittest.TestCase):
	def test_planning_key_deterministic(self):
		a = planning_key("PLAN-1", "SP", "T", "GI", "GI Coil")
		b = planning_key("PLAN-1", "SP", "T", "GI", "GI Coil")
		self.assertEqual(a, b)

	def test_match_updates_same_grain(self):
		existing = SimpleNamespace(
			custom_planning_key="other",
			fiscal_year="2026-2027",
			item="GI",
			item_group="GI Coil",
		)
		parent = SimpleNamespace(targets=[existing])
		row = SimpleNamespace(item_code="GI", item_group="GI Coil")
		matched = _match_child(parent, "2026-2027", "new-key", row, True, "PLAN-2")
		self.assertIs(matched, existing)


class TestAnalysisVariance(unittest.TestCase):
	def test_increase_and_decrease(self):
		from sales_performance.services.analysis_engine import merge_period_rows, variance_row

		up = variance_row(120, 100, 2400, 2000)
		self.assertEqual(up["qty_variance"], 20)
		self.assertEqual(up["qty_variance_percent"], 20)
		self.assertEqual(up["amount_variance"], 400)
		down = variance_row(80, 100, 1600, 2000)
		self.assertEqual(down["amount_variance_percent"], -20)
		merged = merge_period_rows(
			[{"dimension": "Ali", "qty": 120, "amount": 2400}],
			[{"dimension": "Ali", "qty": 100, "amount": 2000}],
			{"Ali": {"qty": 110, "amount": 2200, "growth_percent": 10}},
		)
		self.assertEqual(merged[0]["qty_achievement_percent"], 109.1)
		self.assertEqual(merged[0]["growth_percent"], 10)


if __name__ == "__main__":
	unittest.main()
