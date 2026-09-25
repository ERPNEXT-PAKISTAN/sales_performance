"""Shared target editing rules for forms, imports, transfers and amendments."""

from calendar import month_name
from math import isfinite

import frappe
from sales_performance.services.numbers import nflt as flt, ncint as cint

from sales_performance.services.planning_engine import make_row_key, _distribute_row, refresh_summary
from sales_performance.services.precision import get_qty_precision, get_currency_precision

DIMENSIONS = ("sales_person", "territory", "item_code", "customer_group")
# An in-process capability cannot be forged by passing JSON document flags.
APPROVAL_TOKEN = object()
HEADERS = ("title", "sales_person", "territory", "item_group", "customer_group", "target_source",
           "entry_basis", "value_basis", "growth_method", "uniform_growth_percent", "pricing_method",
           "price_list", "distribution_method", "notes", "incentive_calculation_level")
TABLES = {
    "proposal_details": DIMENSIONS + ("row_key", "item_group", "uom", "pricing_method", "price_list",
        "target_selling_rate", "approved_target_qty", "approved_target_rate", "approved_target_amount",
        "override_reason", "remarks"),
    "monthly_details": DIMENSIONS + ("row_key", "month_number", "target_qty", "target_rate", "target_amount", "distribution_percent"),
    "growth_rules": ("item_group", "growth_percent", "apply_to_children", "priority"),
    "custom_percents": ("month", "month_number", "distribution_percent"),
}
DISPLAY_FIELDS = ("previous_year_target_qty", "previous_year_actual_qty", "previous_year_target_amount",
	"previous_year_actual_amount", "growth_percent", "calculated_target_qty", "source_rate",
	"calculated_target_amount", "price_source", "price_reference", "requires_review", "review_reason",
	"override_percent", "override_by", "override_on")


def snapshot(doc):
	return {**{f: doc.get(f) for f in HEADERS},
			**{f: [{k: r.get(k) for k in keys} for r in doc.get(f) or []] for f, keys in TABLES.items()},
			"proposal_details": [{**{k: r.get(k) for k in TABLES["proposal_details"]},
				**{k: r.get(k) for k in DISPLAY_FIELDS}} for r in doc.get("proposal_details") or []]}


def apply_snapshot(doc, data):
    """Never accept status, approval fields, actuals or other system fields from a client."""
    for field in HEADERS:
        if field in data:
            doc.set(field, data[field])
    old = {r.row_key: r.as_dict() for r in doc.proposal_details or [] if r.row_key}
    for field, keys in TABLES.items():
        if field not in data:
            continue
        rows = []
        for supplied in data[field]:
            row = {k: supplied.get(k) for k in keys}
            if field == "proposal_details":
                base = old.get(row.get("row_key"), {})
                base = {k: v for k, v in base.items() if k not in
                        ("name", "parent", "parenttype", "parentfield", "doctype", "idx", "creation", "modified", "owner", "modified_by")}
                base.update(row)
                row = base
            rows.append(row)
        doc.set(field, rows)


def number(value, label):
    try:
        result = float(value or 0)
    except (ValueError, TypeError):
        frappe.throw(f"{label} must be a number")
    if not isfinite(result) or result < 0:
        frappe.throw(f"{label} must be a finite, non-negative number")
    return result


