import frappe
from frappe import _

from sales_performance.sales_performance.page.target_achievement.target_achievement import (
	get_achievement_board,
)


@frappe.whitelist()
def get_data(
	chart_name=None,
	chart=None,
	no_cache=None,
	filters=None,
	from_date=None,
	to_date=None,
	timespan=None,
	time_interval=None,
	heatmap_year=None,
	refresh=None,
	**kwargs,
):
	filters = frappe._dict(frappe.parse_json(filters) if filters else {})
	company = filters.get("company") or frappe.defaults.get_user_default("Company")
	fiscal_year = filters.get("fiscal_year") or frappe.defaults.get_user_default("fiscal_year")
	if not company or not fiscal_year:
		return {
			"labels": [_("Achieved"), _("Not Achieved")],
			"datasets": [
				{"name": _("Item Groups"), "values": [0, 0]},
				{"name": _("Items"), "values": [0, 0]},
			],
		}

	try:
		board = get_achievement_board(
			company=company,
			fiscal_year=fiscal_year,
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
		frappe.log_error(frappe.get_traceback(), "Target Achievement Split chart failed")
		board = {"totals": {}}

	totals = board.get("totals") or {}
	return {
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
	}
