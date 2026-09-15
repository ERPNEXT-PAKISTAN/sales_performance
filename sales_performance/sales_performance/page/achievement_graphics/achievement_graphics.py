import frappe

from sales_performance.sales_performance.page.target_achievement.target_achievement import get_achievement_board


@frappe.whitelist()
def get_graphics_data(
	company=None,
	fiscal_year=None,
	period="Annual",
	month=None,
	quarter=None,
	judge="Qty",
	sales_person=None,
	territory=None,
	item_group=None,
	customer_group=None,
	item=None,
):
	return get_achievement_board(
		company=company,
		fiscal_year=fiscal_year,
		period=period,
		month=month,
		quarter=quarter,
		judge=judge,
		sales_person=sales_person,
		territory=territory,
		item_group=item_group,
		customer_group=customer_group,
		item=item,
	)