def normalize(doc, force_distribution=False, pricing_start_month=1):
    """Annual entry generates months; monthly entry makes the months authoritative."""
    monthly_entry = doc.get("entry_basis") == "Monthly"
    amount_entry = doc.get("value_basis") == "Quantity and Amount"
    if doc.get("entry_basis") not in (None, "", "Annual", "Monthly") or doc.get("value_basis") not in (None, "", "Quantity and Rate", "Quantity and Amount"):
        frappe.throw("Invalid target entry or value basis")
    remap, proposals = {}, {}
    fallback_prices = None
    fallback_rates = {}
    for row in doc.proposal_details or []:
        if not row.item_code:
            frappe.throw("Every target row requires an Item")
        item = frappe.db.get_value("Item", row.item_code, ["item_name", "item_group", "stock_uom"], as_dict=True)
        if not item:
            frappe.throw(f"Unknown Item: {row.item_code}")
        row.item_name, row.item_group, row.uom = item.item_name, item.item_group, item.stock_uom
        row.sales_person = row.sales_person or doc.sales_person
        row.territory = row.territory or doc.territory
        row.customer_group = row.customer_group or doc.customer_group
        if not row.sales_person and not row.territory:
            frappe.throw(f"Select a Sales Person or Territory for {row.item_code}")
        key = make_row_key(*(row.get(f) for f in DIMENSIONS))
        if key in proposals:
            frappe.throw(f"Duplicate target: {row.sales_person or row.territory} / {row.item_code} / {row.customer_group or ''}")
        if row.row_key:
            remap[row.row_key] = key
        row.row_key = key
        proposals[key] = row
        qty = number(row.approved_target_qty, "Annual quantity")
        qty = flt(qty, get_qty_precision(row.uom))
        row.approved_target_qty = qty
        if amount_entry:
            row.approved_target_amount = flt(number(row.approved_target_amount, "Annual amount"), get_currency_precision())
            row.approved_target_rate = row.approved_target_amount / qty if qty else 0
        else:
            row.approved_target_rate = number(row.approved_target_rate, "Annual rate")
            if qty and not row.approved_target_rate:
                if fallback_prices is None:
                    from sales_performance.services.pricing_engine import prefetch_last_selling
                    fallback_prices = prefetch_last_selling(
                        list({r.item_code for r in doc.proposal_details if r.item_code and not r.approved_target_rate}),
                        doc.company, as_on=doc.get("to_date"))
                price = fallback_prices.get(row.item_code, {})
                if flt(price.get("rate")) > 0:
                    row.approved_target_rate = number(price["rate"], "Last selling rate")
                    row.price_source = price.get("price_source")
                    row.price_reference = price.get("price_reference")
                    fallback_rates[key] = row.approved_target_rate
            row.approved_target_amount = flt(qty * row.approved_target_rate, get_currency_precision())
    existing = {}
    for month in doc.monthly_details or []:
        key = remap.get(month.row_key, month.row_key) or make_row_key(*(month.get(f) for f in DIMENSIONS))
        if key not in proposals:
            continue  # Deleted proposals remove their months.
        n = number(month.month_number, "Month")
        if n != int(n) or not 1 <= n <= 12:
            frappe.throw("Month must be a whole number from 1 to 12")
        if (key, int(n)) in existing:
            frappe.throw(f"Duplicate month {int(n)} for {proposals[key].item_code}")
        month.row_key = key
        existing[key, int(n)] = month
    out = []
    for key, row in proposals.items():
        months = [existing.get((key, n)) for n in range(1, 13)]
        manual = doc.distribution_method == "Manual Monthly" and any(months)
        if force_distribution or (not monthly_entry and not manual):
            percents = list(doc.custom_percents or [])
            if doc.distribution_method == "Custom Percentage Distribution":
                if len(percents) != 12:
                    frappe.throw("Custom distribution requires all 12 months")
                if any(p.get("month_number") for p in percents):
                    if sorted(cint(p.month_number) for p in percents) != list(range(1, 13)):
                        frappe.throw("Custom distribution month numbers must be unique from 1 to 12")
                    percents.sort(key=lambda p: cint(p.month_number))
                for p in percents:
                    number(p.distribution_percent, "Distribution percentage")
            generated = _distribute_row(doc, row.as_dict(), {}, [flt(p.distribution_percent) for p in percents])
            months = [frappe._dict(m) for m in generated]
        else:
            months = [m or frappe._dict(month_number=n) for n, m in enumerate(months, 1)]
        for n, month in enumerate(months, 1):
            qty = flt(number(month.get("target_qty"), "Monthly quantity"), get_qty_precision(row.uom))
            amount = number(month.get("target_amount"), "Monthly amount")
            rate = number(month.get("target_rate"), "Monthly rate")
            if key in fallback_rates and n >= int(pricing_start_month or 1) and not rate and not amount:
                rate = fallback_rates[key]
                amount = flt(qty * rate, get_currency_precision())
            if monthly_entry and not amount_entry:
                amount = flt(qty * rate, get_currency_precision())
            else:
                amount = flt(amount, get_currency_precision())
                rate = amount / qty if qty else 0
            month.update({"row_key": key, "month_number": n, "month": month_name[n],
                          "target_qty": qty, "target_amount": amount, "target_rate": rate,
                          **{f: row.get(f) for f in DIMENSIONS}, "item_group": row.item_group})
        if monthly_entry or (manual and key in fallback_rates):
            row.approved_target_qty = sum(m.target_qty for m in months)
            row.approved_target_amount = sum(m.target_amount for m in months)
            row.approved_target_rate = row.approved_target_amount / row.approved_target_qty if row.approved_target_qty else 0
        elif manual and not force_distribution:
            if abs(sum(m.target_qty for m in months) - row.approved_target_qty) > 0.00001 or abs(sum(m.target_amount for m in months) - row.approved_target_amount) > 0.01:
                frappe.throw(f"Monthly totals for {row.item_code} differ from annual targets. Use Monthly entry or Distribute Targets.")
        total = row.approved_target_qty or row.approved_target_amount
        from sales_performance.services.planning_engine import _apply_override_percent
        _apply_override_percent(row)
        for month in months:
            numerator = month.target_qty if row.approved_target_qty else month.target_amount
            month.distribution_percent = 100 * numerator / total if total else 100 / 12
            # Actuals are refreshed independently; never transfer another person's actuals.
            month.actual_qty = month.actual_amount = 0
            month.qty_variance = -month.target_qty
            month.amount_variance = -month.target_amount
            month.qty_achievement_percent = month.amount_achievement_percent = 0
            values = dict(month) if isinstance(month, dict) else month.as_dict()
            out.append({k: v for k, v in values.items() if k not in
                        ("name", "doctype", "parent", "parenttype", "parentfield", "idx", "creation", "modified", "owner", "modified_by")})
    doc.set("monthly_details", out)
    refresh_summary(doc)


