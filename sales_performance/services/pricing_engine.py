"""Reusable target pricing service. Does not duplicate Item Price tables."""

from frappe.utils import getdate

from sales_performance.services.numbers import nflt

from sales_performance.services.precision import get_currency_precision, round_amount

PRICING_METHODS = (
	"Specific Price List",
	"Last Selling Price",
	"Previous Year Average Selling Price",
	"Manual Price",
)


def get_target_price(
	item_code,
	company,
	pricing_method,
	price_list=None,
	sales_person=None,
	customer=None,
	transaction_date=None,
	uom=None,
	previous_year_qty=None,
	previous_year_amount=None,
	manual_rate=None,
	cache=None,
):
	"""Return dict: rate, price_source, price_reference, price_list."""
	method = pricing_method or "Previous Year Average Selling Price"
	if method == "Manual Price":
		return {
			"rate": round_amount(manual_rate or 0, get_currency_precision()),
			"price_source": "Manual",
			"price_reference": "user-entered",
			"price_list": price_list,
		}
	if method == "Previous Year Average Selling Price":
		return average_selling_price(previous_year_qty, previous_year_amount)
	if method == "Last Selling Price":
		return last_selling_price(
			item_code,
			company,
			sales_person=sales_person,
			customer=customer,
			as_on=transaction_date,
			cache=cache,
		)
	if method == "Specific Price List":
		return price_list_rate(
			item_code,
			price_list,
			company=company,
			uom=uom,
			customer=customer,
			transaction_date=transaction_date,
			cache=cache,
		)
	return {
		"rate": 0,
		"price_source": "",
		"price_reference": "",
		"price_list": price_list,
		"error": f"Unknown pricing method: {method}",
	}


def average_selling_price(qty, amount):
	qty = nflt(qty)
	if not qty:
		return {
			"rate": 0,
			"price_source": "Previous Year Average",
			"price_reference": "",
			"error": "No previous-year quantity for average rate",
		}
	return {
		"rate": round_amount(nflt(amount) / qty, get_currency_precision()),
		"price_source": "Previous Year Average",
		"price_reference": "historical calculation",
	}


def last_selling_price(item_code, company, sales_person=None, customer=None, as_on=None, cache=None):
	if cache is not None and item_code in cache.get("last_selling", {}):
		return cache["last_selling"][item_code]

	import frappe

	conditions = [
		"si.docstatus = 1",
		"si.company = %(company)s",
		"sii.item_code = %(item_code)s",
		"sii.stock_qty != 0",
		"ifnull(si.is_return, 0) = 0",
	]
	values = {"company": company, "item_code": item_code}
	if as_on:
		conditions.append("si.posting_date <= %(as_on)s")
		values["as_on"] = getdate(as_on)
	if customer:
		conditions.append("si.customer = %(customer)s")
		values["customer"] = customer
	if sales_person:
		conditions.append(
			"""exists (
				select 1 from `tabSales Team` st
				where st.parent = si.name and st.parenttype = 'Sales Invoice'
				and st.sales_person = %(sales_person)s
			)"""
		)
		values["sales_person"] = sales_person

	where = " and ".join(conditions)
	row = frappe.db.sql(
		f"""
		select si.name, si.posting_date,
			(sii.base_net_amount / sii.stock_qty) as rate
		from `tabSales Invoice Item` sii
		inner join `tabSales Invoice` si on si.name = sii.parent
		where {where}
		order by si.posting_date desc, si.creation desc, sii.idx desc
		limit 1
		""",
		values,
		as_dict=True,
	)
	if not row:
		result = {
			"rate": 0,
			"price_source": "Last Selling Invoice",
			"price_reference": "",
			"error": "No submitted selling invoice found",
		}
	else:
		result = {
			"rate": round_amount(row[0].rate, get_currency_precision()),
			"price_source": "Last Selling Invoice",
			"price_reference": row[0].name,
		}
	if cache is not None:
		cache.setdefault("last_selling", {})[item_code] = result
	return result


