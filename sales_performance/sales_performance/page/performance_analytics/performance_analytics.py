import frappe
from frappe import _

from sales_performance.services.analysis_engine import (
	fetch_monthly_sales,
	fetch_sales_by_dimension,
	merge_period_rows,
	payout_analysis,
	summarize_rows,
	target_totals_by_dimension,
)
from sales_performance.services.incentive_engine import (
	collect_period_incentive_rows,
	dashboard_totals,
	group_dashboard_rows,
	scheme_settings,
)
from sales_performance.services.planning_engine import calendar_previous_year_dates, fiscal_year_dates


@frappe.whitelist()
def get_analytics(
	company=None,
	fiscal_year=None,
	sales_person=None,
	territory=None,
	item_group=None,
	customer_group=None,
	customer=None,
	item=None,
	period="Annual",
	month=None,
	quarter=None,
):
	if not company or not fiscal_year:
		frappe.throw(_("Company and Fiscal Year are required"))

	start, end = fiscal_year_dates(fiscal_year, company)
	py_start, py_end, _year = calendar_previous_year_dates(fiscal_year, company)
	filters = {
		"sales_person": sales_person,
		"territory": territory,
		"item_group": item_group,
		"customer_group": customer_group,
		"customer": customer,
		"item": item,
	}

	sales = {}
	for dimension in ("sales_person", "territory", "item_group", "customer_group", "customer", "item"):
		cy = fetch_sales_by_dimension(company, start, end, dimension, **filters)
		py = fetch_sales_by_dimension(company, py_start, py_end, dimension, **filters)
		targets = target_totals_by_dimension(company, fiscal_year, dimension)
		sales[dimension] = merge_period_rows(cy, py, targets)

	cy_months = {int(r.month_number): r for r in fetch_monthly_sales(company, start, end, **filters)}
	py_months = {int(r.month_number): r for r in fetch_monthly_sales(company, py_start, py_end, **filters)}
	from sales_performance.services.distribution_engine import MONTHS

	trend = []
	for i, label in enumerate(MONTHS, start=1):
		cy = cy_months.get(i) or {}
		py = py_months.get(i) or {}
		trend.append(
			{
				"dimension": label,
				"current_amount": float(cy.get("amount") or 0),
				"previous_amount": float(py.get("amount") or 0),
				"current_qty": float(cy.get("qty") or 0),
				"previous_qty": float(py.get("qty") or 0),
			}
		)

	incentive_filters = {
		"company": company,
		"fiscal_year": fiscal_year,
		"period": period or "Annual",
		"month": month,
		"quarter": quarter,
		"sales_person": sales_person,
		"territory": territory,
		"item_group": item_group,
		"customer_group": customer_group,
		"item": item,
	}
	incentive_rows = collect_period_incentive_rows(incentive_filters)
	slabs, based_on, pay_on = scheme_settings(incentive_filters)
	payout = payout_analysis(company, fiscal_year, sales_person)
	overview = summarize_rows(sales["sales_person"])
	overview.update(dashboard_totals(incentive_rows, slabs, based_on, pay_on))
	overview.update(payout["totals"])
	return {
		"overview": overview,
		"sales": sales,
		"trend": trend,
		"incentive": {
			"by_sales_person": group_dashboard_rows(incentive_rows, "sales_person", slabs, based_on, pay_on),
			"by_territory": group_dashboard_rows(incentive_rows, "territory", slabs, based_on, pay_on),
			"by_item_group": group_dashboard_rows(incentive_rows, "item_group", slabs, based_on, pay_on),
			"by_customer_group": group_dashboard_rows(incentive_rows, "customer_group", slabs, based_on, pay_on),
			"by_item": group_dashboard_rows(incentive_rows, "item", slabs, based_on, pay_on),
			"by_period": group_dashboard_rows(incentive_rows, "period", slabs, based_on, pay_on),
			"totals": dashboard_totals(incentive_rows, slabs, based_on, pay_on),
		},
		"payout": payout,
	}
