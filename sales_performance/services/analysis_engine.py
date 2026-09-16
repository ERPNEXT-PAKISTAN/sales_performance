"""Sales / incentive / payout analysis by dimension for dashboards."""

from sales_performance.services.historical_sales import (
	EXCLUDED_ITEM_GROUPS,
	customer_group_subtree_sql,
	item_group_subtree_sql,
)
from sales_performance.services.numbers import nflt
from sales_performance.services.growth_engine import (
	get_customer_group_subtree_names,
	get_item_group_subtree_names,
)
from sales_performance.services.precision import round_percent


DIMENSIONS = {
	"sales_person": ("ifnull(st.sales_person, '')", True),
	"territory": ("ifnull(si.territory, '')", False),
	"item_group": ("ifnull(sii.item_group, '')", False),
	"customer_group": ("ifnull(si.customer_group, '')", False),
	"customer": ("ifnull(si.customer_name, si.customer)", False),
	"item": ("sii.item_code", False),
}


def variance_row(
	current_qty,
	previous_qty,
	current_amount,
	previous_amount,
	target_qty=0,
	target_amount=0,
	growth_percent=None,
):
	cq, pq = nflt(current_qty), nflt(previous_qty)
	ca, pa = nflt(current_amount), nflt(previous_amount)
	tq, ta = nflt(target_qty), nflt(target_amount)
	# Target-achievement variance is always actual minus target.
	qty_var = nflt(cq - tq)
	amt_var = nflt(ca - ta)
	return {
		"previous_qty": pq,
		"current_qty": cq,
		"qty_variance": qty_var,
		"qty_variance_percent": round_percent(qty_var / tq * 100.0) if tq else None,
		"previous_year_qty_variance": nflt(cq - pq),
		"previous_amount": pa,
		"current_amount": ca,
		"amount_variance": amt_var,
		"amount_variance_percent": round_percent(amt_var / ta * 100.0) if ta else None,
		"previous_year_amount_variance": nflt(ca - pa),
		"target_qty": tq,
		"target_amount": ta,
		"growth_percent": round_percent(growth_percent),
		"qty_achievement_percent": round_percent(cq / tq * 100.0) if tq else None,
		"amount_achievement_percent": round_percent(ca / ta * 100.0) if ta else None,
	}


def fetch_sales_by_dimension(
	company,
	from_date,
	to_date,
	dimension="sales_person",
	sales_person=None,
	territory=None,
	item_group=None,
	customer_group=None,
	customer=None,
	item=None,
	item_codes=None,
):
	"""Invoice qty/amount grouped by one dimension (calendar or FY window)."""
	import frappe
	from frappe.utils import getdate

	expr, needs_team = DIMENSIONS.get(dimension) or DIMENSIONS["sales_person"]
	conditions = [
		"si.docstatus = 1",
		"si.company = %(company)s",
		"si.posting_date between %(from_date)s and %(to_date)s",
		"sii.item_group not in %(excluded_groups)s",
	]
	values = {
		"company": company,
		"from_date": getdate(from_date),
		"to_date": getdate(to_date),
		"excluded_groups": EXCLUDED_ITEM_GROUPS,
	}
	if sales_person:
		conditions.append("st.sales_person = %(sales_person)s")
		values["sales_person"] = sales_person
		needs_team = True
	if territory:
		conditions.append(
			"""si.territory in (
				select child.name from `tabTerritory` child
				inner join `tabTerritory` parent
					on child.lft >= parent.lft and child.rgt <= parent.rgt
				where parent.name = %(territory)s
			)"""
		)
		values["territory"] = territory
	if item_group:
		conditions.append(item_group_subtree_sql())
		values["item_group"] = item_group
	if customer_group:
		conditions.append(customer_group_subtree_sql())
		values["customer_group"] = customer_group
	if customer:
		conditions.append("si.customer = %(customer)s")
		values["customer"] = customer
	if item:
		conditions.append("sii.item_code = %(item)s")
		values["item"] = item
	if item_codes is not None:
		if not item_codes:
			return []
		conditions.append("sii.item_code in %(item_codes)s")
		values["item_codes"] = tuple(item_codes)

	if needs_team:
		sales_join = """left join `tabSales Team` st
			on st.parent = si.name and st.parenttype = 'Sales Invoice'"""
		share = "ifnull(nullif(st.allocated_percentage, 0), 100) / 100"
	else:
		sales_join = ""
		share = "1"

	sql = f"""
		select
			{expr} as dimension,
			sum(sii.stock_qty * {share}) as qty,
			sum(sii.base_net_amount * {share}) as amount
		from `tabSales Invoice Item` sii
		inner join `tabSales Invoice` si on si.name = sii.parent
		{sales_join}
		where {" and ".join(conditions)}
		group by {expr}
		having sum(sii.base_net_amount * {share}) != 0
		order by amount desc
	"""
	return frappe.db.sql(sql, values, as_dict=True)


