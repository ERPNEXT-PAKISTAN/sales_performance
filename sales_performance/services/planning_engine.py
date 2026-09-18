"""Orchestrate historical sales → growth → pricing → distribution → proposal rows."""

import hashlib

from frappe.utils import cint, getdate

from sales_performance.services.numbers import nflt

from sales_performance.services.distribution_engine import (
	custom_percentage,
	equal_half_yearly,
	equal_monthly,
	equal_quarterly,
)
from sales_performance.services.growth_engine import (
	apply_growth,
	get_item_group_ancestors,
	growth_rule_covers_item_group,
	item_group_in_subtree,
	resolve_growth_percent,
)
from sales_performance.services.historical_sales import fetch_historical_sales
from sales_performance.services.precision import get_currency_precision, get_qty_precision, round_amount, round_percent
from sales_performance.services.pricing_engine import get_target_price, prefetch_last_selling

NO_HISTORY_REASON = "No previous-year sales history"
NO_PRICE_REASON = "No applicable price"
NEGATIVE_NET_REASON = "Net previous-year returns exceed sales; target set to zero"


def make_row_key(sales_person, territory, item_code, customer_group=None):
	raw = f"{sales_person or ''}|{territory or ''}|{item_code or ''}|{customer_group or ''}"
	return hashlib.sha1(raw.encode()).hexdigest()[:12]


def fiscal_year_dates(fiscal_year, company=None):
	from erpnext.accounts.utils import get_fiscal_year

	fy = get_fiscal_year(fiscal_year=fiscal_year, company=company, as_dict=True)
	return fy.year_start_date, fy.year_end_date


def previous_fiscal_year_name(fiscal_year, company=None):
	from frappe.utils import add_days
	from erpnext.accounts.utils import get_fiscal_year

	start, _end = fiscal_year_dates(fiscal_year, company)
	prev = get_fiscal_year(date=add_days(getdate(start), -1), company=company, as_dict=True)
	return prev.name, prev.year_start_date, prev.year_end_date


def calendar_previous_year_dates(fiscal_year, company=None):
	"""Same basis as /desk/sales-target: previous calendar year vs the planning FY end."""
	from datetime import date

	_start, fy_end = fiscal_year_dates(fiscal_year, company)
	previous_year = getdate(fy_end).year - 1
	return date(previous_year, 1, 1), date(previous_year, 12, 31), previous_year


