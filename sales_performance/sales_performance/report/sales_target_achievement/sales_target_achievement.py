import frappe
from frappe import _

from sales_performance.services.incentive_engine import collect_achievement_rows, collect_period_incentive_rows


def execute(filters=None):
	filters = frappe._dict(filters or {})
	period = filters.get("period") or "Monthly"
	columns = get_columns(period)
	if period in ("Monthly", "Quarterly"):
		data = collect_period_incentive_rows(filters)
	else:
		data = collect_achievement_rows(filters)
	return columns, data


def get_columns(period="Annual"):
	qty = {"fieldtype": "Float", "precision": 0, "width": 110}
	amt = {"fieldtype": "Currency", "precision": 0, "width": 130}
	pct = {"fieldtype": "Percent", "precision": 1, "width": 140}
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
			{"fieldname": "qty_achievement_percent", "label": _("Qty Achievement %"), **pct},
			{"fieldname": "target_amount", "label": _("Target Amount"), **amt},
			{"fieldname": "actual_amount", "label": _("Actual Amount"), **amt},
			{"fieldname": "amount_achievement_percent", "label": _("Amount Achievement %"), **pct, "width": 160},
			{"fieldname": "pay_on", "label": _("Pay On"), "fieldtype": "Data", "width": 90},
			{"fieldname": "incentive_rate_percent", "label": _("Incentive %"), **pct, "width": 110},
			{"fieldname": "incentive_on_amount", "label": _("Incentive on Amount"), **amt, "width": 160},
			{"fieldname": "incentive_on_qty", "label": _("Incentive on Qty"), **qty, "width": 150},
			{"fieldname": "incentive_amount", "label": _("Payable Incentive"), **amt, "width": 150},
			{"fieldname": "incentive_band", "label": _("Incentive Band"), "fieldtype": "Data", "width": 110},
			{"fieldname": "variance_qty", "label": _("Variance Qty"), **qty},
			{"fieldname": "variance_amount", "label": _("Variance Amount"), **amt},
			{"fieldname": "planning", "label": _("Planning"), "fieldtype": "Link", "options": "Sales Target Planning", "width": 140},
		]
	)
	return columns
