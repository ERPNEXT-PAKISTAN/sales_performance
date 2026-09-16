"""Resolve min/max incentive rates from achievement slabs. No payout storage."""

from sales_performance.services.numbers import nflt
from sales_performance.services.precision import get_currency_precision, round_percent


def resolve_incentive_rate(achievement_percent, slabs):
	"""Return (rate_percent, band) for an achievement %.

	Band is None (not achieved), "Min", or "Max".
	Inside a slab: min_achievement <= achievement < max_achievement → min rate.
	achievement >= max_achievement → max rate.
	"""
	achievement = nflt(achievement_percent)
	best = (0.0, None)
	for slab in slabs or []:
		min_ach = nflt(slab.get("min_achievement_percent"))
		max_ach = slab.get("max_achievement_percent")
		max_ach = nflt(max_ach) if max_ach not in (None, "") else None
		min_rate = nflt(slab.get("min_incentive_percent") or slab.get("incentive_percent"))
		max_rate = slab.get("max_incentive_percent")
		max_rate = nflt(max_rate) if max_rate not in (None, "") else min_rate
		if achievement < min_ach:
			continue
		if max_ach is None or achievement < max_ach:
			best = (min_rate, "Min")
		else:
			best = (max_rate, "Max")
	return best


def normalize_pay_on(value):
	text = str(value or "Amount")
	return "Qty" if text.strip().lower().startswith("qty") else "Amount"


def empty_incentive(pay_on="Amount"):
	return {
		"incentive_rate_percent": 0.0,
		"incentive_qty": 0.0,
		"incentive_on_amount": 0.0,
		"incentive_on_qty": 0.0,
		"incentive_amount": 0.0,
		"incentive_band": "",
		"pay_on": normalize_pay_on(pay_on),
	}


def incentive_on_surplus(
	actual_qty,
	target_qty,
	actual_amount,
	target_amount,
	rate_percent,
	pay_on="Amount",
):
	"""Pay incentive only on surplus of the scheme's Pay On metric.

	No payable (and no qty/amount incentive columns) unless the rate is earned
	and that metric beat target. The unused Pay On column stays zero.
	"""
	pay_on = normalize_pay_on(pay_on)
	rate = nflt(rate_percent) / 100.0
	if rate <= 0:
		return empty_incentive(pay_on)

	surplus_qty = max(nflt(actual_qty) - nflt(target_qty), 0)
	surplus_amount = max(nflt(actual_amount) - nflt(target_amount), 0)
	if pay_on == "Qty":
		if surplus_qty <= 0:
			return empty_incentive(pay_on)
		qty_pay = nflt(surplus_qty * rate)
		return {
			"incentive_rate_percent": round_percent(rate_percent) or 0.0,
			"incentive_qty": qty_pay,
			"incentive_on_qty": qty_pay,
			"incentive_on_amount": 0.0,
			"incentive_amount": qty_pay,
			"pay_on": pay_on,
		}

	if surplus_amount <= 0:
		return empty_incentive(pay_on)
	amount_pay = nflt(surplus_amount * rate, get_currency_precision())
	return {
		"incentive_rate_percent": round_percent(rate_percent) or 0.0,
		"incentive_qty": 0.0,
		"incentive_on_qty": 0.0,
		"incentive_on_amount": amount_pay,
		"incentive_amount": amount_pay,
		"pay_on": pay_on,
	}


def apply_scheme_payout(
	target_qty,
	actual_qty,
	target_amount,
	actual_amount,
	slabs,
	based_on,
	pay_on,
):
	"""Score this row's totals against Incentive Scheme slabs. Under-target = 0."""
	from sales_performance.services.achievement_engine import compute_metrics

	metrics = compute_metrics(target_qty, actual_qty, target_amount, actual_amount)
	pay_on = normalize_pay_on(pay_on)
	achievement = (
		metrics["amount_achievement_percent"]
		if based_on == "Amount Achievement"
		else metrics["qty_achievement_percent"]
	)
	rate, band = resolve_incentive_rate(achievement, slabs)
	payout = incentive_on_surplus(
		actual_qty,
		target_qty,
		actual_amount,
		target_amount,
		rate if band else 0,
		pay_on,
	)
	if nflt(payout.get("incentive_amount")) <= 0:
		metrics.update(empty_incentive(pay_on))
		return metrics
	metrics.update(payout)
	metrics["incentive_band"] = band or ""
	return metrics