def fetch_monthly_sales(company, from_date, to_date, **filters):
	import frappe
	from frappe.utils import getdate

	conditions = [
		"si.docstatus = 1",
		"si.company = %(company)s",
		"si.posting_date between %(from_date)s and %(to_date)s",
		"sii.item_group not in %(excluded_groups)s",
	]
	values = {
		"company": company,
		"from_date": getdate(from_date),
		"to_date": getdate(to_date),
		"excluded_groups": EXCLUDED_ITEM_GROUPS,
	}
	needs_team = bool(filters.get("sales_person"))
	if filters.get("sales_person"):
		conditions.append("st.sales_person = %(sales_person)s")
		values["sales_person"] = filters["sales_person"]
	if filters.get("territory"):
		conditions.append(
			"""si.territory in (
				select child.name from `tabTerritory` child
				inner join `tabTerritory` parent
					on child.lft >= parent.lft and child.rgt <= parent.rgt
				where parent.name = %(territory)s
			)"""
		)
		values["territory"] = filters["territory"]
	if filters.get("item_group"):
		conditions.append(item_group_subtree_sql())
		values["item_group"] = filters["item_group"]
	if filters.get("customer_group"):
		conditions.append(customer_group_subtree_sql())
		values["customer_group"] = filters["customer_group"]
	if filters.get("customer"):
		conditions.append("si.customer = %(customer)s")
		values["customer"] = filters["customer"]
	if filters.get("item"):
		conditions.append("sii.item_code = %(item)s")
		values["item"] = filters["item"]
	if filters.get("item_codes") is not None:
		if not filters.get("item_codes"):
			return []
		conditions.append("sii.item_code in %(item_codes)s")
		values["item_codes"] = tuple(filters["item_codes"])
	if needs_team:
		sales_join = """left join `tabSales Team` st
			on st.parent = si.name and st.parenttype = 'Sales Invoice'"""
		share = "ifnull(nullif(st.allocated_percentage, 0), 100) / 100"
	else:
		sales_join = ""
		share = "1"
	return frappe.db.sql(
		f"""
		select month(si.posting_date) as month_number,
			sum(sii.stock_qty * {share}) as qty,
			sum(sii.base_net_amount * {share}) as amount
		from `tabSales Invoice Item` sii
		inner join `tabSales Invoice` si on si.name = sii.parent
		{sales_join}
		where {" and ".join(conditions)}
		group by month(si.posting_date)
		order by month_number
		""",
		values,
		as_dict=True,
	)


def merge_period_rows(current_rows, previous_rows, target_map=None):
	target_map = target_map or {}

	def dim(row):
		if isinstance(row, dict):
			return row.get("dimension") or "(Not Set)"
		return getattr(row, "dimension", None) or "(Not Set)"

	prev = {dim(r): r for r in previous_rows}
	keys = {dim(r) for r in current_rows} | set(prev) | set(target_map)
	out = []
	for key in keys:
		cy = next((r for r in current_rows if dim(r) == key), None)
		py = prev.get(key)
		tgt = target_map.get(key) or {}
		packed = variance_row(
			(cy.get("qty") if isinstance(cy, dict) else getattr(cy, "qty", 0)) if cy else 0,
			(py.get("qty") if isinstance(py, dict) else getattr(py, "qty", 0)) if py else 0,
			(cy.get("amount") if isinstance(cy, dict) else getattr(cy, "amount", 0)) if cy else 0,
			(py.get("amount") if isinstance(py, dict) else getattr(py, "amount", 0)) if py else 0,
			tgt.get("qty"),
			tgt.get("amount"),
			tgt.get("growth_percent"),
		)
		packed["dimension"] = key
		out.append(packed)
	out.sort(key=lambda r: abs(r["amount_variance"]), reverse=True)
	return out


