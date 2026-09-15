"""Monthly / quarterly / half-yearly distribution of annual targets.

Uses calendar months January–December. When applying to ERPNext, a
Monthly Distribution document is created/reused (standard ERPNext mechanism).
"""

from calendar import month_name

from sales_performance.services.numbers import nflt

MONTHS = [month_name[i] for i in range(1, 13)]


def _split_equal(total, parts, precision):
	if parts <= 0:
		return []
	base = nflt(total / parts, precision)
	values = [base] * parts
	values[-1] = nflt(total - sum(values[:-1]), precision)
	return values


def reconcile_to_total(values, total, precision):
	if not values:
		return values
	out = [nflt(v, precision) for v in values]
	out[-1] = nflt(total - sum(out[:-1]), precision)
	return out


def equal_monthly(annual_qty, annual_amount=0, precision=3, amount_precision=2):
	qty = _split_equal(nflt(annual_qty), 12, precision)
	amount = _split_equal(nflt(annual_amount), 12, amount_precision)
	percents = _split_equal(100.0, 12, 6)
	percents = reconcile_to_total(percents, 100.0, 6)
	return _as_months(qty, amount, percents, precision, amount_precision)


def equal_quarterly(annual_qty, annual_amount=0, to_months=True, precision=3, amount_precision=2):
	q_qty = _split_equal(nflt(annual_qty), 4, precision)
	q_amt = _split_equal(nflt(annual_amount), 4, amount_precision)
	qty, amount = [], []
	if to_months:
		for q in range(4):
			qty.extend(_split_equal(q_qty[q], 3, precision))
			amount.extend(_split_equal(q_amt[q], 3, amount_precision))
	else:
		# expand quarters as 3 identical month slots that still sum to the quarter
		for q in range(4):
			qty.extend(_split_equal(q_qty[q], 3, precision))
			amount.extend(_split_equal(q_amt[q], 3, amount_precision))
	percents = [nflt(100.0 * (q / nflt(annual_qty or 1)) / 3.0, 6) for q in q_qty for _ in range(3)]
	if nflt(annual_qty):
		percents = []
		for q in q_qty:
			share = 100.0 * nflt(q) / nflt(annual_qty)
			percents.extend(_split_equal(share, 3, 6))
		percents = reconcile_to_total(percents, 100.0, 6)
	else:
		percents = _split_equal(100.0, 12, 6)
		percents = reconcile_to_total(percents, 100.0, 6)
	return _as_months(qty, amount, percents, precision, amount_precision)


def equal_half_yearly(annual_qty, annual_amount=0, to_months=True, precision=3, amount_precision=2):
	h_qty = _split_equal(nflt(annual_qty), 2, precision)
	h_amt = _split_equal(nflt(annual_amount), 2, amount_precision)
	qty, amount, percents = [], [], []
	if nflt(annual_qty):
		for h in h_qty:
			share = 100.0 * nflt(h) / nflt(annual_qty)
			qty.extend(_split_equal(h, 6, precision))
			percents.extend(_split_equal(share, 6, 6))
		for h in h_amt:
			amount.extend(_split_equal(h, 6, amount_precision))
		percents = reconcile_to_total(percents, 100.0, 6)
	else:
		qty = _split_equal(0, 12, precision)
		amount = _split_equal(nflt(annual_amount), 12, amount_precision)
		percents = _split_equal(100.0, 12, 6)
		percents = reconcile_to_total(percents, 100.0, 6)
	return _as_months(qty, amount, percents, precision, amount_precision)


def custom_percentage(annual_qty, percents, annual_amount=0, precision=3, amount_precision=2):
	total_p = nflt(sum(nflt(p) for p in percents), 6)
	if abs(total_p - 100.0) > 0.01:
		raise ValueError("Custom distribution percentages must total 100%")
	if len(percents) != 12:
		raise ValueError("Custom distribution requires 12 monthly percentages")
	qty = [nflt(nflt(annual_qty) * nflt(p) / 100.0, precision) for p in percents]
	qty = reconcile_to_total(qty, annual_qty, precision)
	amount = [nflt(nflt(annual_amount) * nflt(p) / 100.0, amount_precision) for p in percents]
	amount = reconcile_to_total(amount, annual_amount, amount_precision)
	return _as_months(qty, amount, percents, precision, amount_precision)


