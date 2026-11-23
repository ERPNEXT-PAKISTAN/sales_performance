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

MONTHLY_SALES_HIERARCHY = "Month → Sales Person → Territory → Item Group"

TREE_GROUPINGS = {
	"Territory → Item Group": ("territory", "item_group"),
	"Sales Person → Item Group": ("sales_person", "item_group"),
	"Customer Group → Item Group": ("customer_group", "item_group"),
	"Item Group → Item": ("item_group", "item_code"),
	MONTHLY_SALES_HIERARCHY: ("sales_person", "territory", "item_group"),
}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	period = filters.get("period") or "Monthly"
	filters.period = period
	group_by = filters.get("group_by") or ""
	grouped = group_by in TREE_GROUPINGS
	columns = get_columns(period, grouped=grouped, group_by=group_by)
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
	report_data = build_tree_data(data, group_by, period in ("Monthly", "Quarterly"), filters) if grouped else data
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
		if grouped:
			earned_rates = {nflt(row.get("incentive_rate_percent")) for row in data if nflt(row.get("incentive_amount")) > 0}
			total["incentive_rate_percent"] = next(iter(earned_rates)) if len(earned_rates) == 1 else 0
			total.update({
				"group_value": _("Total"),
				"_node": "sales-target-achievement-total",
				"_parent_node": "",
				"_node_type": "total",
				"indent": 0,
			})
		report_data.append(total)
	# The standard footer averages percentages. Supply a total derived from
	# aggregate target/actual instead, shared by the screen and exported report.
	return columns, report_data, message, None, None, True


def get_columns(period="Annual", grouped=False, group_by=None):
	qty = {"fieldtype": "Float", "precision": 0, "width": 110}
	amt = {"fieldtype": "Currency", "precision": 0, "width": 130}
	incentive_amt = {"fieldtype": "Currency", "precision": 2, "width": 150}
	pct = {"fieldtype": "Percent", "precision": 0, "width": 140}
	columns = [
		{"fieldname": "sales_person", "label": _("Sales Person"), "fieldtype": "Link", "options": "Sales Person", "width": 140},
		{"fieldname": "territory", "label": _("Territory"), "fieldtype": "Link", "options": "Territory", "width": 120},
		{"fieldname": "item_group", "label": _("Item Group"), "fieldtype": "Link", "options": "Item Group", "width": 130},
		{"fieldname": "item_code", "label": _("Item"), "fieldtype": "Link", "options": "Item", "width": 280},
		{"fieldname": "growth_percent", "label": _("Growth %"), **pct, "width": 110},
	]
	if period in ("Monthly", "Quarterly"):
		columns.insert(0, {"fieldname": "period", "label": _("Period"), "fieldtype": "Data", "width": 110})
	if grouped:
		group_label = (
			_("Month / Sales Person / Territory / Item Group / Item")
			if group_by == MONTHLY_SALES_HIERARCHY
			else _("Period / Group / Subgroup / Item") if period in ("Monthly", "Quarterly")
			else _("Group / Subgroup / Item")
		)
		columns.insert(0, {
			"fieldname": "group_value",
			"label": group_label,
			"fieldtype": "Data",
			"width": 288,
		})
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
			{"fieldname": "incentive_rate_percent", "label": _("Incentive %"), "fieldtype": "Percent", "precision": 2, "width": 110},
			{"fieldname": "incentive_amount", "label": _("Allocated Incentive"), **incentive_amt},
			{"fieldname": "planning", "label": _("Planning"), "fieldtype": "Link", "options": "Sales Target Planning", "width": 140},
			{"fieldname": "customer_group", "label": _("Customer Group"), "fieldtype": "Link", "options": "Customer Group", "width": 140},
			{"fieldname": "pay_on", "label": _("Pay On"), "fieldtype": "Data", "width": 90},
		]
	)
	if grouped:
		hidden_fields = set(TREE_GROUPINGS[group_by])
		if period in ("Monthly", "Quarterly"):
			hidden_fields.add("period")
		for column in columns:
			if column["fieldname"] in hidden_fields:
				column["hidden"] = True
	return columns


