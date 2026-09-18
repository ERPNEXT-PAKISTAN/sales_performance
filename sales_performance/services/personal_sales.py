"""Personal mobile and manager read models. Every entry point resolves user scope."""
import calendar

import frappe
from frappe import _
from frappe.utils import flt, getdate, now_datetime

from sales_performance.services.access import assignments, is_admin, require_manager, scope
from sales_performance.services.achievement_engine import compute_metrics
from sales_performance.services.analysis_engine import payout_analysis
from sales_performance.services.distribution_engine import MONTHS
from sales_performance.services.incentive_engine import (
    allocate_item_incentives, calculation_level, collect_period_incentive_rows,
    dashboard_totals, scheme_settings,
)
from sales_performance.services.planning_engine import fiscal_year_dates


def personal_person(company, person=None):
    allowed = scope(company, person)
    if person:
        return person
    if allowed is not None:
        leaves = frappe.get_all("Sales Person", filters={"name": ["in", allowed], "is_group": 0, "enabled": 1}, pluck="name")
        if len(leaves) == 1:
            return leaves[0]
    frappe.throw(_("Select a Sales Person to open their personal view"))


@frappe.whitelist()
def get_context():
    if frappe.session.user == "Guest":
        frappe.throw(_("Please sign in"), frappe.PermissionError)
    links = assignments()
    companies = frappe.get_all("Company", order_by="name", pluck="name") if is_admin() else sorted({row.company for row in links})
    years = frappe.get_all("Fiscal Year", filters={"disabled": 0}, fields=["name", "year_start_date", "year_end_date"], order_by="year_start_date desc")
    return {"companies": companies, "fiscal_years": years, "admin": is_admin(),
            "mapped": bool(companies), "user": frappe.session.user,
            "manager": is_admin() or any(row.include_team for row in links)}


@frappe.whitelist()
def get_people(company):
    allowed = scope(company)
    return frappe.get_all("Sales Person", filters={"is_group": 0, **({"name": ["in", allowed]} if allowed is not None else {})}, pluck="name", order_by="name")


def month_dates(company, fiscal_year, month):
    start, end = map(getdate, fiscal_year_dates(fiscal_year, company))
    month = int(month)
    if not 1 <= month <= 12:
        frappe.throw(_("Invalid month"))
    year = start.year if month >= start.month else start.year + 1
    first = getdate(f"{year}-{month:02d}-01")
    last = getdate(f"{year}-{month:02d}-{calendar.monthrange(year, month)[1]}")
    if first > end or last < start:
        frappe.throw(_("Month is outside this fiscal year"))
    return max(first, start), min(last, end)


def pace(row, first, last, metric="amount"):
    today = getdate()
    days = (last - first).days + 1
    elapsed = max(0, min(days, (today - first).days + 1))
    remaining_days = max(0, (last - max(first, today)).days + 1)
    target, actual = flt(row.get("raw_target_" + metric, row.get("target_" + metric))), flt(row.get("raw_actual_" + metric, row.get("actual_" + metric)))
    remaining = max(target - actual, 0)
    if target <= 0:
        status = "No target"
    elif actual >= target:
        status = "Achieved"
    elif actual >= target * 0.9:
        status = "Near target"
    elif actual < target * elapsed / days:
        status = "Behind pace"
    else:
        status = "On pace"
    return {"status": status, "remaining": remaining, "daily_needed": remaining / remaining_days if remaining_days else None,
            "remaining_days": remaining_days, "expected_to_date": target * elapsed / days}