def same_month_previous_year(
	annual_qty,
	prev_month_qty,
	growth_percent,
	annual_amount=0,
	prev_month_amount=None,
	target_rate=0,
	precision=3,
	amount_precision=2,
):
	"""Previous Year Month Qty × (1 + Growth %). Reconcile to annual target qty."""
	grown = [
		nflt(nflt(prev_month_qty.get(i, 0)) * (1 + nflt(growth_percent) / 100.0), precision)
		for i in range(1, 13)
	]
	grown = reconcile_to_total(grown, annual_qty, precision)
	if prev_month_amount and not target_rate:
		amount = [
			nflt(nflt(prev_month_amount.get(i, 0)) * (1 + nflt(growth_percent) / 100.0), amount_precision)
			for i in range(1, 13)
		]
		amount = reconcile_to_total(amount, annual_amount, amount_precision)
	else:
		amount = [nflt(q * nflt(target_rate), amount_precision) for q in grown]
		amount = reconcile_to_total(amount, annual_amount, amount_precision)
	if nflt(annual_qty):
		percents = [nflt(100.0 * q / nflt(annual_qty), 6) for q in grown]
		percents = reconcile_to_total(percents, 100.0, 6)
	else:
		percents = [0] * 12
	return _as_months(grown, amount, percents, precision, amount_precision, prev_month_qty, prev_month_amount)


def manual_monthly(month_qty, month_amount, annual_qty, annual_amount, precision=3, amount_precision=2):
	qty = [nflt(month_qty.get(i, 0), precision) for i in range(1, 13)]
	amount = [nflt(month_amount.get(i, 0), amount_precision) for i in range(1, 13)]
	if abs(nflt(sum(qty), precision) - nflt(annual_qty, precision)) > (10 ** -precision if precision else 0.5):
		raise ValueError("SUM(monthly target qty) must equal annual target qty")
	if annual_amount and abs(nflt(sum(amount), amount_precision) - nflt(annual_amount, amount_precision)) > (
		10 ** -amount_precision
	):
		raise ValueError("SUM(monthly target amount) must equal annual target amount")
	if nflt(annual_qty):
		percents = [nflt(100.0 * q / nflt(annual_qty), 6) for q in qty]
		percents = reconcile_to_total(percents, 100.0, 6)
	else:
		percents = [0] * 12
	return _as_months(qty, amount, percents, precision, amount_precision)


def _as_months(qty, amount, percents, precision, amount_precision, prev_qty=None, prev_amount=None):
	rows = []
	for i in range(12):
		month_no = i + 1
		q = nflt(qty[i], precision)
		a = nflt(amount[i], amount_precision)
		rate = nflt(a / q, amount_precision) if q else 0
		rows.append(
			{
				"month": MONTHS[i],
				"month_number": month_no,
				"target_qty": q,
				"target_amount": a,
				"target_rate": rate,
				"distribution_percent": nflt(percents[i], 6),
				"previous_year_qty": nflt((prev_qty or {}).get(month_no, 0)),
				"previous_year_amount": nflt((prev_amount or {}).get(month_no, 0)),
			}
		)
	return rows


def percents_from_rows(rows):
	return [nflt(r.get("distribution_percent")) for r in rows]


def ensure_monthly_distribution(name, percents, fiscal_year=None):
	"""Create or update an ERPNext Monthly Distribution (idempotent)."""
	import frappe

	if frappe.db.exists("Monthly Distribution", name):
		doc = frappe.get_doc("Monthly Distribution", name)
		doc.percentages = []
	else:
		doc = frappe.new_doc("Monthly Distribution")
		doc.distribution_id = name
	if fiscal_year:
		doc.fiscal_year = fiscal_year
	for i, month in enumerate(MONTHS):
		doc.append(
			"percentages",
			{"month": month, "percentage_allocation": nflt(percents[i] if i < len(percents) else 0, 6)},
		)
	doc.save(ignore_permissions=True)
	return doc.name