def load_scheme_slabs(company=None, fiscal_year=None):
	import frappe

	filters = {"disabled": 0}
	if company:
		filters["company"] = company
	fields = ["name", "fiscal_year", "based_on"]
	meta = frappe.get_meta("Incentive Scheme")
	if meta.has_field("pay_on"):
		fields.append("pay_on")
	schemes = frappe.get_all(
		"Incentive Scheme",
		filters=filters,
		fields=fields,
		order_by="modified desc",
	)
	if fiscal_year:
		matched = [s for s in schemes if s.fiscal_year == fiscal_year] or [
			s for s in schemes if not s.fiscal_year
		]
		schemes = matched
	if not schemes:
		return [], "Qty Achievement", "Amount"
	scheme = schemes[0]
	slabs = frappe.get_all(
		"Incentive Scheme Slab",
		filters={"parent": scheme.name},
		fields=[
			"min_achievement_percent",
			"max_achievement_percent",
			"incentive_percent",
			"min_incentive_percent",
			"max_incentive_percent",
		],
		order_by="min_achievement_percent asc",
		ignore_permissions=True,
	)
	return slabs, scheme.based_on or "Qty Achievement", normalize_pay_on(scheme.get("pay_on"))


def scheme_settings(filters):
	slabs, based_on, pay_on = load_scheme_slabs(filters.get("company"), filters.get("fiscal_year"))
	if filters.get("pay_on"):
		pay_on = normalize_pay_on(filters.get("pay_on"))
	return slabs, based_on, pay_on


def metrics_with_monthly_incentive(
	month_target,
	month_qty,
	month_amount,
	months,
	slabs,
	based_on,
	pay_on,
):
	"""Sum target/actual for the period, then apply the scheme to those totals.

	Incentive is paid only when this row's achievement meets the scheme and the
	Pay On metric is above target. A strong month does not pay if the period missed.
	"""
	target_qty = target_amount = actual_qty = actual_amount = 0.0
	for month in months:
		part = month_target.get(month) or {}
		target_qty += nflt(part.get("target_qty"))
		target_amount += nflt(part.get("target_amount"))
		actual_qty += nflt(month_qty.get(month))
		actual_amount += nflt(month_amount.get(month))
	return apply_scheme_payout(
		target_qty, actual_qty, target_amount, actual_amount, slabs, based_on, pay_on
	)


def collect_achievement_rows(filters):
	"""Item-wise annual achievement. Incentive follows the scheme on year totals."""
	import frappe

	filters = frappe._dict(filters or {})
	filters.period = "Annual"
	filters.month = None
	filters.quarter = None
	return collect_period_incentive_rows(filters)


