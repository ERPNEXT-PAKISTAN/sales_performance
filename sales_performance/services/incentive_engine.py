"""Resolve min/max incentive rates from achievement slabs. No payout storage."""

from sales_performance.services.numbers import nflt


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


def incentive_on_surplus(
	actual_qty,
	target_qty,
	actual_amount,
	target_amount,
	rate_percent,
	pay_on="Amount",
):
	"""Pay incentive only on surplus above target.

	Amount: surplus amount × rate %.
	Qty: surplus qty × rate %  (not converted by selling price).
	"""
	rate = nflt(rate_percent) / 100.0
	surplus_qty = max(nflt(actual_qty) - nflt(target_qty), 0)
	surplus_amount = max(nflt(actual_amount) - nflt(target_amount), 0)
	qty_pay = nflt(surplus_qty * rate)
	amount_pay = nflt(surplus_amount * rate)
	if normalize_pay_on(pay_on) == "Qty":
		incentive_amount = qty_pay
	else:
		incentive_amount = amount_pay
	return {
		"incentive_rate_percent": nflt(rate_percent),
		"incentive_qty": qty_pay,
		"incentive_on_amount": amount_pay,
		"incentive_on_qty": qty_pay,
		"incentive_amount": incentive_amount,
		"pay_on": normalize_pay_on(pay_on),
	}


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
	"""Target/actual are summed across months. Incentive is summed month-by-month.

	A month that misses target does not reduce incentive already earned in a month
	that beat target. Annual/quarter totals are therefore >= any single month.
	"""
	from sales_performance.services.achievement_engine import compute_metrics

	target_qty = target_amount = actual_qty = actual_amount = 0.0
	incentive_amount = incentive_qty = incentive_on_amount = incentive_on_qty = 0.0
	weighted_rate = 0.0
	surplus_weight = 0.0
	bands = []
	for month in months:
		part = month_target.get(month) or {}
		mtq = nflt(part.get("target_qty"))
		mta = nflt(part.get("target_amount"))
		maq = nflt(month_qty.get(month))
		maa = nflt(month_amount.get(month))
		target_qty += mtq
		target_amount += mta
		actual_qty += maq
		actual_amount += maa
		month_metrics = compute_metrics(mtq, maq, mta, maa)
		achievement = (
			month_metrics["amount_achievement_percent"]
			if based_on == "Amount Achievement"
			else month_metrics["qty_achievement_percent"]
		)
		rate, band = resolve_incentive_rate(achievement, slabs)
		payout = incentive_on_surplus(maq, mtq, maa, mta, rate if band else 0, pay_on)
		incentive_amount += nflt(payout["incentive_amount"])
		incentive_qty += nflt(payout["incentive_qty"])
		incentive_on_amount += nflt(payout.get("incentive_on_amount"))
		incentive_on_qty += nflt(payout.get("incentive_on_qty"))
		weight = max(maq - mtq, 0) if normalize_pay_on(pay_on) == "Qty" else max(maa - mta, 0)
		if band:
			bands.append(band)
			weighted_rate += nflt(payout["incentive_rate_percent"]) * (weight or 1.0)
			surplus_weight += weight or 1.0
	metrics = compute_metrics(target_qty, actual_qty, target_amount, actual_amount)
	uniq = set(bands)
	metrics.update(
		{
			"incentive_amount": nflt(incentive_amount),
			"incentive_qty": nflt(incentive_qty),
			"incentive_on_amount": nflt(incentive_on_amount),
			"incentive_on_qty": nflt(incentive_on_qty),
			"incentive_rate_percent": nflt(weighted_rate / surplus_weight, 2) if surplus_weight else 0.0,
			"incentive_band": next(iter(uniq)) if len(uniq) == 1 else ("Mixed" if uniq else ""),
			"pay_on": normalize_pay_on(pay_on),
		}
	)
	return metrics


def collect_achievement_rows(filters):
	"""Item-wise annual achievement. Incentive = sum of monthly incentives (no clawback)."""
	import frappe

	filters = frappe._dict(filters or {})
	filters.period = "Annual"
	filters.month = None
	filters.quarter = None
	return collect_period_incentive_rows(filters)