@frappe.whitelist()
def get_personal_data(company, fiscal_year, month, sales_person=None, customer_group="Market"):
    person = personal_person(company, sales_person)
    first, last = month_dates(company, fiscal_year, month)
    filters = {"company": company, "fiscal_year": fiscal_year, "sales_person": person,
               "customer_group": customer_group, "period": "Monthly", "approved_only": True}
    rows = collect_period_incentive_rows(filters)
    slabs, based_on, pay_on = scheme_settings(filters)
    level = calculation_level(filters)
    allocated = allocate_item_incentives(rows, slabs, based_on, pay_on, level)
    selected = [r for r in allocated if int(r.get("month_number") or 0) == int(month)]
    raw_selected = [r for r in rows if int(r.get("month_number") or 0) == int(month)]
    totals = dashboard_totals(raw_selected, slabs, based_on, pay_on, level)
    codes = sorted({r["item_code"] for r in selected if r.get("item_code")})
    labels = {r.name: r for r in frappe.get_all("Item", filters={"name": ["in", codes]}, fields=["name", "item_name", "stock_uom"])} if codes else {}
    for row in selected:
        item = labels.get(row.get("item_code")) or {}
        row.update(item_name=item.get("item_name") or row.get("item_code"), uom=item.get("stock_uom"),
                   pace=pace(row, first, last, "qty"), amount_pace=pace(row, first, last, "amount"))
        row["surplus"] = max(flt(row.get("actual_qty" if pay_on == "Qty" else "actual_amount")) - flt(row.get("target_qty" if pay_on == "Qty" else "target_amount")), 0)
        achievement = flt(row.get("qty_achievement_percent" if based_on == "Qty Achievement" else "amount_achievement_percent"))
        thresholds = sorted({flt(s.get(k)) for s in slabs for k in ("min_achievement_percent", "max_achievement_percent") if s.get(k) is not None and flt(s.get(k)) > achievement})
        row["next_threshold"] = thresholds[0] if thresholds and level == "Item" else None
    monthly = []
    for number, label in enumerate(MONTHS, 1):
        subset = [r for r in rows if int(r.get("month_number") or 0) == number]
        summary = dashboard_totals(subset, slabs, based_on, pay_on, level)
        monthly.append(dict(summary, month=number, label=label))
    payouts = payout_analysis(company, fiscal_year, person, period="Monthly", month=month, customer_group=customer_group)
    plans = plan_updates(rows, person, company)
    messages = frappe.get_all("Sales Performance Update", filters={"company": company, "sales_person": person},
        fields=["name", "kind", "subject", "message", "response", "status", "creation", "modified", "planning", "responded_by"], order_by="modified desc", limit=100)
    acknowledged = {m.planning for m in messages if m.kind == "Acknowledgement"}
    for plan in plans:
        plan["acknowledged"] = plan["name"] in acknowledged
    return {"sales_person": person, "company": company, "fiscal_year": fiscal_year,
        "month": int(month), "month_label": MONTHS[int(month)-1], "from_date": first, "to_date": last,
        "customer_group": customer_group, "currency": frappe.get_cached_value("Company", company, "default_currency"),
        "totals": totals, "pace": pace(totals, first, last), "items": selected, "monthly": monthly,
        "payouts": payouts, "plans": plans, "updates": messages, "pay_on": pay_on, "based_on": based_on,
        "calculation_level": level, "updated_at": now_datetime(), "approved_only": True,
        "can_acknowledge": any(a.company == company and a.sales_person == person and not a.include_team for a in assignments()),
        "sales": get_personal_sales(company, fiscal_year, month, person, customer_group)}


def plan_updates(rows, person, company):
    names = sorted({r["planning"] for r in rows if r.get("planning")})
    if not names:
        return []
    return frappe.get_all("Sales Target Planning", filters={"name": ["in", names], "company": company, "status": "Approved"},
        fields=["name", "planning_version", "approved_on", "erpnext_targets_synced_on", "previous_planning"], order_by="approved_on desc")


@frappe.whitelist()
def get_personal_sales(company, fiscal_year, month, sales_person=None, customer_group="Market", offset=0):
    person = personal_person(company, sales_person)
    first, last = month_dates(company, fiscal_year, month)
    offset = max(0, int(offset))
    from sales_performance.services.growth_engine import get_customer_group_subtree_names
    conditions = ""
    values = {"company": company, "person": person, "first": first, "last": last, "offset": offset}
    if customer_group:
        conditions = "and si.customer_group in %(groups)s"
        values["groups"] = tuple(get_customer_group_subtree_names(customer_group))
    # Show only the user's attributed portion; never expose whole invoice totals.
    records = frappe.db.sql(f"""select si.name, si.posting_date, si.customer_name, si.is_return,
        sum(sii.base_net_amount * ifnull(nullif(st.allocated_percentage,0),100)/100) as attributed_amount
        from `tabSales Invoice` si join `tabSales Invoice Item` sii on sii.parent=si.name
        join `tabSales Team` st on st.parent=si.name and st.parenttype='Sales Invoice'
        where si.docstatus=1 and si.company=%(company)s and st.sales_person=%(person)s
        and si.posting_date between %(first)s and %(last)s {conditions}
        group by si.name, si.posting_date, si.customer_name, si.is_return
        order by si.posting_date desc, si.name desc limit 31 offset %(offset)s""", values, as_dict=True)
    totals = frappe.db.sql(f"""select count(distinct si.name) as invoice_count,
        max(si.posting_date) as last_posting_date,
        sum(sii.base_net_amount * ifnull(nullif(st.allocated_percentage,0),100)/100) as attributed_amount
        from `tabSales Invoice` si join `tabSales Invoice Item` sii on sii.parent=si.name
        join `tabSales Team` st on st.parent=si.name and st.parenttype='Sales Invoice'
        where si.docstatus=1 and si.company=%(company)s and st.sales_person=%(person)s
        and si.posting_date between %(first)s and %(last)s {conditions}""", values, as_dict=True)[0]
    return {"rows": records[:30], "has_more": len(records)>30, "next_offset": offset+30, "totals": totals}


