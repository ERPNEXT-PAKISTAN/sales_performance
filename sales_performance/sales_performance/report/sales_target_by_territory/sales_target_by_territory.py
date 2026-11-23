import frappe
from frappe import _

from sales_performance.services.numbers import nflt
from sales_performance.services.achievement_engine import compute_metrics
from sales_performance.services.precision import round_percent
from sales_performance.sales_performance.report.sales_target_achievement.sales_target_achievement import (
	execute as execute_sales_target_achievement,
)


def execute(filters=None):
	filters = frappe._dict(filters or {})
	period = filters.get("period") or "Monthly"
	filters.period = period
	columns = get_columns(period)
	is_periodic = period in ("Monthly", "Quarterly")

	# Reuse the source report's target collection, access scoping, incentive
	# allocation, and filters. Its final row is a total, so remove it before
	# building territory and item-group totals.
	_source_columns, detail_rows, _source_message, _chart, _summary, _skip_total_rows = execute_sales_target_achievement(filters)
	grouped = {}
	for row in detail_rows or []:
		if row.get("is_total_row"):
			continue
		key = (
			(row.get("period") or "") if is_periodic else "",
			row.get("territory") or "",
			row.get("item_group") or "",
		)
		bucket = grouped.setdefault(
			key,
			{
				"period": key[0],
				"month_number": row.get("month_number") or 0,
				"territory": key[1],
				"item_group": key[2],
				"target_qty": 0.0,
				"actual_qty": 0.0,
				"target_amount": 0.0,
				"actual_amount": 0.0,
				"incentive_amount": 0.0,
				"pay_on": row.get("pay_on") or filters.get("pay_on") or "Amount",
				"_incentive_surplus": 0.0,
				"_incentive_bands": set(),
			}
		)
		for field in ("target_qty", "actual_qty", "target_amount", "actual_amount", "incentive_amount"):
			bucket[field] += nflt(row.get(field))
		metric = "qty" if (row.get("pay_on") or filters.get("pay_on")) == "Qty" else "amount"
		bucket["_incentive_surplus"] += max(
			nflt(row.get("actual_" + metric)) - nflt(row.get("target_" + metric)), 0
		)
		if nflt(row.get("incentive_amount")) > 0 and row.get("incentive_band"):
			bucket["_incentive_bands"].add(row.get("incentive_band"))

	data = []
	for bucket in grouped.values():
		bands = bucket.pop("_incentive_bands")
		surplus = bucket.pop("_incentive_surplus")
		bucket.update(
			compute_metrics(
				bucket["target_qty"],
				bucket["actual_qty"],
				bucket["target_amount"],
				bucket["actual_amount"],
			)
		)
		bucket["incentive_band"] = next(iter(bands)) if len(bands) == 1 else ("Mixed" if bands else "")
		bucket["incentive_rate_percent"] = round_percent(
			bucket["incentive_amount"] / surplus * 100 if surplus else 0, 2
		)
		bucket["_incentive_surplus"] = surplus
		data.append(bucket)

	data.sort(key=lambda row: (
		row.get("month_number") or 0,
		row.get("period") or "",
		row.get("territory") or "",
		row.get("item_group") or "",
	))

	tree_data = build_tree_data(data, is_periodic)
	if data:
		total_surplus = sum(nflt(row.get("_incentive_surplus")) for row in data)
		total_incentive = sum(nflt(row.get("incentive_amount")) for row in data)
		total = compute_metrics(
			sum(nflt(row.get("raw_target_qty", row.get("target_qty"))) for row in data),
			sum(nflt(row.get("raw_actual_qty", row.get("actual_qty"))) for row in data),
			sum(nflt(row.get("raw_target_amount", row.get("target_amount"))) for row in data),
			sum(nflt(row.get("raw_actual_amount", row.get("actual_amount"))) for row in data),
		)
		total.update(
			{
				"group_value": _("Total"),
				"pay_on": filters.get("pay_on") or "Amount",
				"incentive_band": "",
				"incentive_rate_percent": round_percent(total_incentive / total_surplus * 100 if total_surplus else 0, 2),
				"incentive_amount": total_incentive,
				"_node": "sales-target-by-territory-total",
				"_parent_node": "",
				"_node_type": "total",
				"indent": 0,
				"is_total_row": True,
			}
		)
		tree_data.append(total)

	message = _(
		"Expand each Territory to see its Item Groups. Monthly and Quarterly views also group results by Period. "
		"Incentive % is the blended allocated incentive divided by positive surplus for the selected Pay On metric."
	)
	return columns, tree_data, message, None, None, True