def selected_target_item_codes(company, fiscal_year):
	"""Return the item scope of the latest applicable target plans.

	Dashboards must not report invoice items that are outside Sales Target Planning.
	"""
	import frappe

	plans = frappe.get_all(
		"Sales Target Planning",
		filters={"company": company, "fiscal_year": fiscal_year, "status": ("in", ("Approved", "Calculated", "Under Review"))},
		fields=["name", "status", "planning_version", "sales_person", "territory", "growth_method"],
		order_by="planning_version desc",
	)
	approved = [plan for plan in plans if plan.status == "Approved"]
	latest = {}
	for plan in approved or plans:
		key = (plan.sales_person or "", plan.territory or "")
		if key not in latest:
			latest[key] = plan.name
	if not latest:
		return []
	plans_by_name = {plan.name: plan for plan in plans if plan.name in latest.values()}
	rules_by_plan = {}
	for rule in frappe.get_all(
		"Item Group Growth Rule",
		filters={"parent": ("in", list(latest.values()))},
		fields=["parent", "item_group", "apply_to_children"],
		ignore_permissions=True,
	):
		rules_by_plan.setdefault(rule.parent, []).append(rule)

	children_by_group = {}
	def matches_rule_scope(row):
		plan = plans_by_name.get(row.parent)
		if not plan or plan.growth_method != "Item Group Rules":
			return True
		for rule in rules_by_plan.get(row.parent, []):
			if row.item_group == rule.item_group:
				return True
			if rule.apply_to_children:
				children = children_by_group.setdefault(
					rule.item_group, set(get_item_group_subtree_names(rule.item_group))
				)
				if row.item_group in children:
					return True
		return False

	return sorted({
		row.item_code
		for row in frappe.get_all(
			"Target Proposal Detail",
			filters={"parent": ("in", list(latest.values()))},
			fields=["parent", "item_code", "item_group"],
			ignore_permissions=True,
		)
		if row.item_code and matches_rule_scope(row)
	})


def customer_target_totals(company, fiscal_year, previous_start, previous_end, **filters):
	"""Allocate the stored plan total to customers by their prior-year sales share."""
	scoped = dict(filters)
	scoped.pop("customer", None)
	history = fetch_sales_by_dimension(company, previous_start, previous_end, "customer", **scoped)
	visible_history = history
	if filters.get("customer"):
		visible_history = fetch_sales_by_dimension(company, previous_start, previous_end, "customer", **filters)
	base_targets = target_totals_by_dimension(company, fiscal_year, "sales_person", **scoped)
	total_qty = sum(nflt(row.get("qty")) for row in base_targets.values())
	total_amount = sum(nflt(row.get("amount")) for row in base_targets.values())
	total_history_qty = sum(nflt(row.get("qty")) for row in history)
	total_history_amount = sum(nflt(row.get("amount")) for row in history)
	if not total_history_qty and not total_history_amount:
		return {}
	return {
		row.get("dimension"): {
			"qty": nflt(total_qty * nflt(row.get("qty")) / total_history_qty) if total_history_qty else 0,
			"amount": nflt(total_amount * nflt(row.get("amount")) / total_history_amount) if total_history_amount else 0,
			"growth_percent": round_percent((total_qty / total_history_qty - 1) * 100) if total_history_qty else None,
		}
		for row in visible_history
	}

def target_totals_by_dimension(company, fiscal_year, dimension="sales_person", **filters):
	"""Use filtered targets from only the latest plan in each planning scope."""
	import frappe

	field = {
		"sales_person": "sales_person",
		"territory": "territory",
		"item_group": "item_group",
		"customer_group": "customer_group",
		"item": "item_code",
	}.get(dimension)
	if not field:
		return {}
	# Proposal rows have no Customer field. Do not repeat a target for every
	# customer and present a false achievement percentage.
	if filters.get("customer"):
		return {}
	if not frappe.db.has_column("Target Proposal Detail", field):
		return {}
	plans = frappe.get_all(
		"Sales Target Planning",
		filters={"company": company, "fiscal_year": fiscal_year, "status": ("in", ("Approved", "Calculated", "Under Review"))},
		fields=["name", "status", "planning_version", "sales_person", "territory"],
		order_by="planning_version desc",
	)
	approved = [p for p in plans if p.status == "Approved"]
	use = approved or plans
	latest = {}
	for plan in use:
		key = (plan.get("sales_person") or "", plan.get("territory") or "")
		if key not in latest:
			latest[key] = plan
	use = list(latest.values())
	if not use:
		return {}
	rows = frappe.get_all(
		"Target Proposal Detail",
		filters={"parent": ("in", [p.name for p in use])},
		fields=[
			field,
			"sales_person",
			"territory",
			"item_group",
			"customer_group",
			"item_code",
			"approved_target_qty",
			"approved_target_amount",
			"growth_percent",
			"previous_year_actual_qty",
		],
		ignore_permissions=True,
	)
	allowed_item_groups = set(get_item_group_subtree_names(filters.get("item_group"))) if filters.get("item_group") else None
	allowed_customer_groups = set(get_customer_group_subtree_names(filters.get("customer_group"))) if filters.get("customer_group") else None
	out = {}
	for row in rows:
		if filters.get("item_codes") is not None and row.get("item_code") not in filters.get("item_codes"):
			continue
		# Preserve unallocated rows in an unfiltered dimension tab. They are
		# labelled explicitly below, rather than being silently dropped. A selected
		# Territory/Customer Group still filters them out in the matching checks.
		if filters.get("sales_person") and row.get("sales_person") != filters.get("sales_person"):
			continue
		if filters.get("territory") and row.get("territory") != filters.get("territory"):
			continue
		if allowed_item_groups is not None and row.get("item_group") not in allowed_item_groups:
			continue
		if allowed_customer_groups is not None and row.get("customer_group") not in allowed_customer_groups:
			continue
		if filters.get("item") and row.get("item_code") != filters.get("item"):
			continue
		key = row.get(field) or "(Unallocated)"
		bucket = out.setdefault(key, {"qty": 0.0, "amount": 0.0, "growth_weight": 0.0, "growth_weighted": 0.0})
		bucket["qty"] += nflt(row.approved_target_qty)
		bucket["amount"] += nflt(row.approved_target_amount)
		weight = nflt(row.previous_year_actual_qty) or nflt(row.approved_target_qty) or 1.0
		bucket["growth_weight"] += weight
		bucket["growth_weighted"] += nflt(row.growth_percent) * weight
	for bucket in out.values():
		w = bucket.pop("growth_weight", 0)
		weighted = bucket.pop("growth_weighted", 0)
		bucket["growth_percent"] = round_percent(weighted / w) if w else None
	return out