def build_tree_data(rows, group_by, is_periodic, filters):
	"""Keep item-level results while adding period and selected group totals."""
	group_fields = TREE_GROUPINGS[group_by]
	by_period = {}
	for row in rows:
		period_key = (row.get("period") or "") if is_periodic else ""
		by_period.setdefault(period_key, []).append(row)

	result = []
	for period_key in sorted(by_period, key=lambda value: _period_sort_key(by_period[value][0])):
		period_rows = by_period[period_key]
		period_node = _tree_node_id("period", period_key) if is_periodic else ""
		if is_periodic:
			result.append(_make_group_row(
				period_rows, period_key or _("Unassigned Period"), "period", period_node, "", 0, filters
			))

		def append_groups(group_rows, field_index, parent_node, path):
			field = group_fields[field_index]
			field_label = field.replace("_", " ").title()
			by_value = {}
			for row in group_rows:
				by_value.setdefault(row.get(field) or "", []).append(row)
			level = (1 if is_periodic else 0) + field_index
			for value in sorted(by_value, key=lambda item: (not bool(item), item.casefold())):
				matching_rows = by_value[value]
				group_node = _tree_node_id(field, period_key, *path, value)
				group_name = value or _("Unassigned {0}").format(field_label)
				result.append(_make_group_row(
					matching_rows, group_name, field, group_node, parent_node, level, filters, field, value
				))
				if field_index + 1 < len(group_fields):
					append_groups(matching_rows, field_index + 1, group_node, (*path, value))
					continue

				detail_rows = sorted(matching_rows, key=lambda row: (
					row.get("sales_person") or "", row.get("customer_group") or "",
					row.get("item_code") or "", row.get("planning") or "",
				))
				for index, row in enumerate(detail_rows):
					leaf = dict(row)
					leaf_level = level + 1
					leaf.update({
						"group_value": "",
						"_node": _tree_node_id("detail", period_key, *path, value, index),
						"_parent_node": group_node,
						"_node_type": "detail",
						"_level": leaf_level,
						"indent": leaf_level,
					})
					result.append(leaf)

		append_groups(period_rows, 0, period_node, ())

	return result


def _make_group_row(rows, label, node_type, node, parent, level, filters, dimension=None, value=None):
	row = _aggregate_rows(rows, filters)
	row.update({
		"group_value": label,
		"_link_value": value,
		"_node": node,
		"_parent_node": parent,
		"_node_type": node_type,
		"_level": level,
		"indent": level,
		"is_group_row": 1,
	})
	if dimension:
		row[dimension] = value
	return row


def _aggregate_rows(rows, filters):
	target_qty = sum(nflt(row.get("target_qty")) for row in rows)
	actual_qty = sum(nflt(row.get("actual_qty")) for row in rows)
	target_amount = sum(nflt(row.get("target_amount")) for row in rows)
	actual_amount = sum(nflt(row.get("actual_amount")) for row in rows)
	incentive_amount = sum(nflt(row.get("incentive_amount")) for row in rows)
	earned_rates = {nflt(row.get("incentive_rate_percent")) for row in rows if nflt(row.get("incentive_amount")) > 0}
	row = compute_metrics(target_qty, actual_qty, target_amount, actual_amount)
	row.update({
		"pay_on": filters.get("pay_on") or (rows[0].get("pay_on") if rows else "Amount"),
		"incentive_amount": incentive_amount,
		"incentive_rate_percent": next(iter(earned_rates)) if len(earned_rates) == 1 else 0,
		"growth_percent": None,
	})
	return row


def _tree_node_id(*parts):
	return frappe.as_json(parts)


def _period_sort_key(row):
	return (nflt(row.get("month_number")), row.get("period") or "")