def summarize_payout_by_sales_person(rows):
	"""One payable line per sales person (sums item-wise incentive)."""
	grouped = {}
	for row in rows:
		amount = nflt(row.get("incentive_amount"))
		if amount <= 0:
			continue
		key = (row.get("sales_person") or "(Not Set)", row.get("period") or "")
		bucket = grouped.setdefault(
			key,
			{
				"sales_person": row.get("sales_person") or "",
				"period": row.get("period") or "",
				"month_number": row.get("month_number") or 0,
				"incentive_band": row.get("incentive_band") or "",
				"incentive_rate_percent": nflt(row.get("incentive_rate_percent")),
				"incentive_qty": 0.0,
				"incentive_amount": 0.0,
				"incentive_on_amount": 0.0,
				"incentive_on_qty": 0.0,
			},
		)
		bucket["incentive_qty"] += nflt(row.get("incentive_qty"))
		bucket["incentive_amount"] += amount
		bucket["incentive_on_amount"] += nflt(row.get("incentive_on_amount"))
		bucket["incentive_on_qty"] += nflt(row.get("incentive_on_qty"))
		if nflt(row.get("incentive_rate_percent")) >= nflt(bucket["incentive_rate_percent"]):
			bucket["incentive_rate_percent"] = nflt(row.get("incentive_rate_percent"))
			bucket["incentive_band"] = row.get("incentive_band") or bucket["incentive_band"]
	return list(grouped.values())


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
	"""Incentive by month or quarter. Targets split equally across 12 months."""
	import frappe
	from frappe.utils import getdate

	from sales_performance.services.distribution_engine import equal_monthly
	from sales_performance.services.historical_sales import fetch_historical_sales
	from sales_performance.services.planning_engine import fiscal_year_dates

	filters = frappe._dict(filters or {})
	if not filters.get("company") or not filters.get("fiscal_year"):
		return []

	plans = frappe.get_all(
		"Sales Target Planning",
		filters={"company": filters.company, "fiscal_year": filters.fiscal_year, "status": "Approved"},
		fields=["name", "planning_version", "sales_person", "territory"],
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
			fields=["name", "planning_version", "sales_person", "territory"],
			order_by="planning_version desc",
		)
	if not plans:
		return []

	latest = {}
	for p in plans:
		key = (p.sales_person or "", p.territory or "")
		if key not in latest:
			latest[key] = p.name

	rows = frappe.get_all(
		"Target Proposal Detail",
		filters={"parent": ("in", list(latest.values()))},
		fields=[
			"parent",
			"sales_person",
			"territory",
			"item_group",
			"item_code",
			"approved_target_qty",
			"approved_target_amount",
			"growth_percent",
		],
		ignore_permissions=True,
	)
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
		item_codes=[filters.item] if filters.get("item") else None,
		include_monthly=True,
	)
	slabs, based_on, pay_on = scheme_settings(filters)
	buckets = period_buckets(filters.get("period"), filters.get("month"), filters.get("quarter"))
	seen = set()
	out = []
	for row in rows:
		if filters.get("sales_person") and row.sales_person != filters.sales_person:
			continue
		if filters.get("territory") and row.territory != filters.territory:
			continue
		if filters.get("item_group") and row.item_group != filters.item_group:
			continue
		if filters.get("item") and row.item_code != filters.item:
			continue
		grain = (row.sales_person or "", row.territory or "", row.item_code or "")
		if grain in seen:
			continue
		seen.add(grain)
		actual = actuals.get(grain) or actuals.get(("", "", row.item_code or "")) or {}
		month_target = {
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
					"item_code": row.item_code,
					"planning": row.parent,
					"growth_percent": nflt(row.get("growth_percent"), 2),
				}
			)
			out.append(metrics)
	return out


def group_dashboard_rows(rows, group_by="sales_person"):
	field = {
		"sales_person": "sales_person",
		"territory": "territory",
		"item_group": "item_group",
		"item": "item_code",
		"period": "period",
	}.get(group_by or "sales_person", "sales_person")
	grouped = {}
	for row in rows:
		key = row.get(field) or "(Not Set)"
		bucket = grouped.setdefault(
			key,
			{
				"dimension": key,
				"target_qty": 0.0,
				"actual_qty": 0.0,
				"target_amount": 0.0,
				"actual_amount": 0.0,
				"incentive_amount": 0.0,
				"incentive_qty": 0.0,
				"incentive_on_amount": 0.0,
				"incentive_on_qty": 0.0,
				"min_incentive_amount": 0.0,
				"max_incentive_amount": 0.0,
			},
		)
		bucket["target_qty"] += nflt(row.get("target_qty"))
		bucket["actual_qty"] += nflt(row.get("actual_qty"))
		bucket["target_amount"] += nflt(row.get("target_amount"))
		bucket["actual_amount"] += nflt(row.get("actual_amount"))
		bucket["incentive_amount"] += nflt(row.get("incentive_amount"))
		bucket["incentive_qty"] += nflt(row.get("incentive_qty"))
		bucket["incentive_on_amount"] += nflt(row.get("incentive_on_amount"))
		bucket["incentive_on_qty"] += nflt(row.get("incentive_on_qty"))
		if row.get("incentive_band") == "Min":
			bucket["min_incentive_amount"] += nflt(row.get("incentive_amount"))
		elif row.get("incentive_band") == "Max":
			bucket["max_incentive_amount"] += nflt(row.get("incentive_amount"))
	out = list(grouped.values())
	for bucket in out:
		bucket["qty_achievement_percent"] = (
			nflt(bucket["actual_qty"] / bucket["target_qty"] * 100.0, 2) if bucket["target_qty"] else None
		)
	out.sort(key=lambda r: r["incentive_amount"], reverse=True)
	return out


def dashboard_totals(rows):
	target_qty = sum(nflt(r.get("target_qty")) for r in rows)
	actual_qty = sum(nflt(r.get("actual_qty")) for r in rows)
	target_amount = sum(nflt(r.get("target_amount")) for r in rows)
	actual_amount = sum(nflt(r.get("actual_amount")) for r in rows)
	incentive_amount = sum(nflt(r.get("incentive_amount")) for r in rows)
	incentive_on_amount = sum(nflt(r.get("incentive_on_amount")) for r in rows)
	incentive_on_qty = sum(nflt(r.get("incentive_on_qty")) for r in rows)
	return {
		"target_qty": target_qty,
		"actual_qty": actual_qty,
		"target_amount": target_amount,
		"actual_amount": actual_amount,
		"incentive_amount": incentive_amount,
		"incentive_on_amount": incentive_on_amount,
		"incentive_on_qty": incentive_on_qty,
		"qty_achievement_percent": nflt(actual_qty / target_qty * 100.0, 2) if target_qty else 0,
		"min_incentive_amount": sum(nflt(r.get("incentive_amount")) for r in rows if r.get("incentive_band") == "Min"),
		"max_incentive_amount": sum(nflt(r.get("incentive_amount")) for r in rows if r.get("incentive_band") == "Max"),
		"rows_with_incentive": sum(1 for r in rows if nflt(r.get("incentive_amount")) > 0),
	}

