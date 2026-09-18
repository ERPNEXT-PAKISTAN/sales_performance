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
	ensure_customer_group_columns()


def after_migrate():
	setup_sales_performance()
	ensure_customer_group_columns()


def setup_sales_performance():
	ensure_roles()
	ensure_target_detail_trace_fields()
	ensure_nonseasonal_distribution_default()
	ensure_desktop()
	from sales_performance.permissions import apply_sales_performance_roles

	apply_sales_performance_roles()
	frappe.clear_cache(doctype="Target Detail")
	frappe.clear_cache(doctype="Sales Target Planning")
	frappe.clear_cache()


def ensure_nonseasonal_distribution_default():
	"""Migrate only the retired default; never alter a plan or approved detail."""
	if not frappe.db.exists("DocType", "Sales Performance Settings"):
		return
	if frappe.db.get_single_value("Sales Performance Settings", "default_distribution_method") == "Same Month Previous Year + Growth":
		frappe.db.set_single_value("Sales Performance Settings", "default_distribution_method", "Equal Monthly")


def ensure_customer_group_columns():
	"""Add Customer Group columns when DocType JSON is ahead of the MariaDB table."""
	doctypes = (
		("target_proposal_detail", "Target Proposal Detail"),
		("sales_target_monthly_detail", "Sales Target Monthly Detail"),
		("sales_target_planning", "Sales Target Planning"),
		("sales_incentive_payout", "Sales Incentive Payout"),
		("sales_incentive_payout_item", "Sales Incentive Payout Item"),
	)
	for filename, doctype in doctypes:
		try:
			frappe.reload_doc("sales_performance", "doctype", filename, force=True)
		except Exception:
			frappe.log_error(title=f"Sales Performance reload {doctype}")
		if not frappe.db.has_column(doctype, "customer_group"):
			try:
				frappe.db.sql(
					f"ALTER TABLE `tab{doctype}` ADD COLUMN `customer_group` varchar(140) DEFAULT NULL"
				)
			except Exception:
				frappe.log_error(title=f"Sales Performance add customer_group on {doctype}")
			frappe.clear_cache(doctype=doctype)


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

	for page_name in ("my_sales", "sales_performance_overview", "incentive_dashboard", "monthly_incentives", "performance_analytics", "target_achievement", "achievement_graphics"):
		page_json = frappe.get_app_path(
			"sales_performance", "sales_performance", "page", page_name, f"{page_name}.json"
		)
		if page_json and os.path.exists(page_json):
			import_file_by_path(page_json, force=True)

	for parts in (
		("report", "target_achievement_status", "target_achievement_status.json"),
		("number_card", "item_groups_achieved", "item_groups_achieved.json"),
		("number_card", "item_groups_not_achieved", "item_groups_not_achieved.json"),
		("number_card", "items_achieved", "items_achieved.json"),
		("number_card", "items_not_achieved", "items_not_achieved.json"),
		("dashboard_chart_source", "target_achievement_split", "target_achievement_split.json"),
		("dashboard_chart", "item_groups_vs_items_achievement", "item_groups_vs_items_achievement.json"),
		("sales_performance_dashboard", "target_achievement", "target_achievement.json"),
	):
		path = frappe.get_app_path("sales_performance", "sales_performance", *parts)
		if path and os.path.exists(path):
			import_file_by_path(path, force=True)

	workspace = frappe.get_app_path(
		"sales_performance", "sales_performance", "workspace", "sales_performance", "sales_performance.json"
	)
	if workspace and os.path.exists(workspace):
		import_file_by_path(workspace, force=True)

	_ensure_workspace_exists()

	if frappe.db.exists("Workspace", "Sales Performance"):
		frappe.db.set_value("Workspace", "Sales Performance", "public", 1)
		frappe.db.set_value("Workspace", "Sales Performance", "is_hidden", 0)
		frappe.db.set_value("Workspace", "Sales Performance", "icon", "chart-bar")

	try:
		create_desktop_icons()
	except Exception:
		frappe.log_error(title="Sales Performance desktop icon setup")

	_force_desktop_icon()
	_inject_icon_into_desktop_layouts()
	clear_desktop_icons_cache()
	frappe.cache.delete_key("desktop_icons")


def _force_desktop_icon():
	if not frappe.db.exists("Desktop Icon", "Sales Performance"):
		return
	values = {
		"hidden": 0,
		"standard": 1,
		"icon_type": "App",
		"link_type": "External",
		"link": "/app/sales-performance",
		"sidebar": "Sales Performance",
		"logo_url": "/assets/sales_performance/images/sales-performance-logo.png",
		"bg_color": "blue",
		"icon": "chart-bar",
		"idx": 1,
		"parent_icon": "",
		"app": "sales_performance",
	}
	for field, value in values.items():
		frappe.db.set_value("Desktop Icon", "Sales Performance", field, value, update_modified=False)


