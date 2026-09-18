import frappe
from frappe import _
from frappe.utils import flt, getdate, add_months, get_first_day

from sales_performance.services.distribution_engine import MONTHS
from sales_performance.services.incentive_engine import (
    allocate_item_incentives, calculation_level, collect_period_incentive_rows, scheme_settings,
)


@frappe.whitelist()
def get_data(company=None, fiscal_year=None, sales_person=None, item_group=None,
             customer_group="Market", territory=None, item=None, incentive_status="All",
             pay_on=None, from_date=None, to_date=None, include_details=False, detail_month=None):
    if not company or not fiscal_year:
        frappe.throw(_("Company and Fiscal Year are required"))
    frappe.has_permission("Sales Target Planning", "read", throw=True)
    frappe.get_doc("Company", company).check_permission("read")
    from sales_performance.services.planning_engine import fiscal_year_dates

    if pay_on not in (None, "", "Scheme Default", "Qty", "Amount"):
        frappe.throw(_("Invalid incentive basis"))
    incentive_status = incentive_status or "All"
    if incentive_status not in ("All", "Achieved", "Not Achieved"):
        frappe.throw(_("Invalid incentive achievement filter"))
    start, end = map(getdate, fiscal_year_dates(fiscal_year, company))
    from_date, to_date = getdate(from_date or start), getdate(to_date or end)
    if from_date > to_date:
        frappe.throw(_("From Date must be on or before To Date"))
    if from_date < start or to_date > end:
        frappe.throw(_("Dates must be within the selected Fiscal Year"))
    month_numbers = []
    cursor = get_first_day(from_date)
    while cursor <= to_date:
        if cursor.month not in month_numbers:
            month_numbers.append(cursor.month)
        cursor = add_months(cursor, 1)
    filters = {"company": company, "fiscal_year": fiscal_year, "period": "Monthly",
               "sales_person": sales_person, "item_group": item_group,
               "customer_group": customer_group, "territory": territory, "item": item,
               "pay_on": pay_on if pay_on in ("Qty", "Amount") else None,
               "from_date": from_date, "to_date": to_date}
    rows = collect_period_incentive_rows(filters)
    slabs, based_on, pay_on = scheme_settings(filters)
    allocated = allocate_item_incentives(rows, slabs, based_on, pay_on, calculation_level(filters))
    allocated = [row for row in allocated if row.get("month_number") in month_numbers]
    result = filter_achievement(pivot_rows(allocated), incentive_status)
    if frappe.utils.cint(include_details):
        result["details"] = [row for row in allocated if not detail_month or int(row.get("month_number") or 0) == int(detail_month)]
    result["provisional"] = any(r.get("plan_status") != "Approved" for r in rows)
    result.update(months=MONTHS, month_numbers=month_numbers, pay_on=pay_on,
                  currency=frappe.get_cached_value("Company", company, "default_currency"))
    return result


def pivot_rows(rows):
    """Pivot already allocated monthly payouts without rescoring annual totals."""
    people = {}
    totals = [0.0] * 12
    for row in rows:
        month = int(row.get("month_number") or 0)
        if not 1 <= month <= 12:
            continue
        person = row.get("sales_person") or ""
        group = people.setdefault(person, {"sales_person": person, "months": [0.0] * 12, "items": {}})
        key = tuple(row.get(field) or "" for field in ("item_code", "item_group", "territory", "customer_group"))
        item = group["items"].setdefault(key, {
            **dict(zip(("item_code", "item_group", "territory", "customer_group"), key)),
            "months": [0.0] * 12,
        })
        amount = flt(row.get("incentive_amount"))
        item["months"][month - 1] += amount
        group["months"][month - 1] += amount
        totals[month - 1] += amount
    groups = []
    for person in sorted(people):
        group = people[person]
        group["items"] = [dict(item, total=sum(item["months"])) for _, item in sorted(group["items"].items())]
        group["total"] = sum(group["months"])
        groups.append(group)
    return {"groups": groups, "months_total": totals, "total": sum(totals)}


def filter_achievement(result, status):
    """Filter item totals after allocation, then reconcile visible totals."""
    if status == "All":
        return result
    groups = []
    totals = [0.0] * 12
    for group in result["groups"]:
        items = [item for item in group["items"]
                 if (item["total"] > 0) == (status == "Achieved")]
        if not items:
            continue
        months = [sum(item["months"][month] for item in items) for month in range(12)]
        groups.append(dict(group, items=items, months=months, total=sum(months)))
        totals = [left + right for left, right in zip(totals, months)]
    return {"groups": groups, "months_total": totals, "total": sum(totals)}
