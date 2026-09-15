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
	columns = [
		{"fieldname": "sales_person", "label": _("Sales Person"), "fieldtype": "Link", "options": "Sales Person", "width": 140},
		{"fieldname": "territory", "label": _("Territory"), "fieldtype": "Link", "options": "Territory", "width": 120},
		{"fieldname": "item_group", "label": _("Item Group"), "fieldtype": "Link", "options": "Item Group", "width": 130},
		{"fieldname": "item_code", "label": _("Item"), "fieldtype": "Link", "options": "Item", "width": 140},
		{"fieldname": "growth_percent", "label": _("Growth %"), "fieldtype": "Percent", "width": 110},
	]
	if period in ("Monthly", "Quarterly"):
		columns.insert(0, {"fieldname": "period", "label": _("Period"), "fieldtype": "Data", "width": 110})
	columns.extend(
		[
			{"fieldname": "target_qty", "label": _("Target Qty"), "fieldtype": "Float", "width": 110},
			{"fieldname": "actual_qty", "label": _("Actual Qty"), "fieldtype": "Float", "width": 110},
			{"fieldname": "qty_achievement_percent", "label": _("Qty Achievement %"), "fieldtype": "Percent", "width": 140},
			{"fieldname": "target_amount", "label": _("Target Amount"), "fieldtype": "Currency", "width": 130},
			{"fieldname": "actual_amount", "label": _("Actual Amount"), "fieldtype": "Currency", "width": 130},
			{"fieldname": "amount_achievement_percent", "label": _("Amount Achievement %"), "fieldtype": "Percent", "width": 160},
			{"fieldname": "pay_on", "label": _("Pay On"), "fieldtype": "Data", "width": 90},
			{"fieldname": "incentive_rate_percent", "label": _("Incentive %"), "fieldtype": "Percent", "width": 110},
			{"fieldname": "incentive_on_amount", "label": _("Incentive on Amount"), "fieldtype": "Currency", "width": 160},
			{"fieldname": "incentive_on_qty", "label": _("Incentive on Qty"), "fieldtype": "Float", "width": 150},
			{"fieldname": "incentive_amount", "label": _("Payable Incentive"), "fieldtype": "Currency", "width": 150},
			{"fieldname": "incentive_band", "label": _("Incentive Band"), "fieldtype": "Data", "width": 110},
			{"fieldname": "variance_qty", "label": _("Variance Qty"), "fieldtype": "Float", "width": 110},
			{"fieldname": "variance_amount", "label": _("Variance Amount"), "fieldtype": "Currency", "width": 130},
			{"fieldname": "planning", "label": _("Planning"), "fieldtype": "Link", "options": "Sales Target Planning", "width": 140},
		]
	)
	return columns
