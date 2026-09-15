import frappe
from frappe import _
from frappe.utils import flt

from sales_performance.services.incentive_engine import (
	collect_period_incentive_rows,
	dashboard_totals,
	group_dashboard_rows,
)


@frappe.whitelist()
def get_filter_options():
	return {
		"companies": frappe.get_all("Company", order_by="name", pluck="name"),
		"fiscal_years": frappe.get_all("Fiscal Year", order_by="year_start_date desc", pluck="name"),
		"sales_persons": frappe.get_all(
			"Sales Person", filters={"is_group": 0, "enabled": 1}, order_by="name", pluck="name"
		),
		"territories": frappe.get_all("Territory", filters={"is_group": 0}, order_by="name", pluck="name"),
		"item_groups": frappe.get_all("Item Group", filters={"is_group": 0}, order_by="name", pluck="name"),
	}


@frappe.whitelist()
def get_dashboard_data(
	company=None,
	fiscal_year=None,
	period="Monthly",
	month=None,
	quarter=None,
	group_by="sales_person",
	sales_person=None,
	territory=None,
	item_group=None,
	item=None,
):
	if not company or not fiscal_year:
		frappe.throw(_("Company and Fiscal Year are required"))

	rows = collect_period_incentive_rows(
		{
			"company": company,
			"fiscal_year": fiscal_year,
			"period": period or "Monthly",
			"month": month,
			"quarter": quarter,
			"sales_person": sales_person,
			"territory": territory,
			"item_group": item_group,
			"item": item,
		}
	)
	grouped = group_dashboard_rows(rows, group_by or "sales_person")
	totals = dashboard_totals(rows)
	posted = _payout_totals(company, fiscal_year)
	totals["posted_incentive"] = posted["accrued"]
	totals["paid_incentive"] = posted["paid"]
	totals["unpaid_incentive"] = posted["unpaid"]

	if (period or "Monthly") == "Monthly" and not month:
		month_chart = group_dashboard_rows(rows, "period")
	else:
		month_chart = group_dashboard_rows(
			collect_period_incentive_rows(
				{
					"company": company,
					"fiscal_year": fiscal_year,
					"period": "Monthly",
					"sales_person": sales_person,
					"territory": territory,
					"item_group": item_group,
					"item": item,
				}
			),
			"period",
		)
	return {
		"rows": rows,
		"grouped": grouped,
		"totals": totals,
		"month_chart": _months_january_first(month_chart),
		"group_by": group_by or "sales_person",
		"period": period or "Monthly",
	}


def _months_january_first(rows):
	from sales_performance.services.distribution_engine import MONTHS

	by_name = {row.get("dimension"): row for row in rows or []}
	ordered = []
	for name in MONTHS:
		row = by_name.get(name)
		if row:
			ordered.append(row)
		else:
			ordered.append({"dimension": name, "incentive_amount": 0.0})
	return ordered


def _payout_totals(company, fiscal_year):
	meta = frappe.get_meta("Sales Incentive Payout")
	fields = ["total_incentive_amount"]
	if meta.has_field("payment_status"):
		fields.append("payment_status")
	rows = frappe.get_all(
		"Sales Incentive Payout",
		filters={"company": company, "fiscal_year": fiscal_year, "docstatus": 1},
		fields=fields,
	)
	accrued = sum(flt(r.total_incentive_amount) for r in rows)
	paid = sum(
		flt(r.total_incentive_amount) for r in rows if r.get("payment_status") == "Paid"
	)
	return {"accrued": accrued, "paid": paid, "unpaid": max(accrued - paid, 0)}