def payout_analysis(company, fiscal_year, sales_person=None):
	import frappe

	filters = {"company": company, "fiscal_year": fiscal_year, "docstatus": ("<", 2)}
	fields = ["name", "sales_person", "period", "month", "docstatus", "total_incentive_amount", "posting_date"]
	meta = frappe.get_meta("Sales Incentive Payout")
	if meta.has_field("payment_status"):
		fields.append("payment_status")
	docs = frappe.get_all(
		"Sales Incentive Payout",
		filters=filters,
		fields=fields,
		order_by="creation desc",
		limit=100,
	)
	if sales_person:
		docs = [d for d in docs if not d.sales_person or d.sales_person == sales_person]
	items = []
	names = [d.name for d in docs]
	if names:
		items = frappe.get_all(
			"Sales Incentive Payout Item",
			filters={"parent": ("in", names)},
			fields=["parent", "sales_person", "period", "incentive_amount", "incentive_band"],
			ignore_permissions=True,
		)
	by_person = {}
	for row in items:
		if sales_person and row.sales_person != sales_person:
			continue
		key = row.sales_person or "(Not Set)"
		bucket = by_person.setdefault(key, {"dimension": key, "incentive_amount": 0.0, "rows": 0})
		bucket["incentive_amount"] += nflt(row.incentive_amount)
		bucket["rows"] += 1
	accrued = sum(nflt(d.total_incentive_amount) for d in docs if d.docstatus == 1)
	paid = sum(
		nflt(d.total_incentive_amount)
		for d in docs
		if d.docstatus == 1 and d.get("payment_status") == "Paid"
	)
	draft = sum(nflt(d.total_incentive_amount) for d in docs if d.docstatus == 0)
	return {
		"documents": docs,
		"by_sales_person": sorted(by_person.values(), key=lambda r: r["incentive_amount"], reverse=True),
		"totals": {
			"draft": draft,
			"accrued": accrued,
			"paid": paid,
			"unpaid": max(accrued - paid, 0),
			"count": len(docs),
		},
	}


def summarize_rows(rows):
	qty = sum(nflt(r.get("current_qty")) for r in rows)
	pq = sum(nflt(r.get("previous_qty")) for r in rows)
	amt = sum(nflt(r.get("current_amount")) for r in rows)
	pa = sum(nflt(r.get("previous_amount")) for r in rows)
	tq = sum(nflt(r.get("target_qty")) for r in rows)
	ta = sum(nflt(r.get("target_amount")) for r in rows)
	pairs = []
	for r in rows:
		if r.get("growth_percent") in (None, ""):
			continue
		w = nflt(r.get("previous_qty")) or nflt(r.get("target_qty")) or 1.0
		pairs.append((nflt(r.get("growth_percent")), w))
	base = variance_row(qty, pq, amt, pa, tq, ta)
	if pairs:
		tw = sum(w for _g, w in pairs)
		base["growth_percent"] = round_percent(sum(g * w for g, w in pairs) / tw) if tw else None
	base["up_count"] = sum(1 for r in rows if nflt(r.get("amount_variance")) > 0)
	base["down_count"] = sum(1 for r in rows if nflt(r.get("amount_variance")) < 0)
	return base
