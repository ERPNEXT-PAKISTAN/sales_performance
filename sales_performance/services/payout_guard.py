"""Prevent overlapping entitlement posting and preserve the approved inputs."""
import frappe
from frappe import _
from frappe.utils import flt
from sales_performance.services.distribution_engine import MONTHS


def months_for(label):
    if label in MONTHS:
        return {MONTHS.index(label) + 1}
    if label in ("Q1", "Q2", "Q3", "Q4"):
        quarter = int(label[1])
        return set(range(quarter * 3 - 2, quarter * 3 + 1))
    return set(range(1, 13))


def overlaps(left, right):
    if left.get("sales_person") != right.get("sales_person"):
        return False
    if not months_for(left.get("period")).intersection(months_for(right.get("period"))):
        return False
    # Blank dimensions represent the whole group, not a separate entitlement.
    return all(not left.get(k) or not right.get(k) or left.get(k) == right.get(k)
               for k in ("customer_group", "territory", "item_code"))


def validate_new_payout(doc):
    if doc.pay_on == "Qty" and flt(doc.get("qty_conversion_rate")) <= 0:
        frappe.throw(_("Set Currency per Incentive Unit before submitting a Qty payout"))
    # Serialize new submissions for this company so two workers cannot both pass.
    frappe.db.sql("select name from `tabCompany` where name=%s for update", (doc.company,))
    existing = frappe.db.sql("""select i.sales_person, i.customer_group, i.territory, i.item_code, i.period, p.name
        from `tabSales Incentive Payout Item` i join `tabSales Incentive Payout` p on p.name=i.parent
        where p.company=%s and p.fiscal_year=%s and p.docstatus=1 and p.name!=%s for update""",
        (doc.company, doc.fiscal_year, doc.name), as_dict=True)
    seen = []
    for item in doc.items:
        if any(overlaps(item, other) for other in seen):
            frappe.throw(_("This payout contains overlapping entitlement rows"))
        seen.append(item)
        for other in existing:
            if overlaps(item, other):
                frappe.throw(_("This entitlement overlaps submitted payout {0}. Cancel or reconcile that payout before posting again.").format(other.name))
    from sales_performance.services.incentive_engine import scheme_settings, calculation_level
    filters = {"company": doc.company, "fiscal_year": doc.fiscal_year, "pay_on": doc.pay_on}
    slabs, based_on, pay_on = scheme_settings(filters)
    original = frappe.parse_json(doc.get("calculation_snapshot") or "{}")
    if not original.get("source_rows"):
        frappe.throw(_("Load incentives again before submitting so the calculation can be recorded"))
    if original.get("slabs") != slabs or original.get("pay_on") != pay_on or original.get("based_on") != based_on:
        frappe.throw(_("The incentive scheme changed. Load incentives again before submitting"))
    plans = sorted({row.get("planning") for row in original["source_rows"] if row.get("planning")})
    for name in plans:
        if frappe.db.get_value("Sales Target Planning", name, "status") != "Approved":
            frappe.throw(_("Only approved target plans can be paid"))
    doc.calculation_snapshot = frappe.as_json({"recorded_at": frappe.utils.now_datetime(),
        "recorded_by": frappe.session.user, "source_rows": original["source_rows"], "calculated_at": original.get("calculated_at"), "slabs": slabs, "based_on": based_on, "pay_on": pay_on,
        "calculation_level": calculation_level(filters), "qty_conversion_rate": doc.get("qty_conversion_rate"),
        "plans": [{"name": name, "version": frappe.db.get_value("Sales Target Planning", name, "planning_version")} for name in plans],
        "items": [row.as_dict() for row in doc.items]})
