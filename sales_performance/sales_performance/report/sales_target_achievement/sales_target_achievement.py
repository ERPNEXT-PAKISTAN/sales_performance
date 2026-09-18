import frappe
from frappe import _

from sales_performance.services.achievement_engine import compute_metrics
from sales_performance.services.numbers import nflt
from sales_performance.services.incentive_engine import (
	allocate_item_incentives,
	collect_achievement_rows,
	collect_period_incentive_rows,
	calculation_level,
	scheme_settings,
)


def execute(filters=None):
	filters = frappe._dict(filters or {})
	period = filters.get("period") or "Monthly"
	filters.period = period
	columns = get_columns(period)
	if period in ("Monthly", "Quarterly"):
		data = collect_period_incentive_rows(filters)
	else:
		data = collect_achievement_rows(filters)
	slabs, based_on, pay_on = scheme_settings(filters)
	level = calculation_level(filters)
	data = allocate_item_incentives(data, slabs, based_on, pay_on, level)
	# Filter the completed allocation: hiding rows must never change the earned
	# slab or redistribute their incentive among the remaining visible items.
	band = filters.get("incentive_band") or "All"
	if band in ("Min", "Max"):
		data = [row for row in data if row.get("incentive_band") == band]
	elif band in ("Not Achieve", "Not Achive"):
		data = [row for row in data if not row.get("incentive_band")]
	data.sort(key=lambda row: (
		row.get("month_number") or 0, row.get("period") or "",
		row.get("sales_person") or "", row.get("territory") or "",
		row.get("item_group") or "", row.get("item_code") or "",
	))
	message = _(
		"Each row shows the item's target, sales and achievement. In Item mode, each item "
		"qualifies independently; in grouped mode, the slab is applied after combining "
		"Sales Person, Period and Customer Group. Rows at or below target receive zero. "
		"Achievement is blank when target is zero. Incentive % is the earned scheme rate used "
		"before allocation. Min/Max filter by that incentive band; Not Achieve shows rows with "
		"no allocated incentive."
	)
	if data:
		total = compute_metrics(
			sum(nflt(row.get("target_qty")) for row in data),
			sum(nflt(row.get("actual_qty")) for row in data),
			sum(nflt(row.get("target_amount")) for row in data),
			sum(nflt(row.get("actual_amount")) for row in data),
		)
		total.update({
			columns[0]["fieldname"]: _("Total"),
			"incentive_amount": sum(nflt(row.get("incentive_amount")) for row in data),
			"is_total_row": True,
		})
		data.append(total)
	# The standard footer averages percentages. Supply a total derived from
	# aggregate target/actual instead, shared by the screen and exported report.
	return columns, data, message, None, None, True


def get_columns(period="Annual"):
	qty = {"fieldtype": "Float", "precision": 0, "width": 110}
	amt = {"fieldtype": "Currency", "precision": 0, "width": 130}
	incentive_amt = {"fieldtype": "Currency", "precision": 0, "width": 150}
	pct = {"fieldtype": "Percent", "precision": 0, "width": 140}
	columns = [
		{"fieldname": "sales_person", "label": _("Sales Person"), "fieldtype": "Link", "options": "Sales Person", "width": 140},
		{"fieldname": "territory", "label": _("Territory"), "fieldtype": "Link", "options": "Territory", "width": 120},
		{"fieldname": "item_group", "label": _("Item Group"), "fieldtype": "Link", "options": "Item Group", "width": 130},
		{"fieldname": "customer_group", "label": _("Customer Group"), "fieldtype": "Link", "options": "Customer Group", "width": 140},
		{"fieldname": "item_code", "label": _("Item"), "fieldtype": "Link", "options": "Item", "width": 140},
		{"fieldname": "growth_percent", "label": _("Growth %"), **pct, "width": 110},
	]
	if period in ("Monthly", "Quarterly"):
		columns.insert(0, {"fieldname": "period", "label": _("Period"), "fieldtype": "Data", "width": 110})
	columns.extend(
		[
			{"fieldname": "target_qty", "label": _("Target Qty"), **qty},
			{"fieldname": "actual_qty", "label": _("Actual Qty"), **qty},
			{"fieldname": "variance_qty", "label": _("Qty Variance"), **qty},
			{"fieldname": "qty_achievement_percent", "label": _("Qty Achievement %"), **pct},
			{"fieldname": "target_amount", "label": _("Target Amount"), **amt},
			{"fieldname": "actual_amount", "label": _("Actual Amount"), **amt},
			{"fieldname": "variance_amount", "label": _("Amount Variance"), **amt},
			{"fieldname": "amount_achievement_percent", "label": _("Amount Achievement %"), **pct, "width": 160},
			{"fieldname": "pay_on", "label": _("Pay On"), "fieldtype": "Data", "width": 90},
			{"fieldname": "incentive_rate_percent", "label": _("Incentive %"), **pct, "width": 110},
			{"fieldname": "incentive_amount", "label": _("Allocated Incentive"), **incentive_amt},
			{"fieldname": "planning", "label": _("Planning"), "fieldtype": "Link", "options": "Sales Target Planning", "width": 140},
		]
	)
	return columns
