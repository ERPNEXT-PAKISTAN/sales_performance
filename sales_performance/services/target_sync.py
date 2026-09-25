"""Idempotent sync of approved plans onto ERPNext Sales Person / Territory Target Detail."""

import hashlib

from frappe.utils import now_datetime
from sales_performance.services.numbers import nflt as flt, ncint as cint


def planning_key(planning_name, sales_person, territory, item_code, item_group):
	return "|".join(
		[
			planning_name or "",
			sales_person or "",
			territory or "",
			item_code or "",
			item_group or "",
		]
	)


def sync_official_targets(planning_doc):
	"""Create or update Target Detail rows. Safe to run more than once."""
	import frappe

	if planning_doc.status != "Approved":
		frappe.throw("Only approved plans can be applied to ERPNext targets")

	has_item = frappe.db.has_column("Target Detail", "item")
	fiscal_year = planning_doc.fiscal_year
	version = cint(planning_doc.planning_version)
	approved_by = planning_doc.approved_by or frappe.session.user
	approved_on = planning_doc.approved_on or now_datetime()

	# Replace only rows owned by this plan (or the revision it supersedes).
	# Include old parents so reassignment/deletion also clears obsolete targets.
	owned = [planning_doc.name]
	if planning_doc.previous_planning:
		owned.append(planning_doc.previous_planning)
	grouped = {}
	for old in frappe.get_all("Target Detail", filters={"custom_source_planning": ["in", owned]}, fields=["parent", "parenttype"]):
		if old.parenttype in ("Sales Person", "Territory"):
			grouped.setdefault((old.parenttype, old.parent), [])
	for row in planning_doc.proposal_details or []:
		qty = flt(row.approved_target_qty)
		amount = flt(row.approved_target_amount)
		if not qty and not amount:
			continue
		parenttype, parent = _parent_for_row(row, planning_doc)
		if not parent:
			continue
		grouped.setdefault((parenttype, parent), []).append(row)

	synced = 0
	for (parenttype, parent), rows in grouped.items():
		frappe.db.sql(f"select name from `tab{parenttype}` where name=%s for update", parent)
		parent_doc = frappe.get_doc(parenttype, parent)
		parent_doc.set("targets", [r for r in parent_doc.targets if r.get("custom_source_planning") not in owned])
		# Target Detail has a single row per item (or item group) and fiscal
		# year for each parent. Proposal rows may be split by customer group, so
		# combine those splits before syncing to avoid ERPNext duplicate-row
		# validation errors and retain their summed monthly allocations.
		target_rows = {}
		for row in rows:
			grain = (row.item_code or "") if has_item else (row.item_group or "")
			if not grain:
				continue
			target_rows.setdefault(grain, []).append(row)
		for grain, source_rows in target_rows.items():
			row = source_rows[0]
			qty = sum(flt(source.approved_target_qty) for source in source_rows)
			amount = sum(flt(source.approved_target_amount) for source in source_rows)
			if not qty and not amount:
				continue
			identity = f"{parenttype}|{parent}|{grain}"
			key = f"{planning_doc.name}|{hashlib.sha1(identity.encode()).hexdigest()}"
			payload = {
				"item_group": row.item_group,
				"fiscal_year": fiscal_year,
				"target_qty": qty,
				"target_amount": amount,
				"custom_source_planning": planning_doc.name,
				"custom_planning_version": version,
				"custom_planning_key": key,
				"custom_approved_by": approved_by,
				"custom_approved_on": approved_on,
			}
			if has_item:
				payload["item"] = row.item_code
			# ERPNext has one distribution per target row. Separate quantity and
			# amount rows when monthly rates differ to preserve both allocations.
			qty_p = _percentages(planning_doc, source_rows, "target_qty")
			amt_p = _percentages(planning_doc, source_rows, "target_amount")
			from sales_performance.services.distribution_engine import ensure_monthly_distribution
			parts = [("both", qty_p if qty else amt_p, qty, amount)]
			if qty and amount and any(abs(a - b) > 0.000001 for a, b in zip(qty_p, amt_p)):
				parts = [("qty", qty_p, qty, 0), ("amount", amt_p, 0, amount)]
			for suffix, percentages, qty, amount in parts:
				dist_name = ensure_monthly_distribution(f"SP-{planning_doc.name}-{row.row_key}-{suffix}"[:140], percentages, fiscal_year)
				parent_doc.append("targets", {**payload, "distribution_id": dist_name,
					"target_qty": qty, "target_amount": amount, "custom_planning_key": f"{key}|{suffix}"})
				synced += 1
		parent_doc.flags.ignore_validate_update_after_submit = True
		parent_doc.save(ignore_permissions=True)

	planning_doc.db_set("erpnext_targets_synced_on", now_datetime())
	return synced


def _percentages(doc, rows, field):
	if not isinstance(rows, (list, tuple, set)):
		rows = [rows]
	row_keys = {row.row_key for row in rows}
	values = [sum(flt(m.get(field)) for m in doc.monthly_details if m.row_key in row_keys and cint(m.month_number) == n) for n in range(1, 13)]
	total = sum(values)
	result = [round(v / total * 100, 6) for v in values] if total else [round(100 / 12, 6)] * 12
	# Reconcile in a nonzero month, avoiding a residual on a transferred-out month.
	last = max((i for i, v in enumerate(values) if v), default=11)
	result[last] += 100 - sum(result)
	return result


def qty_of(row):
	return flt(row.approved_target_qty)


def amount_of(row):
	return flt(row.approved_target_amount)


def _parent_for_row(row, planning_doc):
	sales_person = row.sales_person or planning_doc.sales_person
	territory = row.territory or planning_doc.territory
	if sales_person:
		return "Sales Person", sales_person
	if territory:
		return "Territory", territory
	return None, None


def _match_child(parent_doc, fiscal_year, key, row, has_item, planning_name):
	"""One official Target Detail row per grain per fiscal year (update, do not duplicate)."""
	for child in parent_doc.targets:
		if getattr(child, "custom_planning_key", None) == key:
			return child
	for child in parent_doc.targets:
		if child.fiscal_year != fiscal_year:
			continue
		if has_item:
			if (getattr(child, "item", None) or "") == (row.item_code or ""):
				return child
		elif (child.item_group or "") == (row.item_group or "") and not getattr(child, "item", None):
			return child
	return None


def _distribution_for_row(planning_doc, row):
	from sales_performance.services.distribution_engine import ensure_monthly_distribution
	from frappe.utils import cint

	percents = []
	for month in range(1, 13):
		match = next(
			(
				m
				for m in (planning_doc.monthly_details or [])
				if m.row_key == row.row_key and cint(m.month_number) == month
			),
			None,
		)
		percents.append(float(match.distribution_percent) if match else 0)

	if abs(sum(percents) - 100) > 0.05:
		percents = [100.0 / 12] * 11
		percents.append(100.0 - sum(percents))

	safe_key = (row.row_key or "row")[:20]
	name = f"SP-{planning_doc.name}-{safe_key}"[:140]
	return ensure_monthly_distribution(name, percents, planning_doc.fiscal_year)
