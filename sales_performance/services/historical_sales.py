"""Aggregate submitted Sales Invoice history. Returns reduce net qty/amount.

One row per sales person × item (previous-year Sales Team). Qty/amount are
split by allocated_percentage so shared invoices are not double-counted.
Invoices with no Sales Team keep a blank sales person.
"""

from frappe.utils import getdate

# Same exclusions as analytics_studio sales-target report
EXCLUDED_ITEM_GROUPS = (
	"Mix Items",
	"Services",
	"Tape",
	"PVC",
	"Thread",
	"Therad",
	"Elastocraft_Unpack",
	"General Section",
	"KG GAUZE",
)


def item_group_subtree_sql(field="sii.item_group", param="item_group"):
	"""SQL predicate: field is the selected item group or a child of it."""
	return f"""{field} in (
		select child.name from `tabItem Group` child
		inner join `tabItem Group` parent
			on child.lft >= parent.lft and child.rgt <= parent.rgt
		where parent.name = %({param})s
	)"""


def customer_group_subtree_sql(field="si.customer_group", param="customer_group"):
	"""SQL predicate: field is the selected customer group or a child of it."""
	return f"""{field} in (
		select child.name from `tabCustomer Group` child
		inner join `tabCustomer Group` parent
			on child.lft >= parent.lft and child.rgt <= parent.rgt
		where parent.name = %({param})s
	)"""


def fetch_historical_sales(
	company,
	from_date,
	to_date,
	sales_person=None,
	territory=None,
	item_group=None,
	customer_group=None,
	item_codes=None,
	include_monthly=False,
	allowed_sales_persons=None,
):
	"""Return dict keyed by sales person, territory, item and customer group.

	The planning grain must retain every dimension exposed by the app. Collapsing
	territory or customer group here makes filtered reports compare a partial
	actual with an unfiltered target.
	"""
	import frappe

	conditions = [
		"si.docstatus = 1",
		"si.company = %(company)s",
		"si.posting_date between %(from_date)s and %(to_date)s",
		"sii.item_group not in %(excluded_groups)s",
	]
	values = {
		"company": company,
		"from_date": getdate(from_date),
		"to_date": getdate(to_date),
		"excluded_groups": EXCLUDED_ITEM_GROUPS,
	}

	if allowed_sales_persons is not None:
		conditions.append("st.sales_person in %(allowed_sales_persons)s")
		values["allowed_sales_persons"] = tuple(allowed_sales_persons or ("",))

	if sales_person:
		conditions.append("st.sales_person = %(sales_person)s")
		values["sales_person"] = sales_person
		sales_join = """inner join `tabSales Team` st
			on st.parent = si.name and st.parenttype = 'Sales Invoice'"""
	else:
		sales_join = """left join `tabSales Team` st
			on st.parent = si.name and st.parenttype = 'Sales Invoice'"""

	if territory:
		conditions.append(
			"""si.territory in (
				select child.name from `tabTerritory` child
				inner join `tabTerritory` parent
					on child.lft >= parent.lft and child.rgt <= parent.rgt
				where parent.name = %(territory)s
			)"""
		)
		values["territory"] = territory
	if item_group:
		conditions.append(item_group_subtree_sql())
		values["item_group"] = item_group
	if customer_group:
		conditions.append(customer_group_subtree_sql())
		values["customer_group"] = customer_group
	# An explicit empty target scope must return no actuals. Treating it as an
	# unfiltered query would show invoice items outside Sales Target Planning.
	if item_codes is not None:
		if not item_codes:
			return {}
		conditions.append("sii.item_code in %(item_codes)s")
		values["item_codes"] = tuple(item_codes)

	where = " and ".join(conditions)
	month_select = "month(si.posting_date) as month_number," if include_monthly else "0 as month_number,"
	month_group = ", month(si.posting_date)" if include_monthly else ""
	share = "ifnull(nullif(st.allocated_percentage, 0), 100) / 100"

	sql = f"""
		select
			ifnull(st.sales_person, '') as sales_person,
			ifnull(si.territory, '') as territory,
			sii.item_code,
			max(sii.item_name) as item_name,
			max(sii.item_group) as item_group,
			ifnull(si.customer_group, '') as customer_group,
			max(sii.stock_uom) as uom,
			{month_select}
			sum(sii.stock_qty * {share}) as qty,
			sum(sii.base_net_amount * {share}) as amount
		from `tabSales Invoice Item` sii
		inner join `tabSales Invoice` si on si.name = sii.parent
		{sales_join}
		where {where}
		group by ifnull(st.sales_person, ''), ifnull(si.territory, ''),
			sii.item_code, ifnull(si.customer_group, ''){month_group}
		having sum(sii.stock_qty * {share}) != 0
	"""

	rows = frappe.db.sql(sql, values, as_dict=True)
	return rollup_monthly(rows)


def rollup_monthly(rows):
	"""Combine monthly SQL rows into grain totals plus month maps."""
	out = {}
	for row in rows:
		key = (
			row.get("sales_person") or "",
			row.get("territory") or "",
			row.get("item_code"),
			row.get("customer_group") or "",
		)
		bucket = out.setdefault(
			key,
			{
				"sales_person": row.get("sales_person") or "",
				"territory": row.get("territory") or "",
				"item_code": row.get("item_code"),
				"item_name": row.get("item_name"),
				"item_group": row.get("item_group"),
				"customer_group": row.get("customer_group") or "",
				"uom": row.get("uom"),
				"qty": 0.0,
				"amount": 0.0,
				"month_qty": {},
				"month_amount": {},
			},
		)
		month = int(row.get("month_number") or 0)
		qty = float(row.get("qty") or 0)
		amount = float(row.get("amount") or 0)
		bucket["qty"] += qty
		bucket["amount"] += amount
		if month:
			bucket["month_qty"][month] = bucket["month_qty"].get(month, 0) + qty
			bucket["month_amount"][month] = bucket["month_amount"].get(month, 0) + amount
		if row.get("item_name"):
			bucket["item_name"] = row.get("item_name")
		if row.get("item_group"):
			bucket["item_group"] = row.get("item_group")
		if row.get("customer_group"):
			bucket["customer_group"] = row.get("customer_group")
		if row.get("uom"):
			bucket["uom"] = row.get("uom")
	return out


def fetch_previous_targets(fiscal_year, sales_person=None, territory=None):
	"""Official ERPNext Target Detail values for the previous year (reference only)."""
	import frappe

	filters = {"fiscal_year": fiscal_year}
	fields = ["parent", "parenttype", "item_group", "target_qty", "target_amount"]
	if frappe.db.has_column("Target Detail", "item"):
		fields.append("item")
	rows = frappe.get_all("Target Detail", filters=filters, fields=fields)
	out = {}
	for row in rows:
		if sales_person and row.parenttype == "Sales Person" and row.parent != sales_person:
			continue
		if territory and row.parenttype == "Territory" and row.parent != territory:
			continue
		item = row.get("item") or ""
		key = (
			row.parent if row.parenttype == "Sales Person" else "",
			row.parent if row.parenttype == "Territory" else "",
			item,
		)
		out[key] = row
	return out