def refresh_actuals(doc):
    if not doc.monthly_details:
        return
    from sales_performance.services.planning_engine import _fetch_current_year_monthly_actuals
    from sales_performance.services.achievement_engine import compute_metrics
    actuals = _fetch_current_year_monthly_actuals(doc)
    history = {}
    if doc.get("from_date") and doc.get("to_date"):
        from sales_performance.services.historical_sales import fetch_historical_sales
        history = fetch_historical_sales(company=doc.company, from_date=doc.from_date, to_date=doc.to_date,
            item_codes=list({r.item_code for r in doc.proposal_details}), include_monthly=True)
        for row in doc.proposal_details:
            grain = history.get(tuple(row.get(f) or "" for f in DIMENSIONS), {})
            row.previous_year_actual_qty = flt(grain.get("qty"))
            row.previous_year_actual_amount = flt(grain.get("amount"))
    for month in doc.monthly_details or []:
        grain = actuals.get(tuple(month.get(f) or "" for f in DIMENSIONS), {})
        n = cint(month.month_number)
        month.actual_qty = flt((grain.get("month_qty") or {}).get(n))
        month.actual_amount = flt((grain.get("month_amount") or {}).get(n))
        if doc.get("from_date") and doc.get("to_date"):
            previous = history.get(tuple(month.get(f) or "" for f in DIMENSIONS), {})
            month.previous_year_qty = flt((previous.get("month_qty") or {}).get(n))
            month.previous_year_amount = flt((previous.get("month_amount") or {}).get(n))
        metrics = compute_metrics(month.target_qty, month.actual_qty, month.target_amount, month.actual_amount)
        month.qty_variance = metrics["variance_qty"]
        month.amount_variance = metrics["variance_amount"]
        month.qty_achievement_percent = metrics["qty_achievement_percent"]
        month.amount_achievement_percent = metrics["amount_achievement_percent"]