def _inject_icon_into_desktop_layouts():
	import json

	for name in frappe.get_all("Desktop Layout", pluck="name"):
		doc = frappe.get_doc("Desktop Layout", name)
		try:
			layout = json.loads(doc.layout or "[]")
		except Exception:
			continue
		if not isinstance(layout, list):
			continue
		if any(isinstance(row, dict) and row.get("label") == "Sales Performance" for row in layout):
			continue
		icon = frappe.get_doc("Desktop Icon", "Sales Performance")
		layout.append(
			{
				"label": icon.label,
				"icon_type": icon.icon_type,
				"link_type": icon.link_type,
				"link": icon.link,
				"logo_url": icon.logo_url,
				"icon": icon.icon,
				"bg_color": icon.bg_color,
				"hidden": 0,
				"standard": 1,
				"idx": icon.idx,
				"name": icon.name,
				"app": icon.app,
			}
		)
		doc.layout = json.dumps(layout)
		doc.flags.ignore_permissions = True
		doc.save()


def boot_session(bootinfo):
	"""Put the app tile on desk even if a saved layout omitted it."""
	icons = list(bootinfo.get("desktop_icons") or [])
	if any(icon.get("label") == "Sales Performance" and not icon.get("hidden") for icon in icons):
		return
	if not frappe.db.exists("Desktop Icon", "Sales Performance"):
		return
	icon = frappe.get_doc("Desktop Icon", "Sales Performance")
	icons.append(
		{
			"label": icon.label,
			"bg_color": icon.bg_color,
			"link": icon.link,
			"link_type": icon.link_type,
			"app": icon.app,
			"icon_type": icon.icon_type,
			"parent_icon": None,
			"icon": icon.icon,
			"link_to": icon.link_to,
			"idx": icon.idx or 1,
			"standard": 1,
			"logo_url": icon.logo_url,
			"hidden": 0,
			"name": icon.name,
			"restrict_removal": icon.restrict_removal,
			"icon_image": icon.icon_image,
		}
	)
	bootinfo.desktop_icons = icons


def _ensure_workspace_exists():
	if frappe.db.exists("Workspace", "Sales Performance"):
		import json

		doc = frappe.get_doc("Workspace", "Sales Performance")
		if doc.content in (None, "", "[]"):
			cards = {
				"Plan & Approve": [("Sales Target Planning", "Sales Target Planning", "DocType"), ("Target Planning Audit", "Target Planning Audit", "Report")],
				"Performance": [("Performance Analytics", "performance-analytics", "Page"), ("Target Achievement", "target-achievement", "Page"), ("Achievement Graphics", "achievement-graphics", "Page")],
				"Reports": [("Sales Target Achievement", "Sales Target Achievement", "Report"), ("Sales Target Monthly Performance", "Sales Target Monthly Performance", "Report"), ("Target Achievement Status", "Target Achievement Status", "Report")],
				"Incentives & Setup": [("Incentive Dashboard", "incentive-dashboard", "Page"), ("Monthly Incentives", "monthly-incentives", "Page"), ("Sales Incentive Payout", "Sales Incentive Payout", "DocType"), ("Incentive Scheme", "Incentive Scheme", "DocType"), ("Sales Performance Settings", "Sales Performance Settings", "DocType")],
			}
			doc.content = json.dumps(
				[{"id": "sp_header", "type": "header", "data": {"text": "Sales Performance", "col": 12}},
				 {"id": "sp_intro", "type": "paragraph", "data": {"text": "Plan targets, review achievement, and manage incentives from one workspace.", "col": 12}}]
				+ [{"id": "sp_card_" + str(index), "type": "card", "data": {"card_name": label, "col": 3}} for index, label in enumerate(cards, 1)]
			)
			existing = {(link.label, link.link_to, link.link_type) for link in doc.links or []}
			for label, entries in cards.items():
				if (label, None, "DocType") not in existing:
					doc.append("links", {"type": "Card Break", "label": label, "link_type": "DocType", "link_count": len(entries)})
				for link_label, link_to, link_type in entries:
					if (link_label, link_to, link_type) not in existing:
						doc.append("links", {"type": "Link", "label": link_label, "link_to": link_to, "link_type": link_type, "is_query_report": 1 if link_type == "Report" else 0})
			doc.flags.ignore_permissions = True
			doc.save()
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