def recalculate_proposal(doc, preserve_overrides=True):
	import frappe

	if doc.status in ("Approved", "Cancelled", "Superseded"):
		frappe.throw("Approved or cancelled plans cannot be recalculated. Create a revision instead.")

	doc.status = "Calculating"
	if not doc.growth_method:
		doc.growth_method = "Uniform Percent"
	if not doc.pricing_method:
		doc.pricing_method = "Previous Year Average Selling Price"
	if not doc.distribution_method:
		doc.distribution_method = "Equal Monthly"
	_validate_header(doc)

	prev_start, prev_end, prev_year = calendar_previous_year_dates(doc.fiscal_year, doc.company)
	try:
		prev_name, _fy_start, _fy_end = previous_fiscal_year_name(doc.fiscal_year, doc.company)
		doc.previous_fiscal_year = prev_name
	except Exception:
		doc.previous_fiscal_year = str(prev_year)
	doc.from_date = prev_start
	doc.to_date = prev_end

	history = fetch_historical_sales(
		company=doc.company,
		from_date=prev_start,
		to_date=prev_end,
		sales_person=doc.sales_person,
		territory=doc.territory,
		item_group=getattr(doc, "item_group", None),
		customer_group=getattr(doc, "customer_group", None),
		include_monthly=True,
	)
	current_actuals = _fetch_current_year_monthly_actuals(doc)
	prev_targets = {}

	rules = []
	if doc.growth_method != "Uniform Percent":
		rules = [
			{
				"item_group": r.item_group,
				"growth_percent": r.growth_percent,
				"apply_to_children": r.apply_to_children,
				"priority": r.priority,
			}
			for r in (doc.growth_rules or [])
			if r.item_group
		]
		history = {
			key: grain
			for key, grain in history.items()
			if _item_group_allowed_for_planning(grain.get("item_group"), doc, rules)
		}

	existing_overrides = {}
	if preserve_overrides:
		for row in doc.proposal_details or []:
			if row.row_key and (row.override_reason or nflt(row.approved_target_qty) or nflt(row.approved_target_rate)):
				existing_overrides[row.row_key] = row

	cache = {"item_price": {}, "last_selling": {}}
	if doc.pricing_method == "Last Selling Price":
		cache["last_selling"] = prefetch_last_selling(
			[v["item_code"] for v in history.values()],
			doc.company,
			as_on=prev_end,
		)

	proposal = []
	monthly = []
	custom_percents = [nflt(p.distribution_percent) for p in (doc.custom_percents or [])]

	for grain in history.values():
		row = _build_proposal_row(doc, grain, rules, prev_targets, cache, existing_overrides)
		proposal.append(row)
		monthly.extend(_distribute_row(doc, row, grain, custom_percents, current_actuals))

	for key, old in existing_overrides.items():
		if key not in {r["row_key"] for r in proposal} and old.item_code:
			if not _item_group_allowed_for_planning(old.item_group, doc, rules):
				continue
			grain = {
				"sales_person": old.sales_person,
				"territory": old.territory,
				"item_code": old.item_code,
				"item_name": old.item_name,
				"item_group": old.item_group,
				"customer_group": getattr(old, "customer_group", None) or "",
				"uom": old.uom,
				"qty": 0,
				"amount": 0,
				"month_qty": {},
				"month_amount": {},
			}
			row = _build_proposal_row(doc, grain, rules, prev_targets, cache, existing_overrides)
			proposal.append(row)
			monthly.extend(_distribute_row(doc, row, grain, custom_percents, current_actuals))

	doc.set("proposal_details", [])
	for row in proposal:
		doc.append("proposal_details", row)

	doc.set("monthly_details", [])
	for row in monthly:
		doc.append("monthly_details", row)

	refresh_summary(doc)
	doc.status = "Calculated"
	return doc


def rebuild_plan(name, preserve_overrides=True):
	"""Rebuild a draft plan from its invoice-history grain and save it."""
	import frappe

	doc = frappe.get_doc("Sales Target Planning", name)
	recalculate_proposal(doc, preserve_overrides=preserve_overrides)
	doc.save(ignore_version=True)
	return doc.name