def transfer(doc, source, destination, start_month, percent=100, row_keys=None):
    start_month, percent = number(start_month, "Effective month"), number(percent, "Transfer percentage")
    if start_month != int(start_month) or not 1 <= start_month <= 12 or not 0 < percent <= 100:
        frappe.throw("Choose an effective month from 1–12 and a percentage greater than 0 and at most 100")
    if not source or not destination or source == destination:
        frappe.throw("Choose two different Sales Persons")
    if not frappe.db.get_value("Sales Person", destination, "enabled"):
        frappe.throw("The receiving Sales Person must be enabled")
    source_rows = [r for r in doc.proposal_details if (r.sales_person or doc.sales_person) == source]
    if not source_rows:
        frappe.throw("The selected source Sales Person has no target rows in the current editor. "
                     "They may already have been reassigned or removed in this amendment. "
                     "Choose a person currently listed in Proposal Details.")
    if row_keys and (not isinstance(row_keys, list) or any(not isinstance(k, str) for k in row_keys)):
        frappe.throw("Invalid selected target rows. Close Transfer Targets and select the rows again.")
    # Keep the selected row objects: normalization regenerates keys after identity edits.
    selected = [r for r in source_rows if not row_keys or r.row_key in row_keys]
    if row_keys and {r.row_key for r in selected} != set(row_keys):
        frappe.throw("Selected rows must all belong to the From Sales Person. "
                     "Select that person's rows again, or choose All Matching Rows.")
    normalize(doc)
    selected_keys = {r.row_key for r in selected}
    if not any(m.row_key in selected_keys and m.month_number >= start_month
               and (m.target_qty or m.target_amount) for m in doc.monthly_details):
        frappe.throw("The selected rows have no targets from the effective month through December. "
                     "They may already have been transferred.")
    proposals = {r.row_key: r for r in doc.proposal_details}
    monthly = {(m.row_key, m.month_number): m for m in doc.monthly_details}
    moved_qty = moved_amount = 0
    for row in selected:
        dest_key = make_row_key(destination, row.territory, row.item_code, row.customer_group)
        if dest_key not in proposals:
            new = doc.append("proposal_details", {**{f: row.get(f) for f in TABLES["proposal_details"]},
                                                  "sales_person": destination, "row_key": dest_key,
                                                  "override_reason": "Transferred targets"})
            proposals[dest_key] = new
        for n in range(int(start_month), 13):
            old = monthly[row.row_key, n]
            dest = monthly.get((dest_key, n))
            if not dest:
                dest = doc.append("monthly_details", {"row_key": dest_key, "month_number": n,
                            "sales_person": destination, "item_code": row.item_code,
                            "territory": row.territory, "customer_group": row.customer_group})
                monthly[dest_key, n] = dest
            qty = flt(old.target_qty * percent / 100, get_qty_precision(row.uom))
            amount = flt(old.target_amount * percent / 100, get_currency_precision())
            old.target_qty -= qty
            old.target_amount -= amount
            dest.target_qty = flt(dest.target_qty) + qty
            dest.target_amount = flt(dest.target_amount) + amount
            moved_qty += qty
            moved_amount += amount
    doc.entry_basis, doc.value_basis, doc.distribution_method = "Monthly", "Quantity and Amount", "Manual Monthly"
    normalize(doc)
    return {"quantity": moved_qty, "amount": moved_amount, "rows": len(selected)}