def summarize_payout_by_sales_person(rows, slabs=None, based_on="Qty Achievement", pay_on="Amount"):
	"""One payable line per sales person.

	When slabs are passed, incentive is recalculated on that person's totals so
	a miss versus target does not keep child-row surplus.
	"""
	grouped = {}
	for row in rows:
		key = (
			row.get("sales_person") or "(Not Set)",
			row.get("period") or "",
			row.get("customer_group") or "",
		)
		bucket = grouped.setdefault(
			key,
			{
				"sales_person": row.get("sales_person") or "",
				"customer_group": row.get("customer_group") or "",
				"period": row.get("period") or "",
				"month_number": row.get("month_number") or 0,
				"target_qty": 0.0,
				"actual_qty": 0.0,
				"target_amount": 0.0,
				"actual_amount": 0.0,
				"incentive_band": row.get("incentive_band") or "",
				"incentive_rate_percent": nflt(row.get("incentive_rate_percent")),
				"incentive_qty": 0.0,
				"incentive_amount": 0.0,
				"incentive_on_amount": 0.0,
				"incentive_on_qty": 0.0,
			},
		)
		bucket["target_qty"] += nflt(row.get("target_qty"))
		bucket["actual_qty"] += nflt(row.get("actual_qty"))
		bucket["target_amount"] += nflt(row.get("target_amount"))
		bucket["actual_amount"] += nflt(row.get("actual_amount"))
		amount = nflt(row.get("incentive_amount"))
		if amount > 0:
			bucket["incentive_qty"] += nflt(row.get("incentive_qty"))
			bucket["incentive_amount"] += amount
			bucket["incentive_on_amount"] += nflt(row.get("incentive_on_amount"))
			bucket["incentive_on_qty"] += nflt(row.get("incentive_on_qty"))
			if nflt(row.get("incentive_rate_percent")) >= nflt(bucket["incentive_rate_percent"]):
				bucket["incentive_rate_percent"] = nflt(row.get("incentive_rate_percent"))
				bucket["incentive_band"] = row.get("incentive_band") or bucket["incentive_band"]
	out = []
	for bucket in grouped.values():
		if slabs is not None:
			paid = apply_scheme_payout(
				bucket["target_qty"],
				bucket["actual_qty"],
				bucket["target_amount"],
				bucket["actual_amount"],
				slabs,
				based_on,
				pay_on,
			)
			if nflt(paid.get("incentive_amount")) <= 0:
				continue
			bucket.update(paid)
		elif nflt(bucket.get("incentive_amount")) <= 0:
			continue
		out.append(bucket)
	return out


def period_buckets(view, month=None, quarter=None):
	"""Return [(label, [month_numbers])] for Monthly / Quarterly / Annual."""
	from sales_performance.services.distribution_engine import MONTHS

	view = view or "Annual"
	if view == "Monthly":
		if month:
			m = int(month)
			return [(MONTHS[m - 1], [m])]
		return [(MONTHS[i], [i + 1]) for i in range(12)]
	if view == "Quarterly":
		quarters = [("Q1", [1, 2, 3]), ("Q2", [4, 5, 6]), ("Q3", [7, 8, 9]), ("Q4", [10, 11, 12])]
		if quarter:
			q = int(quarter)
			return [quarters[q - 1]]
		return quarters
	return [("Annual", list(range(1, 13)))]