def price_list_rate(
	item_code,
	price_list,
	company=None,
	uom=None,
	customer=None,
	transaction_date=None,
	cache=None,
):
	if not price_list:
		return {
			"rate": 0,
			"price_source": "Item Price",
			"price_reference": "",
			"price_list": price_list,
			"error": "Price List is required",
		}

	cache_key = (item_code, price_list, uom or "", customer or "")
	if cache is not None and cache_key in cache.get("item_price", {}):
		return cache["item_price"][cache_key]

	import frappe

	conditions = [
		"ip.item_code = %(item_code)s",
		"ip.price_list = %(price_list)s",
		"ifnull(ip.selling, 0) = 1",
	]
	values = {"item_code": item_code, "price_list": price_list}
	if transaction_date:
		td = getdate(transaction_date)
		conditions.append("(ip.valid_from is null or ip.valid_from <= %(td)s)")
		conditions.append("(ip.valid_upto is null or ip.valid_upto >= %(td)s)")
		values["td"] = td
	if uom:
		conditions.append("(ifnull(ip.uom, '') = '' or ip.uom = %(uom)s)")
		values["uom"] = uom
	if customer:
		conditions.append("(ifnull(ip.customer, '') = '' or ip.customer = %(customer)s)")
		values["customer"] = customer

	where = " and ".join(conditions)
	row = frappe.db.sql(
		f"""
		select ip.name, ip.price_list_rate, ip.uom, ip.currency
		from `tabItem Price` ip
		where {where}
		order by
			if(ifnull(ip.customer, '') = '', 0, 1) desc,
			ifnull(ip.valid_from, '0001-01-01') desc,
			if(ifnull(ip.uom, '') = '', 0, 1) desc
		limit 1
		""",
		values,
		as_dict=True,
	)
	if not row:
		result = {
			"rate": 0,
			"price_source": "Item Price",
			"price_reference": "",
			"price_list": price_list,
			"error": "No applicable Item Price",
		}
	else:
		rate = nflt(row[0].price_list_rate)
		ip_uom = row[0].uom
		stock_uom = frappe.db.get_value("Item", item_code, "stock_uom")
		if ip_uom and stock_uom and ip_uom != stock_uom:
			from erpnext.stock.doctype.item.item import get_uom_conv_factor

			factor = nflt(get_uom_conv_factor(ip_uom, stock_uom))
			if factor:
				# price is per ip_uom; convert to per stock UOM
				rate = rate / factor
		if company:
			company_currency = frappe.get_cached_value("Company", company, "default_currency")
			if row[0].currency and company_currency and row[0].currency != company_currency:
				from erpnext.setup.utils import get_exchange_rate

				ex = nflt(
					get_exchange_rate(
						row[0].currency,
						company_currency,
						transaction_date or getdate(),
					)
				)
				if ex:
					rate = rate * ex
		result = {
			"rate": round_amount(rate, get_currency_precision()),
			"price_source": "Item Price",
			"price_reference": row[0].name,
			"price_list": price_list,
		}

	if cache is not None:
		cache.setdefault("item_price", {})[cache_key] = result
	return result


def prefetch_last_selling(item_codes, company, as_on=None):
	"""One query for latest submitted selling rate per item (stock UOM)."""
	import frappe

	if not item_codes:
		return {}
	values = {"company": company, "items": tuple(item_codes)}
	date_filter = ""
	if as_on:
		date_filter = "and si.posting_date <= %(as_on)s"
		values["as_on"] = getdate(as_on)
	rows = frappe.db.sql(
		f"""
		select x.item_code, x.name, x.rate
		from (
			select
				sii.item_code,
				si.name,
				(sii.base_net_amount / sii.stock_qty) as rate,
				row_number() over (
					partition by sii.item_code
					order by si.posting_date desc, si.creation desc, sii.idx desc
				) as rn
			from `tabSales Invoice Item` sii
			inner join `tabSales Invoice` si on si.name = sii.parent
			where si.docstatus = 1
				and si.company = %(company)s
				and sii.item_code in %(items)s
				and sii.stock_qty != 0
				and ifnull(si.is_return, 0) = 0
				{date_filter}
		) x
		where x.rn = 1
		""",
		values,
		as_dict=True,
	)
	out = {}
	for row in rows:
		out[row.item_code] = {
			"rate": round_amount(row.rate, get_currency_precision()),
			"price_source": "Last Selling Invoice",
			"price_reference": row.name,
		}
	return out