def _build_proposal_row(doc, grain, rules, prev_targets, cache, existing_overrides):
	item_group = grain.get("item_group")
	if doc.growth_method == "Uniform Percent":
		growth = nflt(doc.uniform_growth_percent)
		growth_source = "Uniform"
	else:
		ancestors = get_item_group_ancestors(item_group)
		growth, growth_source = resolve_growth_percent(item_group, rules, ancestors)

	uom = grain.get("uom")
	qty_precision = get_qty_precision(uom)
	prev_qty = nflt(grain.get("qty"))
	prev_amount = nflt(grain.get("amount"))
	# Annual target uses the complete previous calendar year at this planning grain.
	# Stable-sales distributions split that annual target evenly by default.
	calc_qty = apply_growth(prev_qty, growth, precision=qty_precision, whole_number=qty_precision == 0)
	# Returns remain visible as negative historical actuals, but a target cannot
	# be negative. Keep the row for review and set its planned quantity to zero.
	negative_net_qty = calc_qty < 0
	if negative_net_qty:
		calc_qty = 0
	avg_month_qty = nflt(prev_qty / 12.0, qty_precision)
	monthly_target_qty = nflt(calc_qty / 12.0, qty_precision)

	row_key = make_row_key(
		grain.get("sales_person"), grain.get("territory"), grain.get("item_code"), grain.get("customer_group")
	)
	override = existing_overrides.get(row_key)

	pricing_method = (override.pricing_method if override and override.pricing_method else None) or doc.pricing_method
	price_list = (override.price_list if override and override.price_list else None) or doc.price_list
	manual_rate = override.target_selling_rate if override and pricing_method == "Manual Price" else None

	price = get_target_price(
		item_code=grain.get("item_code"),
		company=doc.company,
		pricing_method=pricing_method,
		price_list=price_list,
		sales_person=grain.get("sales_person") or doc.sales_person,
		transaction_date=doc.to_date,
		uom=uom,
		previous_year_qty=prev_qty,
		previous_year_amount=prev_amount,
		manual_rate=manual_rate,
		cache=cache,
	)
	rate = nflt(price.get("rate"))
	calc_amount = round_amount(calc_qty * rate, get_currency_precision())

	requires_review = 0
	review_reasons = []
	if negative_net_qty:
		requires_review = 1
		review_reasons.append(NEGATIVE_NET_REASON)
	if not prev_qty:
		requires_review = 1
		review_reasons.append(NO_HISTORY_REASON)
	if price.get("error") or not rate:
		requires_review = 1
		review_reasons.append(NO_PRICE_REASON)

	prev_tgt = prev_targets.get(
		(grain.get("sales_person") or "", grain.get("territory") or "", grain.get("item_code") or "")
	) or prev_targets.get((grain.get("sales_person") or "", "", grain.get("item_code") or ""))

	row = {
		"row_key": row_key,
		"sales_person": grain.get("sales_person") or "",
		"territory": grain.get("territory") or "",
		"item_code": grain.get("item_code"),
		"item_name": grain.get("item_name"),
		"item_group": item_group,
		"customer_group": grain.get("customer_group") or "",
		"uom": uom,
		"previous_year_target_qty": nflt(prev_tgt.target_qty) if prev_tgt else 0,
		"previous_year_actual_qty": prev_qty,
		"previous_year_target_amount": nflt(prev_tgt.target_amount) if prev_tgt else 0,
		"previous_year_actual_amount": prev_amount,
		"growth_percent": growth,
		"calculated_target_qty": calc_qty,
		"pricing_method": pricing_method,
		"price_list": price_list,
		"source_rate": rate,
		"target_selling_rate": rate,
		"calculated_target_amount": calc_amount,
		"price_source": price.get("price_source"),
		"price_reference": price.get("price_reference"),
		"requires_review": requires_review,
		"review_reason": "; ".join(review_reasons),
		"remarks": (
			f"Avg PY month {avg_month_qty}; monthly target {monthly_target_qty}; "
			f"quarter ×3; year {calc_qty}. Growth source: {growth_source}"
			if growth_source
			else f"Avg PY month {avg_month_qty}; monthly target {monthly_target_qty}"
		),
	}

	if override:
		approved_qty = nflt(override.approved_target_qty) if override.approved_target_qty not in (None, "") else calc_qty
		approved_rate = (
			nflt(override.approved_target_rate) if override.approved_target_rate not in (None, "") else rate
		)
		row.update(
			{
				"approved_target_qty": approved_qty,
				"approved_target_rate": approved_rate,
				"approved_target_amount": round_amount(approved_qty * approved_rate, get_currency_precision()),
				"override_reason": override.override_reason,
				"override_by": override.override_by,
				"override_on": override.override_on,
			}
		)
		_apply_override_percent(row)
	else:
		row.update(
			{
				"approved_target_qty": calc_qty,
				"approved_target_rate": rate,
				"approved_target_amount": calc_amount,
			}
		)
	return row


def apply_row_override(row):
	qty = nflt(row.approved_target_qty)
	rate = nflt(row.approved_target_rate)
	row.approved_target_amount = round_amount(qty * rate, get_currency_precision())
	_apply_override_percent(row)
	return row


def _apply_override_percent(row):
	calc_qty = nflt(row.get("calculated_target_qty") if isinstance(row, dict) else row.calculated_target_qty)
	approved_qty = nflt(row.get("approved_target_qty") if isinstance(row, dict) else row.approved_target_qty)
	if calc_qty:
		pct = round_percent((approved_qty - calc_qty) / calc_qty * 100.0) or 0
	else:
		pct = 0
	if isinstance(row, dict):
		row["override_percent"] = pct
	else:
		row.override_percent = pct


