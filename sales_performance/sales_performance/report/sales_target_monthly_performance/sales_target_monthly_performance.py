import frappe
from frappe import _
from frappe.utils import getdate

from sales_performance.services.distribution_engine import MONTHS
from sales_performance.services.incentive_engine import (
	collect_period_incentive_rows,
	calculation_level,
	calculation_level,
	dashboard_totals,
	period_selection_from_dates,
	scheme_settings,
)
from sales_performance.services.numbers import nflt
from sales_performance.services.planning_engine import fiscal_year_dates
from sales_performance.services.precision import round_percent


def execute(filters=None):
	filters = frappe._dict(filters or {})
	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_columns():
	qty = {"fieldtype": "Float", "precision": 0, "width": 120}
	amt = {"fieldtype": "Currency", "precision": 0, "width": 130}
	incentive_amt = {"fieldtype": "Currency", "precision": 2, "width": 150}
	pct = {"fieldtype": "Percent", "precision": 1, "width": 150}
	return [
		{"fieldname": "period", "label": _("Period"), "fieldtype": "Data", "width": 120},
		{"fieldname": "growth_percent", "label": _("Growth %"), **pct, "width": 110},
		{"fieldname": "target_qty", "label": _("Target Qty"), **qty},
		{"fieldname": "actual_qty", "label": _("Actual Qty"), **qty},
		{"fieldname": "qty_achievement_percent", "label": _("Qty Achievement %"), **pct},
		{"fieldname": "target_amount", "label": _("Target Amount"), **amt},
		{"fieldname": "actual_amount", "label": _("Actual Amount"), **amt},
		{"fieldname": "amount_achievement_percent", "label": _("Amount Achievement %"), **pct, "width": 160},
		{"fieldname": "pay_on", "label": _("Pay On"), "fieldtype": "Data", "width": 90},
		{"fieldname": "incentive_rate_percent", "label": _("Incentive %"), **pct, "width": 110},
		{"fieldname": "incentive_on_amount", "label": _("Incentive on Amount"), **amt, "width": 160},
		{"fieldname": "incentive_on_qty", "label": _("Incentive on Qty"), **qty, "width": 150},
		{"fieldname": "incentive_amount", "label": _("Payable Incentive"), **incentive_amt},
		{"fieldname": "incentive_band", "label": _("Incentive Band"), "fieldtype": "Data", "width": 110},
		{"fieldname": "variance_qty", "label": _("Variance Qty"), **qty, "width": 110},
		{"fieldname": "variance_amount", "label": _("Variance Amount"), **amt},
	]


def get_data(filters):
	if not filters.get("company") or not filters.get("fiscal_year"):
		return []

	view = filters.get("period") or "Monthly"
	start, end = fiscal_year_dates(filters.fiscal_year, filters.company)
	selected_month, selected_quarter = period_selection_from_dates(
		view, filters.get("month"), filters.get("quarter"),
		getdate(filters.get("from_date")) if filters.get("from_date") else None,
		getdate(filters.get("to_date")) if filters.get("to_date") else None,
	)
	line_filters = frappe._dict(filters)
	line_filters.period = "Monthly"
	line_filters.month = selected_month if view == "Monthly" else None
	line_filters.quarter = None
	lines = collect_period_incentive_rows(line_filters)
	if not lines:
		frappe.msgprint(
			_("No Sales Target Planning found for {0} / {1}. Use an Approved or Calculated plan.").format(
				filters.company, filters.fiscal_year
			)
		)
		return []

	today = getdate()
	ytd_month = today.month if (getdate(start) <= today <= getdate(end)) else 12
	slabs, based_on, pay_on = scheme_settings(filters)
	level = calculation_level(filters)

	def pack(label, month_numbers):
		wanted = {int(m) for m in month_numbers}
		subset = [row for row in lines if int(row.get("month_number") or 0) in wanted]
		# A quarterly/annual slab is earned on the whole period, not by adding
		# separately scored monthly payouts.
		period_rows = [dict(line, period=label) for line in subset]
		row = dashboard_totals(period_rows, slabs, based_on, pay_on, level)
		growth_weight = sum(nflt(r.get("target_qty")) or 1 for r in subset if r.get("growth_percent") not in (None, ""))
		growth_weighted = sum(
			nflt(r.get("growth_percent")) * (nflt(r.get("target_qty")) or 1)
			for r in subset
			if r.get("growth_percent") not in (None, "")
		)
		row["growth_percent"] = round_percent(growth_weighted / growth_weight) if growth_weight else None
		row["period"] = label
		return row

	if view == "Monthly":
		if selected_month:
			month = int(selected_month)
			return [pack(MONTHS[month - 1], [month])]
		return [pack(MONTHS[month - 1], [month]) for month in range(1, 13)]
	if view == "Quarterly":
		if selected_quarter:
			quarter = int(selected_quarter)
			return [pack(f"Q{quarter}", [quarter * 3 - 2, quarter * 3 - 1, quarter * 3])]
		return [pack(f"Q{quarter}", [quarter * 3 - 2, quarter * 3 - 1, quarter * 3]) for quarter in range(1, 5)]
	if view == "Half-Yearly":
		return [pack("H1", list(range(1, 7))), pack("H2", list(range(7, 13)))]
	if view == "YTD":
		return [pack("YTD", list(range(1, ytd_month + 1)))]
	return [pack("Annual", list(range(1, 13)))]