@frappe.whitelist()
def ask_question(company, sales_person, subject, message):
    personal_person(company, sales_person)
    if not subject or not message or len(subject)>140 or len(message)>4000:
        frappe.throw(_("Enter a subject (up to 140 characters) and message (up to 4000 characters)"))
    doc = frappe.get_doc({"doctype": "Sales Performance Update", "company": company, "sales_person": sales_person,
        "kind": "Question", "subject": subject, "message": message, "status": "Open"})
    doc.flags.personal_action = True
    doc.insert(ignore_permissions=True)
    return doc.name


@frappe.whitelist()
def acknowledge_plan(company, sales_person, planning):
    personal_person(company, sales_person)
    if not any(a.company == company and a.sales_person == sales_person and not a.include_team for a in assignments()):
        frappe.throw(_("Only the assigned sales person can acknowledge this target"), frappe.PermissionError)
    plan = frappe.get_doc("Sales Target Planning", planning)
    if plan.company != company or plan.status != "Approved" or not (plan.sales_person == sales_person or any(r.sales_person == sales_person for r in plan.proposal_details)):
        frappe.throw(_("This approved plan is not assigned to you"), frappe.PermissionError)
    existing = frappe.db.get_value("Sales Performance Update", {"company":company, "sales_person":sales_person, "planning":planning, "kind":"Acknowledgement"}, "name")
    if existing:
        return existing
    doc = frappe.get_doc({"doctype":"Sales Performance Update", "company":company, "sales_person":sales_person,
        "planning":planning, "kind":"Acknowledgement", "subject":"Target acknowledged", "message":"Approved target acknowledged by " + frappe.session.user, "status":"Acknowledged"})
    doc.flags.personal_action=True
    doc.insert(ignore_permissions=True)
    return doc.name


@frappe.whitelist()
def get_manager_data(company, fiscal_year, month, customer_group="Market"):
    allowed = require_manager(company)
    first, last = month_dates(company, fiscal_year, month)
    filters = {"company":company,"fiscal_year":fiscal_year,"period":"Monthly","customer_group":customer_group}
    rows = collect_period_incentive_rows(filters)
    slabs,based_on,pay_on = scheme_settings(filters)
    level = calculation_level(filters)
    selected = [r for r in rows if int(r.get("month_number") or 0)==int(month)]
    people = sorted({r.get("sales_person") for r in rows if r.get("sales_person")})
    heatmap=[]
    for person in people:
        cells=[]
        for number in range(1,13):
            subset=[r for r in rows if r.get("sales_person")==person and int(r.get("month_number") or 0)==number]
            summary=dashboard_totals(subset,slabs,based_on,pay_on,level)
            cells.append(summary)
        heatmap.append({"sales_person":person,"months":cells,"pace":pace(cells[int(month)-1],first,last)})
    queue = frappe.get_list("Sales Target Planning",filters={"company":company,"fiscal_year":fiscal_year,"status":["in",["Draft","Calculated","Under Review"]]},
        fields=["name","sales_person","status","planning_version","rows_requiring_review","rows_overridden","summary_warnings","previous_planning"],order_by="modified desc",limit_page_length=100)
    messages=frappe.get_list("Sales Performance Update",filters={"company":company,"kind":"Question","status":"Open"},fields=["name","sales_person","subject","message"],order_by="creation",limit_page_length=100)
    return {"totals":dashboard_totals(selected,slabs,based_on,pay_on,level),"heatmap":heatmap,"months":MONTHS,
        "payouts":payout_analysis(company,fiscal_year,period="Monthly",month=month,customer_group=customer_group),
        "queue":queue,"questions":messages,"provisional":any(r.get("plan_status")!="Approved" for r in selected),
        "pay_on":pay_on,"currency":frappe.get_cached_value("Company",company,"default_currency"),"updated_at":now_datetime()}


@frappe.whitelist()
def get_revision_changes(name):
    plan = frappe.get_doc("Sales Target Planning", name)
    require_manager(plan.company)
    plan.check_permission("read")
    if not plan.previous_planning:
        return {"rows": [], "total": 0}
    previous = frappe.get_doc("Sales Target Planning", plan.previous_planning)
    previous.check_permission("read")
    def key(row):
        return tuple(row.get(k) or "" for k in ("sales_person", "territory", "customer_group", "item_code"))
    before = {key(row): row for row in previous.proposal_details}
    after = {key(row): row for row in plan.proposal_details}
    changes = []
    for grain in sorted(before.keys() | after.keys()):
        old, new = before.get(grain) or {}, after.get(grain) or {}
        if any(flt(old.get(k)) != flt(new.get(k)) for k in ("approved_target_qty", "approved_target_rate", "approved_target_amount")):
            changes.append({"sales_person": grain[0], "territory": grain[1], "customer_group": grain[2], "item": grain[3],
                "old_qty": old.get("approved_target_qty", 0), "new_qty": new.get("approved_target_qty", 0),
                "old_rate": old.get("approved_target_rate", 0), "new_rate": new.get("approved_target_rate", 0),
                "reason": new.get("override_reason") or ""})
    return {"rows": changes, "total": len(changes), "previous": previous.name, "current": plan.name}