def _fetch_current_year_monthly_actuals(doc):
	"""Planning-year monthly actuals for Actual Qty / Amount on monthly rows."""
	from frappe.utils import getdate, today

	try:
		fy_start, fy_end = fiscal_year_dates(doc.fiscal_year, doc.company)
	except Exception:
		return {}
	as_on = getdate(today())
	start = getdate(fy_start)
	end = getdate(fy_end)
	if as_on < start:
		return {}
	return fetch_historical_sales(
		company=doc.company,
		from_date=start,
		to_date=min(as_on, end),
		sales_person=doc.sales_person,
		territory=doc.territory,
		item_group=getattr(doc, "item_group", None),
		customer_group=getattr(doc, "customer_group", None),
		include_monthly=True,
	)


def complete_monthly_row(row, month, grain=None, actual_grain=None):
	"""Fill target rate, previous-year, actuals, variance, and achievement on a month row."""
	qp = get_qty_precision()
	ap = get_currency_precision()
	month_no = int(month.get("month_number") or 0)
	target_qty = nflt(month.get("target_qty"), qp)
	target_amount = nflt(month.get("target_amount"), ap)
	rate = nflt(month.get("target_rate"), ap)
	if not rate and target_qty:
		rate = nflt(target_amount / target_qty, ap)
	if not rate:
		rate = nflt(row.get("approved_target_rate") or row.get("target_selling_rate"), ap)
	if not target_amount and target_qty and rate:
		target_amount = nflt(target_qty * rate, ap)

	prev_qty = nflt(month.get("previous_year_qty"), qp)
	prev_amount = nflt(month.get("previous_year_amount"), ap)
	if grain:
		prev_qty = nflt((grain.get("month_qty") or {}).get(month_no), qp) or prev_qty
		prev_amount = nflt((grain.get("month_amount") or {}).get(month_no), ap) or prev_amount

	actual_qty = nflt(month.get("actual_qty"), qp)
	actual_amount = nflt(month.get("actual_amount"), ap)
	if actual_grain:
		actual_qty = nflt((actual_grain.get("month_qty") or {}).get(month_no), qp)
		actual_amount = nflt((actual_grain.get("month_amount") or {}).get(month_no), ap)

	qty_variance = nflt(actual_qty - target_qty, qp)
	amount_variance = nflt(actual_amount - target_amount, ap)
	return {
		"row_key": row.get("row_key"),
		"sales_person": row.get("sales_person"),
		"territory": row.get("territory"),
		"item_code": row.get("item_code"),
		"item_group": row.get("item_group"),
		"customer_group": row.get("customer_group"),
		"month": month.get("month"),
		"month_number": month_no,
		"target_qty": target_qty,
		"target_amount": target_amount,
		"target_rate": rate,
		"distribution_percent": round_percent(month.get("distribution_percent")) or 0,
		"previous_year_qty": prev_qty,
		"previous_year_amount": prev_amount,
		"actual_qty": actual_qty,
		"actual_amount": actual_amount,
		"qty_variance": qty_variance,
		"amount_variance": amount_variance,
		"qty_achievement_percent": round_percent(actual_qty / target_qty * 100.0) if target_qty else None,
		"amount_achievement_percent": round_percent(actual_amount / target_amount * 100.0)
		if target_amount
		else None,
	}


def _distribute_row(doc, row, grain, custom_percents, current_actuals=None):
	method = doc.distribution_method or "Equal Monthly"
	precision = get_qty_precision(row.get("uom"))
	amount_precision = get_currency_precision()
	annual_qty = nflt(row.get("approved_target_qty"))
	annual_amount = nflt(row.get("approved_target_amount"))
	rate = nflt(row.get("approved_target_rate"))
	growth = nflt(row.get("growth_percent"))
	prev_month_qty = grain.get("month_qty") or {}
	prev_month_amount = grain.get("month_amount") or {}

	if method == "Equal Monthly":
		months = equal_monthly(annual_qty, annual_amount, precision, amount_precision)
	elif method == "Equal Quarterly":
		months = equal_quarterly(annual_qty, annual_amount, True, precision, amount_precision)
	elif method == "Equal Half-Yearly":
		months = equal_half_yearly(annual_qty, annual_amount, True, precision, amount_precision)
	elif method == "Custom Percentage Distribution":
		months = custom_percentage(annual_qty, custom_percents, annual_amount, precision, amount_precision)
	elif method == "Manual Monthly":
		months = equal_monthly(annual_qty, annual_amount, precision, amount_precision)
	else:
		# Legacy method values stay readable, but never generate a new seasonal
		# target distribution. Approved documents are not modified here.
		months = equal_monthly(annual_qty, annual_amount, precision, amount_precision)

	actual_grain = None
	if current_actuals:
		key = (
			row.get("sales_person") or "",
			row.get("territory") or "",
			row.get("item_code"),
			row.get("customer_group") or "",
		)
		actual_grain = current_actuals.get(key)

	return [complete_monthly_row(row, month, grain, actual_grain) for month in months]


