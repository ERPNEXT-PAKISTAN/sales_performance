import os

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


ROLES = [
	"Sales Target User",
	"Sales Target Manager",
	"Sales Target Approver",
	"Sales Performance Manager",
	"Sales Performance Admin",
]


def after_install():
	setup_sales_performance()


def after_migrate():
	setup_sales_performance()


def setup_sales_performance():
	ensure_roles()
	ensure_target_detail_trace_fields()
	ensure_desktop()
	from sales_performance.permissions import apply_sales_performance_roles

	apply_sales_performance_roles()
	frappe.clear_cache(doctype="Target Detail")
	frappe.clear_cache(doctype="Sales Target Planning")
	frappe.clear_cache()


def ensure_roles():
	for role in ROLES:
		if frappe.db.exists("Role", role):
			continue
		doc = frappe.get_doc(
			{
				"doctype": "Role",
				"role_name": role,
				"desk_access": 1,
			}
		)
		doc.insert(ignore_permissions=True)


def ensure_target_detail_trace_fields():
	"""Traceability from official ERPNext Target Detail back to the planning document.

	Does not alter ERPNext core JSON. Item-level targets continue to use the
	custom `item` field provided by the item_sales_target app when present.
	"""
	create_custom_fields(
		{
			"Target Detail": [
				{
					"fieldname": "custom_source_planning",
					"label": "Source Planning",
					"fieldtype": "Link",
					"options": "Sales Target Planning",
					"insert_after": "distribution_id",
					"read_only": 1,
				},
				{
					"fieldname": "custom_planning_version",
					"label": "Planning Version",
					"fieldtype": "Int",
					"insert_after": "custom_source_planning",
					"read_only": 1,
				},
				{
					"fieldname": "custom_planning_key",
					"label": "Planning Key",
					"fieldtype": "Data",
					"insert_after": "custom_planning_version",
					"read_only": 1,
					"hidden": 1,
				},
				{
					"fieldname": "custom_approved_by",
					"label": "Approved By",
					"fieldtype": "Link",
					"options": "User",
					"insert_after": "custom_planning_key",
					"read_only": 1,
				},
				{
					"fieldname": "custom_approved_on",
					"label": "Approved On",
					"fieldtype": "Datetime",
					"insert_after": "custom_approved_by",
					"read_only": 1,
				},
			]
		},
		update=True,
	)


def ensure_desktop():
	"""Frappe v16 desk home uses Desktop Icon + Workspace Sidebar, not Module Def."""
	from frappe.desk.doctype.desktop_icon.desktop_icon import (
		clear_desktop_icons_cache,
		create_desktop_icons,
	)
	from frappe.modules.import_file import import_file_by_path

	for parts in (
		("workspace_sidebar", "sales_performance.json"),
		("desktop_icon", "sales_performance.json"),
	):
		path = frappe.get_app_path("sales_performance", *parts)
		if path and os.path.exists(path):
			import_file_by_path(path, force=True)

	for page_name in ("incentive_dashboard", "performance_analytics"):
		page_json = frappe.get_app_path(
			"sales_performance", "sales_performance", "page", page_name, f"{page_name}.json"
		)
		if page_json and os.path.exists(page_json):
			import_file_by_path(page_json, force=True)

	workspace = frappe.get_app_path(
		"sales_performance", "sales_performance", "workspace", "sales_performance", "sales_performance.json"
	)
	if workspace and os.path.exists(workspace):
		import_file_by_path(workspace, force=True)

	_ensure_workspace_exists()

	if frappe.db.exists("Desktop Icon", "Sales Performance"):
		frappe.db.set_value("Desktop Icon", "Sales Performance", "hidden", 0)
		frappe.db.set_value(
			"Desktop Icon",
			"Sales Performance",
			"logo_url",
			"/assets/sales_performance/images/sales-performance-logo.png",
		)
		frappe.db.set_value("Desktop Icon", "Sales Performance", "sidebar", "Sales Performance")
		frappe.db.set_value("Desktop Icon", "Sales Performance", "link_type", "Workspace Sidebar")
		frappe.db.set_value("Desktop Icon", "Sales Performance", "link_to", "Sales Performance")
		frappe.db.set_value("Desktop Icon", "Sales Performance", "icon_type", "Link")
		frappe.db.set_value("Desktop Icon", "Sales Performance", "standard", 1)
		frappe.db.set_value("Desktop Icon", "Sales Performance", "bg_color", "blue")
		frappe.db.set_value("Desktop Icon", "Sales Performance", "icon", "chart-bar")

	if frappe.db.exists("Workspace", "Sales Performance"):
		frappe.db.set_value("Workspace", "Sales Performance", "public", 1)
		frappe.db.set_value("Workspace", "Sales Performance", "is_hidden", 0)
		frappe.db.set_value("Workspace", "Sales Performance", "icon", "chart-bar")

	try:
		create_desktop_icons()
	except Exception:
		frappe.log_error(title="Sales Performance desktop icon setup")

	clear_desktop_icons_cache()


def _ensure_workspace_exists():
	if frappe.db.exists("Workspace", "Sales Performance"):
		return
	if not frappe.db.exists("Module Def", "Sales Performance"):
		frappe.get_doc(
			{
				"doctype": "Module Def",
				"module_name": "Sales Performance",
				"app_name": "sales_performance",
			}
		).insert(ignore_permissions=True)
	doc = frappe.get_doc(
		{
			"doctype": "Workspace",
			"label": "Sales Performance",
			"title": "Sales Performance",
			"module": "Sales Performance",
			"app": "sales_performance",
			"icon": "chart-bar",
			"public": 1,
			"is_hidden": 0,
			"type": "Workspace",
			"content": "[]",
		}
	)
	from sales_performance.permissions import DESK_ROLES

	for role in DESK_ROLES:
		if frappe.db.exists("Role", role):
			doc.append("roles", {"role": role})
	doc.insert(ignore_permissions=True)