def collect_period_incentive_rows(filters):
	"""Collect target/actual rows at the planning grain for a selected period."""
	import frappe
	from frappe.utils import getdate

	from sales_performance.services.distribution_engine import equal_monthly
	from sales_performance.services.growth_engine import get_customer_group_subtree_names, get_item_group_subtree_names
	from sales_performance.services.historical_sales import fetch_historical_sales
	from sales_performance.services.planning_engine import fiscal_year_dates
	from sales_performance.services.analysis_engine import selected_target_item_codes

	filters = frappe._dict(filters or {})
	if not filters.get("company") or not filters.get("fiscal_year"):
		return []

	plan_fields = ["name", "planning_version", "sales_person", "territory"]
	if frappe.db.has_column("Sales Target Planning", "customer_group"):
		plan_fields.append("customer_group")
	plans = frappe.get_all(
		"Sales Target Planning",
		filters={"company": filters.company, "fiscal_year": filters.fiscal_year, "status": "Approved"},
		fields=plan_fields,
		order_by="planning_version desc",
	)
	if not plans:
		plans = frappe.get_all(
			"Sales Target Planning",
			filters={
				"company": filters.company,
				"fiscal_year": filters.fiscal_year,
				"status": ("in", ("Calculated", "Under Review")),
			},
			fields=plan_fields,
			order_by="planning_version desc",
		)
	if not plans:
		return []

	latest = {}
	for p in plans:
		key = (p.sales_person or "", p.territory or "")
		if key not in latest:
			latest[key] = p.name
	latest_plans = {p.name: p for p in plans if p.name in latest.values()}

	detail_fields = [
		"parent",
		"row_key",
		"sales_person",
		"territory",
		"item_group",
		"item_code",
		"approved_target_qty",
		"approved_target_amount",
		"growth_percent",
	]
	if frappe.db.has_column("Target Proposal Detail", "customer_group"):
		detail_fields.append("customer_group")
	rows = frappe.get_all(
		"Target Proposal Detail",
		filters={"parent": ("in", list(latest.values()))},
		fields=detail_fields,
		ignore_permissions=True,
	)
	# Older detail rows can predate these dimensions. The parent plan remains
	# authoritative for their scope, so retain it for report output and matching.
	for row in rows:
		plan = latest_plans.get(row.parent)
		if not plan:
			continue
		if not row.get("territory") and plan.get("territory"):
			row.territory = plan.territory
		if not row.get("customer_group") and plan.get("customer_group"):
			row.customer_group = plan.customer_group
	# Keep all achievement and incentive outputs on the same item-group rule
	# scope as Performance Analytics, including plans revised after their rows
	# were originally calculated.
	allowed_item_codes = set(selected_target_item_codes(filters.company, filters.fiscal_year))
	rows = [row for row in rows if row.item_code in allowed_item_codes]
	# Proposal rows define the scope of achievement and incentive actuals,
	# including when only selected items in an item group were planned.
	planned_item_codes = sorted({row.item_code for row in rows if row.item_code})
	if not planned_item_codes:
		return []
	monthly_targets = {}
	for part in frappe.get_all(
		"Sales Target Monthly Detail",
		filters={"parent": ("in", list(latest.values()))},
		fields=["parent", "row_key", "month_number", "target_qty", "target_amount"],
		ignore_permissions=True,
	):
		monthly_targets.setdefault((part.parent, part.row_key), {})[part.month_number] = part

	start, end = fiscal_year_dates(filters.fiscal_year, filters.company)
	from_date = getdate(filters.get("from_date") or start)
	to_date = getdate(filters.get("to_date") or end)
	actuals = fetch_historical_sales(
		company=filters.company,
		from_date=from_date,
		to_date=to_date,
		sales_person=filters.get("sales_person"),
		territory=filters.get("territory"),
		item_group=filters.get("item_group"),
		customer_group=filters.get("customer_group"),
		item_codes=[filters.item] if filters.get("item") else planned_item_codes,
		include_monthly=True,
	)
	slabs, based_on, pay_on = scheme_settings(filters)
	buckets = period_buckets(filters.get("period"), filters.get("month"), filters.get("quarter"))
	allowed_groups = None
	if filters.get("item_group"):
		allowed_groups = set(get_item_group_subtree_names(filters.item_group))
	allowed_customer_groups = None
	if filters.get("customer_group"):
		allowed_customer_groups = set(get_customer_group_subtree_names(filters.customer_group))
	seen = set()
	# A blank legacy customer-group row is a wildcard only when no specific
	# allocation exists for the same Sales Person/Territory/Item.
	specific_customer_groups = {
		(row.sales_person or "", row.territory or "", row.item_code or "")
		for row in rows
		if row.get("customer_group")
	}
	# The equivalent guard protects legacy blank-territory rows as well.
	specific_territories = {
		(row.sales_person or "", row.item_code or "", row.get("customer_group") or "")
		for row in rows
		if row.territory
	}
	out = []
	for row in rows:
		if filters.get("sales_person") and row.sales_person != filters.sales_person:
			continue
		if filters.get("territory") and row.territory != filters.territory:
			continue
		if allowed_groups is not None and (row.item_group or "") not in allowed_groups:
			continue
		# An unallocated row cannot represent a selected customer group.
		if allowed_customer_groups is not None and (
			not row.get("customer_group") or row.get("customer_group") not in allowed_customer_groups
		):
			continue
		if filters.get("item") and row.item_code != filters.item:
			continue
		grain = (
			row.sales_person or "",
			row.territory or "",
			row.item_code or "",
			row.get("customer_group") or "",
		)
		if grain in seen:
			continue
		seen.add(grain)
		actual = actuals.get(grain)
		if actual is None:
			# Legacy plans may have been calculated before territory/customer-group
			# were retained in the grain. Aggregate only matching dimensions so
			# their actual quantity remains visible without pulling unrelated items.
			base = (row.sales_person or "", row.territory or "", row.item_code or "")
			can_use_blank_customer_group = bool(row.get("customer_group")) or base not in specific_customer_groups
			territory_base = (row.sales_person or "", row.item_code or "", row.get("customer_group") or "")
			can_use_blank_territory = bool(row.territory) or territory_base not in specific_territories
			matches = [
				value for key, value in actuals.items()
				if key[2] == row.item_code
				and (not row.sales_person or key[0] == row.sales_person)
				and (not row.territory or key[1] == row.territory)
				and (not row.get("customer_group") or key[3] == row.get("customer_group"))
				and can_use_blank_customer_group
				and can_use_blank_territory
			]
			actual = {
				"month_qty": {month: sum(nflt(value.get("month_qty", {}).get(month)) for value in matches) for month in range(1, 13)},
				"month_amount": {month: sum(nflt(value.get("month_amount", {}).get(month)) for value in matches) for month in range(1, 13)},
			}
		# Monthly detail is authoritative. A legacy plan without it is displayed
		# with a read-only stable equal split; approved annual targets stay intact.
		month_target = monthly_targets.get((row.parent, row.row_key)) or {
			part["month_number"]: part
			for part in equal_monthly(row.approved_target_qty, row.approved_target_amount)
		}
		month_qty = actual.get("month_qty") or {}
		month_amount = actual.get("month_amount") or {}
		for label, months in buckets:
			metrics = metrics_with_monthly_incentive(
				month_target, month_qty, month_amount, months, slabs, based_on, pay_on
			)
			metrics.update(
				{
					"period": label,
					"month_number": months[0] if len(months) == 1 else 0,
					"sales_person": row.sales_person,
					"territory": row.territory,
					"item_group": row.item_group,
					"customer_group": row.get("customer_group"),
					"item_code": row.item_code,
					"planning": row.parent,
					"growth_percent": round_percent(row.get("growth_percent")),
				}
			)
			out.append(metrics)
	return out