def refresh_summary(doc):
	rows = doc.proposal_details or []
	groups = {r.item_group for r in rows if r.item_group}
	persons = {r.sales_person for r in rows if r.sales_person}
	doc.total_previous_qty = sum(nflt(r.previous_year_actual_qty) for r in rows)
	doc.total_previous_amount = sum(nflt(r.previous_year_actual_amount) for r in rows)
	doc.total_calculated_qty = sum(nflt(r.calculated_target_qty) for r in rows)
	doc.total_calculated_amount = sum(nflt(r.calculated_target_amount) for r in rows)
	doc.total_approved_qty = sum(nflt(r.approved_target_qty) for r in rows)
	doc.total_approved_amount = sum(nflt(r.approved_target_amount) for r in rows)
	doc.rows_count = len(rows)
	doc.item_groups_count = len(groups)
	doc.sales_persons_count = len(persons)
	doc.rows_requiring_review = sum(1 for r in rows if cint(r.requires_review))
	doc.rows_overridden = sum(
		1 for r in rows if r.override_reason or nflt(r.override_percent)
	)
	doc.rows_without_price = sum(1 for r in rows if not nflt(r.target_selling_rate) or r.price_source == "")
	warnings = []
	no_hist = sum(1 for r in rows if NO_HISTORY_REASON in (r.review_reason or ""))
	no_price = sum(1 for r in rows if NO_PRICE_REASON in (r.review_reason or ""))
	if no_hist:
		warnings.append(f"{no_hist} items have no previous-year sales.")
	if no_price:
		warnings.append(f"{no_price} items have no applicable price.")
	if doc.rows_overridden:
		warnings.append(f"{doc.rows_overridden} items have manager overrides.")
	doc.summary_warnings = "\n".join(warnings)


def _item_group_allowed_for_planning(item_group, doc, rules):
	scope = getattr(doc, "item_group", None)
	ancestors = get_item_group_ancestors(item_group) if (scope or rules) else []
	if scope and not item_group_in_subtree(item_group, scope, ancestors):
		return False
	if doc.growth_method == "Item Group Rules":
		return growth_rule_covers_item_group(item_group, rules, ancestors)
	return True


def _validate_header(doc):
	import frappe

	if not doc.company:
		frappe.throw("Company is required")
	if not doc.fiscal_year:
		frappe.throw("Fiscal Year is required")
	if doc.pricing_method == "Specific Price List" and not doc.price_list:
		frappe.throw("Price List is required for Specific Price List pricing")
	if doc.growth_method == "Item Group Rules":
		if not doc.growth_rules:
			frappe.throw("Add at least one Item Group Growth Rule to set targets for selected groups")
		seen = set()
		scope = getattr(doc, "item_group", None)
		for rule in doc.growth_rules or []:
			if not rule.item_group:
				frappe.throw("Each growth rule must have an Item Group")
			if rule.item_group in seen:
				frappe.throw(f"Duplicate growth rule for Item Group {rule.item_group}")
			seen.add(rule.item_group)
			if scope:
				ancestors = get_item_group_ancestors(rule.item_group)
				if not item_group_in_subtree(rule.item_group, scope, ancestors):
					frappe.throw(
						f"Growth rule Item Group {rule.item_group} must be {scope} or a child of it"
					)
	if doc.distribution_method == "Custom Percentage Distribution":
		total = sum(nflt(p.distribution_percent) for p in (doc.custom_percents or []))
		if abs(total - 100) > 0.01:
			frappe.throw("Custom distribution percentages must equal 100%")
		if len(doc.custom_percents or []) != 12:
			frappe.throw("Custom distribution requires 12 monthly percentages")