def build_tree_data(detail_rows, is_periodic):
	"""Build a Period → Territory → Item Group tree from the grouped detail rows."""
	if not detail_rows:
		return []

	by_period = {}
	for row in detail_rows:
		period_key = (row.get("period") or "") if is_periodic else ""
		by_period.setdefault(period_key, []).append(row)

	result = []
	for period_key in sorted(by_period, key=lambda value: _period_sort_key(by_period[value][0])):
		period_rows = by_period[period_key]
		period_node = _node_id("period", period_key) if is_periodic else ""
		if is_periodic:
			result.append(
				make_tree_row(
					aggregate_rows(period_rows),
					period_key or _("Unassigned Period"),
					"period",
					period_node,
					"",
					0,
					True,
				)
			)

		by_territory = {}
		for row in period_rows:
			by_territory.setdefault(row.get("territory") or "", []).append(row)

		for territory in sorted(by_territory, key=lambda value: (not bool(value), value.casefold())):
			item_rows = by_territory[territory]
			territory_node = _node_id("territory", period_key, territory)
			territory_level = 1 if is_periodic else 0
			result.append(
				make_tree_row(
					aggregate_rows(item_rows),
					territory or _("Unassigned Territory"),
					"territory",
					territory_node,
					period_node,
					territory_level,
					True,
					territory,
				)
			)
			for row in sorted(item_rows, key=lambda value: (value.get("item_group") or "").casefold()):
				item_group = row.get("item_group") or ""
				result.append(
					make_tree_row(
						row,
						item_group or _("Unassigned Item Group"),
						"item_group",
						_node_id("item_group", period_key, territory, item_group),
						territory_node,
						territory_level + 1,
						False,
						item_group,
					)
				)

	return result


def make_tree_row(values, label, node_type, node, parent, level, is_group, link_value=None):
	row = {
		"group_value": label,
		"_link_value": link_value,
		"_node": node,
		"_parent_node": parent,
		"_node_type": node_type,
		"_level": level,
		"indent": level,
		"is_group_row": 1 if is_group else 0,
	}
	for field in (
		"target_qty", "actual_qty", "variance_qty", "qty_achievement_percent",
		"target_amount", "actual_amount", "variance_amount", "amount_achievement_percent",
		"pay_on", "incentive_rate_percent", "incentive_band", "incentive_amount",
	):
		row[field] = values.get(field)
	return row


def aggregate_rows(rows):
	"""Calculate parent values from child rows, including a blended incentive rate."""
	target_qty = sum(nflt(row.get("raw_target_qty", row.get("target_qty"))) for row in rows)
	actual_qty = sum(nflt(row.get("raw_actual_qty", row.get("actual_qty"))) for row in rows)
	target_amount = sum(nflt(row.get("raw_target_amount", row.get("target_amount"))) for row in rows)
	actual_amount = sum(nflt(row.get("raw_actual_amount", row.get("actual_amount"))) for row in rows)
	incentive_amount = sum(nflt(row.get("incentive_amount")) for row in rows)
	incentive_surplus = sum(nflt(row.get("_incentive_surplus")) for row in rows)
	bands = {row.get("incentive_band") for row in rows if row.get("incentive_band")}
	result = compute_metrics(target_qty, actual_qty, target_amount, actual_amount)
	result.update(
		{
			"pay_on": rows[0].get("pay_on") or "Amount",
			"incentive_amount": incentive_amount,
			"incentive_band": next(iter(bands)) if len(bands) == 1 else ("Mixed" if bands else ""),
			"incentive_rate_percent": round_percent(
				incentive_amount / incentive_surplus * 100 if incentive_surplus else 0, 2
			),
		}
	)
	return result


def _node_id(*parts):
	# JSON encoding keeps node IDs unique even when names contain separators.
	return frappe.as_json(parts)


def _period_sort_key(row):
	return (nflt(row.get("month_number")), row.get("period") or "")


def get_columns(period="Annual"):
	qty = {"fieldtype": "Float", "precision": 0, "width": 110}
	amt = {"fieldtype": "Currency", "precision": 0, "width": 130}
	pct = {"fieldtype": "Percent", "precision": 0, "width": 150}
	columns = [
		{
			"fieldname": "group_value",
			"label": _("Period / Territory / Item Group") if period in ("Monthly", "Quarterly") else _("Territory / Item Group"),
			"fieldtype": "Data",
			"width": 280,
		}
	]
	columns.extend(
		[
			{"fieldname": "target_qty", "label": _("Target Qty"), **qty},
			{"fieldname": "actual_qty", "label": _("Actual Qty"), **qty},
			{"fieldname": "variance_qty", "label": _("Qty Variance"), **qty},
			{"fieldname": "qty_achievement_percent", "label": _("Qty Achievement %"), **pct},
			{"fieldname": "target_amount", "label": _("Target Amount"), **amt},
			{"fieldname": "actual_amount", "label": _("Actual Amount"), **amt},
			{"fieldname": "variance_amount", "label": _("Amount Variance"), **amt},
			{"fieldname": "amount_achievement_percent", "label": _("Amount Achievement %"), **pct},
			{"fieldname": "incentive_rate_percent", "label": _("Incentive %"), "fieldtype": "Percent", "precision": 2, "width": 110},
			{"fieldname": "incentive_amount", "label": _("Allocated Incentive"), "fieldtype": "Currency", "precision": 2, "width": 150},
			{"fieldname": "pay_on", "label": _("Pay On"), "fieldtype": "Data", "width": 90},
			{"fieldname": "incentive_band", "label": _("Incentive Band"), "fieldtype": "Data", "width": 120},
		]
	)
	return columns
