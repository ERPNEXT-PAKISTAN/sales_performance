"""Roles shown on desk (icon, workspace, pages, reports) and DocType read access."""

from __future__ import annotations

import frappe

CUSTOM_ROLES = [
	"Sales Target User",
	"Sales Target Manager",
	"Sales Target Approver",
	"Sales Performance Manager",
	"Sales Performance Admin",
]

# Every desk user has All. Include it so the desktop icon and pages appear
# even when custom roles were not assigned on a new site.
DESK_ROLES = [
	"System Manager",
	"Sales User",
	"Sales Manager",
	"Accounts Manager",
	*CUSTOM_ROLES,
]

STANDARD_DOCTYPES = [
	"Sales Target Planning",
	"Sales Incentive Payout",
	"Incentive Scheme",
	"Sales Performance Settings",
]

PAGES = ["my-sales", "sales-performance-overview", "monthly-incentives", "incentive-dashboard", "performance-analytics", "target-achievement", "achievement-graphics"]

REPORTS = [
	"Sales Target Achievement",
	"Sales Target Monthly Performance",
	"Target Planning Audit",
	"Target Achievement Status",
]


def apply_sales_performance_roles():
	_ensure_custom_roles()
	for name in frappe.get_all("DocType", filters={"module": "Sales Performance", "istable": 0}, pluck="name"):
		frappe.db.delete("DocPerm", {"parent": name, "role": ["in", ["All", "Desk User"]]})
		frappe.db.delete("Custom DocPerm", {"parent": name, "role": ["in", ["All", "Desk User"]]})
		frappe.clear_cache(doctype=name)
	for name in STANDARD_DOCTYPES:
		_ensure_doctype_read(name)
	for name in PAGES:
		_set_has_roles("Page", name)
	for name in REPORTS:
		_set_has_roles("Report", name)
	_set_has_roles("Desktop Icon", "Sales Performance")
	_set_has_roles("Workspace", "Sales Performance")


def _ensure_custom_roles():
	for role in CUSTOM_ROLES:
		if frappe.db.exists("Role", role):
			frappe.db.set_value("Role", role, "desk_access", 1)
			continue
		frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(
			ignore_permissions=True
		)


def _set_has_roles(doctype, name):
	if not frappe.db.exists(doctype, name):
		return
	meta = frappe.get_meta(doctype)
	if not meta.has_field("roles"):
		return
	doc = frappe.get_doc(doctype, name)
	existing = {row.role for row in doc.get("roles") or []}
	changed = False
	for role in DESK_ROLES:
		if role in existing:
			continue
		if not frappe.db.exists("Role", role):
			continue
		doc.append("roles", {"role": role})
		changed = True
	if changed:
		doc.flags.ignore_permissions = True
		doc.flags.ignore_validate = True
		doc.flags.ignore_mandatory = True
		doc.save()


def _ensure_doctype_read(doctype):
	if not frappe.db.exists("DocType", doctype):
		return
	doc = frappe.get_doc("DocType", doctype)
	for row in list(doc.permissions or []):
		if row.role in ("All", "Desk User"):
			doc.remove(row)
	removed = doc.has_value_changed("permissions")
	existing = {row.role for row in doc.permissions or []}
	changed = bool(removed)
	for role in DESK_ROLES:
		if role in existing or not frappe.db.exists("Role", role):
			continue
		doc.append(
			"permissions",
			{
				"role": role,
				"read": 1,
				"email": 1,
				"print": 1,
				"report": 1,
				"export": 1,
			},
		)
		changed = True
	if changed:
		doc.flags.ignore_permissions = True
		doc.save()
		frappe.clear_cache(doctype=doctype)