def group_dashboard_rows(rows, group_by="sales_person", slabs=None, based_on="Qty Achievement", pay_on="Amount"):
	field = {
		"sales_person": "sales_person",
		"territory": "territory",
		"item_group": "item_group",
		"customer_group": "customer_group",
		"item": "item_code",
		"period": "period",
	}.get(group_by or "sales_person", "sales_person")
	grouped = {}
	for row in rows:
		key = row.get(field) or "(Unallocated)"
		bucket = grouped.setdefault(
			key,
			{
				"dimension": key,
				"target_qty": 0.0,
				"actual_qty": 0.0,
				"target_amount": 0.0,
				"actual_amount": 0.0,
			},
		)
		bucket["target_qty"] += nflt(row.get("target_qty"))
		bucket["actual_qty"] += nflt(row.get("actual_qty"))
		bucket["target_amount"] += nflt(row.get("target_amount"))
		bucket["actual_amount"] += nflt(row.get("actual_amount"))
	out = []
	for bucket in grouped.values():
		paid = apply_scheme_payout(
			bucket["target_qty"],
			bucket["actual_qty"],
			bucket["target_amount"],
			bucket["actual_amount"],
			slabs,
			based_on,
			pay_on,
		)
		bucket.update(paid)
		bucket["min_incentive_amount"] = paid["incentive_amount"] if paid.get("incentive_band") == "Min" else 0.0
		bucket["max_incentive_amount"] = paid["incentive_amount"] if paid.get("incentive_band") == "Max" else 0.0
		out.append(bucket)
	out.sort(key=lambda r: r["incentive_amount"], reverse=True)
	return out


def dashboard_totals(rows, slabs=None, based_on="Qty Achievement", pay_on="Amount"):
	target_qty = sum(nflt(r.get("target_qty")) for r in rows)
	actual_qty = sum(nflt(r.get("actual_qty")) for r in rows)
	target_amount = sum(nflt(r.get("target_amount")) for r in rows)
	actual_amount = sum(nflt(r.get("actual_amount")) for r in rows)
	paid = apply_scheme_payout(
		target_qty, actual_qty, target_amount, actual_amount, slabs, based_on, pay_on
	)
	paid["min_incentive_amount"] = paid["incentive_amount"] if paid.get("incentive_band") == "Min" else 0.0
	paid["max_incentive_amount"] = paid["incentive_amount"] if paid.get("incentive_band") == "Max" else 0.0
	paid["rows_with_incentive"] = sum(1 for r in rows if nflt(r.get("incentive_amount")) > 0)
	return paid
