"""Idempotent sync of approved plans onto ERPNext Sales Person / Territory Target Detail."""

from frappe.utils import cint, flt, now_datetime


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

	# Group rows by parent document so each Sales Person / Territory is saved once.
	grouped = {}
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
		parent_doc = frappe.get_doc(parenttype, parent)
		for row in rows:
			dist_name = _distribution_for_row(planning_doc, row)
			key = planning_key(
				planning_doc.name,
				row.sales_person,
				row.territory,
				row.item_code,
				row.item_group,
			)
			payload = {
				"item_group": row.item_group,
				"fiscal_year": fiscal_year,
				"target_qty": qty_of(row),
				"target_amount": amount_of(row),
				"distribution_id": dist_name,
				"custom_source_planning": planning_doc.name,
				"custom_planning_version": version,
				"custom_planning_key": key,
				"custom_approved_by": approved_by,
				"custom_approved_on": approved_on,
			}
			if has_item:
				payload["item"] = row.item_code
			existing = _match_child(parent_doc, fiscal_year, key, row, has_item, planning_doc.name)
			if existing:
				for field, value in payload.items():
					existing.set(field, value)
			else:
				parent_doc.append("targets", payload)
			synced += 1
		parent_doc.flags.ignore_validate_update_after_submit = True
		parent_doc.save(ignore_permissions=True)

	planning_doc.db_set("erpnext_targets_synced_on", now_datetime())
	return synced


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
