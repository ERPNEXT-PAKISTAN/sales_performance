import frappe
from frappe import _

from sales_performance.sales_performance.page.target_achievement.target_achievement import (
	get_achievement_board,
)
from sales_performance.services.numbers import nflt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	columns = get_columns()
	empty = _chart({})
	if not filters.get("company") or not filters.get("fiscal_year"):
		return columns, [], None, empty
	try:
		board = get_achievement_board(
			company=filters.company,
			fiscal_year=filters.fiscal_year,
			period=filters.get("period") or "Annual",
			month=filters.get("month"),
			quarter=filters.get("quarter"),
			judge=filters.get("judge") or "Qty",
			sales_person=filters.get("sales_person"),
			territory=filters.get("territory"),
			item_group=filters.get("item_group"),
			customer_group=filters.get("customer_group"),
			item=filters.get("item"),
		)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Target Achievement Status failed")
		return columns, [], None, empty
	data = _flatten(board)
	return columns, data, None, _chart(board.get("totals") or {})


def get_columns():
	qty = {"fieldtype": "Float", "precision": 0, "width": 110}
	amt = {"fieldtype": "Currency", "precision": 0, "width": 130}
	pct = {"fieldtype": "Percent", "precision": 1, "width": 140}
	return [
		{"fieldname": "row_type", "label": _("Type"), "fieldtype": "Data", "width": 110},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 120},
		{"fieldname": "name", "label": _("Name"), "fieldtype": "Data", "width": 180},
		{"fieldname": "dimension", "label": _("Code"), "fieldtype": "Data", "width": 140},
		{"fieldname": "target_qty", "label": _("Target Qty"), **qty},
		{"fieldname": "actual_qty", "label": _("Actual Qty"), **qty},
		{"fieldname": "qty_achievement_percent", "label": _("Qty Achievement %"), **pct},
		{"fieldname": "target_amount", "label": _("Target Amount"), **amt},
		{"fieldname": "actual_amount", "label": _("Actual Amount"), **amt},
		{"fieldname": "amount_achievement_percent", "label": _("Amount Achievement %"), **pct, "width": 160},
	]


def _flatten(board):
	rows = []
	mapping = (
		("Item Group", "Achieved", "item_groups_achieved"),
		("Item Group", "Not Achieved", "item_groups_missed"),
		("Item", "Achieved", "items_achieved"),
		("Item", "Not Achieved", "items_missed"),
	)
	for row_type, status, key in mapping:
		for row in board.get(key) or []:
			rows.append(
				{
					"row_type": row_type,
					"status": status,
					"name": row.get("item_name") or row.get("dimension"),
					"dimension": row.get("dimension"),
					"target_qty": nflt(row.get("target_qty")),
					"actual_qty": nflt(row.get("actual_qty")),
					"qty_achievement_percent": row.get("qty_achievement_percent"),
					"target_amount": nflt(row.get("target_amount")),
					"actual_amount": nflt(row.get("actual_amount")),
					"amount_achievement_percent": row.get("amount_achievement_percent"),
				}
			)
	return rows


def _chart(totals):
	return {
		"data": {
			"labels": [_("Achieved"), _("Not Achieved")],
			"datasets": [
				{
					"name": _("Item Groups"),
					"values": [
						totals.get("item_groups_achieved") or 0,
						totals.get("item_groups_missed") or 0,
					],
				},
				{
					"name": _("Items"),
					"values": [
						totals.get("items_achieved") or 0,
						totals.get("items_missed") or 0,
					],
				},
			],
		},
		"type": "bar",
		"colors": ["#16a34a", "#dc2626"],
	}
