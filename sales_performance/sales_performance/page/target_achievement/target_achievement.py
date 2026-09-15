import frappe
from frappe import _

from sales_performance.services.incentive_engine import (
	collect_period_incentive_rows,
	group_dashboard_rows,
	scheme_settings,
)
from sales_performance.services.numbers import nflt


def _pct(row, field):
	value = row.get(field)
	return nflt(value) if value not in (None, "") else None


def row_achieved(row, judge="Qty"):
	qty = _pct(row, "qty_achievement_percent")
	amt = _pct(row, "amount_achievement_percent")
	judge = (judge or "Qty").strip()
	if judge == "Amount":
		return amt is not None and amt >= 100
	if judge == "Both":
		return qty is not None and amt is not None and qty >= 100 and amt >= 100
	return qty is not None and qty >= 100


def split_rows(rows, judge="Qty"):
	achieved, missed = [], []
	for row in rows:
		if row_achieved(row, judge):
			achieved.append(row)
		else:
			missed.append(row)
	achieved.sort(key=lambda r: nflt(r.get("qty_achievement_percent") or r.get("amount_achievement_percent")), reverse=True)
	missed.sort(key=lambda r: nflt(r.get("qty_achievement_percent") if r.get("qty_achievement_percent") is not None else -1))
	return achieved, missed


def _item_labels(rows):
	codes = list({row.get("item_code") for row in rows if row.get("item_code")})
	if not codes:
		return {}
	return {
		d.name: d.item_name or d.name
		for d in frappe.get_all("Item", filters={"name": ("in", codes)}, fields=["name", "item_name"])
	}


@frappe.whitelist()
def get_achievement_board(
	company=None,
	fiscal_year=None,
	period="Annual",
	month=None,
	quarter=None,
	judge="Qty",
	sales_person=None,
	territory=None,
	item_group=None,
	customer_group=None,
	item=None,
):
	if not company or not fiscal_year:
		frappe.throw(_("Company and Fiscal Year are required"))

	filters = {
		"company": company,
		"fiscal_year": fiscal_year,
		"period": period or "Annual",
		"month": month,
		"quarter": quarter,
		"sales_person": sales_person,
		"territory": territory,
		"item_group": item_group,
		"customer_group": customer_group,
		"item": item,
	}
	rows = collect_period_incentive_rows(filters)
	slabs, based_on, pay_on = scheme_settings(filters)
	if not judge:
		judge = "Amount" if based_on == "Amount Achievement" else "Qty"

	groups = group_dashboard_rows(rows, "item_group", slabs, based_on, pay_on)
	items = group_dashboard_rows(rows, "item", slabs, based_on, pay_on)
	labels = _item_labels(rows)
	for row in items:
		row["item_name"] = labels.get(row.get("dimension")) or row.get("dimension")

	g_ok, g_miss = split_rows(groups, judge)
	i_ok, i_miss = split_rows(items, judge)
	return {
		"judge": judge,
		"based_on": based_on,
		"item_groups_achieved": g_ok,
		"item_groups_missed": g_miss,
		"items_achieved": i_ok,
		"items_missed": i_miss,
		"totals": {
			"item_groups_achieved": len(g_ok),
			"item_groups_missed": len(g_miss),
			"items_achieved": len(i_ok),
			"items_missed": len(i_miss),
		},
	}


def _parse_card_filters(filters=None):
	if isinstance(filters, str):
		filters = frappe.parse_json(filters)
	if isinstance(filters, list):
		out = {}
		for row in filters:
			if isinstance(row, (list, tuple)) and len(row) >= 4:
				out[row[1]] = row[3]
		filters = out
	filters = frappe._dict(filters or {})
	if not filters.get("company"):
		filters.company = frappe.defaults.get_user_default("Company")
	if not filters.get("fiscal_year"):
		filters.fiscal_year = frappe.defaults.get_user_default("fiscal_year")
	if not filters.get("period"):
		filters.period = "Annual"
	if not filters.get("judge"):
		filters.judge = "Qty"
	return filters


def _card_result(filters, total_key):
	filters = _parse_card_filters(filters)
	if not filters.get("company") or not filters.get("fiscal_year"):
		return {"value": 0, "fieldtype": "Int"}
	try:
		board = get_achievement_board(
			company=filters.company,
			fiscal_year=filters.fiscal_year,
			period=filters.period,
			month=filters.get("month"),
			quarter=filters.get("quarter"),
			judge=filters.judge,
			sales_person=filters.get("sales_person"),
			territory=filters.get("territory"),
			item_group=filters.get("item_group"),
			customer_group=filters.get("customer_group"),
			item=filters.get("item"),
		)
	except Exception:
		return {"value": 0, "fieldtype": "Int"}
	return {
		"value": board["totals"].get(total_key) or 0,
		"fieldtype": "Int",
		"route": ["query-report", "Target Achievement Status"],
		"route_options": {
			"company": filters.company,
			"fiscal_year": filters.fiscal_year,
			"period": filters.period,
			"judge": filters.judge,
		},
	}


@frappe.whitelist()
def card_item_groups_achieved(filters=None, **kwargs):
	return _card_result(filters, "item_groups_achieved")


@frappe.whitelist()
def card_item_groups_missed(filters=None, **kwargs):
	return _card_result(filters, "item_groups_missed")


@frappe.whitelist()
def card_items_achieved(filters=None, **kwargs):
	return _card_result(filters, "items_achieved")


@frappe.whitelist()
def card_items_missed(filters=None, **kwargs):
	return _card_result(filters, "items_missed")
