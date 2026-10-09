"""Shared selection of active plans for achievement and analytics."""


def applicable_plans(plans):
	"""Keep every approved allocation; otherwise use latest provisional scopes.

	Approval explicitly supersedes the previous revision. Independent approved
	plans can share header dimensions and must not suppress one another.
	"""
	approved = [plan for plan in plans if plan.get("status") == "Approved"]
	if approved:
		return approved
	latest = {}
	for plan in sorted(plans, key=lambda p: p.get("planning_version") or 0, reverse=True):
		if plan.get("status") not in ("Calculated", "Under Review"):
			continue
		key = (plan.get("sales_person") or "", plan.get("territory") or "")
		latest.setdefault(key, plan)
	return list(latest.values())


def target_rows(company, fiscal_year, approved_only=False):
	"""Read the saved proposal table, with parent dimensions for legacy rows."""
	import frappe
	plans = frappe.get_all("Sales Target Planning",
		filters={"company": company, "fiscal_year": fiscal_year,
			"status": "Approved" if approved_only else ("in", ("Approved", "Calculated", "Under Review"))},
		fields=["name", "status", "planning_version", "sales_person", "territory", "customer_group"],
		order_by="planning_version desc")
	plans = {p.name: p for p in applicable_plans(plans)}
	if not plans:
		return []
	rows = frappe.get_all("Target Proposal Detail",
		filters={"parent": ("in", list(plans)), "parenttype": "Sales Target Planning", "parentfield": "proposal_details"},
		fields=["parent", "row_key", "sales_person", "territory", "customer_group", "item_group",
			"item_code", "approved_target_qty", "approved_target_amount", "growth_percent", "previous_year_actual_qty"])
	for row in rows:
		for field in ("sales_person", "territory", "customer_group"):
			row[field] = row.get(field) or plans[row.parent].get(field)
	return rows


def target_sales_condition(rows, values):
	"""Match invoice allocations to proposal grains without multiplying sales."""
	groups = {}
	for row in rows:
		if not row.get("item_code"):
			continue
		grain = tuple(row.get(f) or "" for f in ("sales_person", "territory", "customer_group"))
		groups.setdefault(grain, set()).add(row["item_code"])
	clauses = []
	for index, (grain, items) in enumerate(sorted(groups.items())):
		key = f"target_items_{index}"
		values[key] = tuple(sorted(items))
		parts = [f"sii.item_code in %({key})s"]
		for field, expression, value in zip(("person", "territory", "group"),
			("st.sales_person", "si.territory", "si.customer_group"), grain):
			if value:
				key = f"target_{field}_{index}"
				values[key] = value
				parts.append(f"{expression} = %({key})s")
		clauses.append("(" + " and ".join(parts) + ")")
	return "(" + " or ".join(clauses) + ")" if clauses else "1=0"
