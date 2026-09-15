import frappe
from frappe import _


def execute(filters=None):
	filters = frappe._dict(filters or {})
	columns = [
		{"fieldname": "name", "label": _("Planning"), "fieldtype": "Link", "options": "Sales Target Planning", "width": 160},
		{"fieldname": "title", "label": _("Title"), "fieldtype": "Data", "width": 180},
		{"fieldname": "planning_version", "label": _("Version"), "fieldtype": "Int", "width": 80},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 110},
		{"fieldname": "company", "label": _("Company"), "fieldtype": "Link", "options": "Company", "width": 140},
		{"fieldname": "fiscal_year", "label": _("Fiscal Year"), "fieldtype": "Link", "options": "Fiscal Year", "width": 120},
		{"fieldname": "owner", "label": _("Created By"), "fieldtype": "Link", "options": "User", "width": 140},
		{"fieldname": "creation", "label": _("Created On"), "fieldtype": "Datetime", "width": 150},
		{"fieldname": "approved_by", "label": _("Approved By"), "fieldtype": "Link", "options": "User", "width": 140},
		{"fieldname": "approved_on", "label": _("Approved On"), "fieldtype": "Datetime", "width": 150},
		{"fieldname": "rows_count", "label": _("Rows"), "fieldtype": "Int", "width": 80},
		{"fieldname": "rows_overridden", "label": _("Overrides"), "fieldtype": "Int", "width": 90},
		{"fieldname": "rows_requiring_review", "label": _("Warnings"), "fieldtype": "Int", "width": 90},
		{"fieldname": "summary_warnings", "label": _("Warning Detail"), "fieldtype": "Data", "width": 280},
	]
	flt = {}
	if filters.get("company"):
		flt["company"] = filters.company
	if filters.get("fiscal_year"):
		flt["fiscal_year"] = filters.fiscal_year
	if filters.get("status"):
		flt["status"] = filters.status
	data = frappe.get_all(
		"Sales Target Planning",
		filters=flt,
		fields=[
			"name",
			"title",
			"planning_version",
			"status",
			"company",
			"fiscal_year",
			"owner",
			"creation",
			"approved_by",
			"approved_on",
			"rows_count",
			"rows_overridden",
			"rows_requiring_review",
			"summary_warnings",
		],
		order_by="creation desc",
	)
	return columns, data
