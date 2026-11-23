"""Selected dimensions shared by plan calculation and manual target editing."""

TABLES = {
	"sales_person": "selected_sales_persons",
	"territory": "selected_territories",
	"customer_group": "selected_customer_groups",
}


def dimension_allowed(doc, field, value):
	"""An empty selection includes every value in this dimension."""
	rows = doc.get(TABLES[field]) or []
	selected = {row.get(field) for row in rows if row.get(field)}
	return not selected or value in selected


def validate_selections(doc):
	import frappe
	from frappe import _

	for field, table in TABLES.items():
		seen = set()
		for row in doc.get(table) or []:
			value = row.get(field)
			if not value:
				frappe.throw(_("Every row in {0} needs a value").format(table.replace("_", " ").title()))
			if value in seen:
				frappe.throw(_("Duplicate {0}: {1}").format(field.replace("_", " ").title(), value))
			seen.add(value)
