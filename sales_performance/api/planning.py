"""Whitelisted planning actions."""

import frappe
from frappe.utils import now_datetime

from sales_performance.services.planning_engine import apply_row_override, recalculate_proposal
from sales_performance.services.target_sync import sync_official_targets


@frappe.whitelist()
def recalculate(name):
	doc = frappe.get_doc("Sales Target Planning", name)
	doc.check_permission("write")
	recalculate_proposal(doc)
	doc.save()
	return doc.as_dict()


@frappe.whitelist()
def submit_for_review(name):
	doc = frappe.get_doc("Sales Target Planning", name)
	doc.check_permission("write")
	if doc.status not in ("Calculated", "Draft", "Rejected"):
		frappe.throw("Plan must be calculated before review")
	doc.status = "Under Review"
	doc.save()
	return doc.status


@frappe.whitelist()
def approve_plan(name):
	if not _has_role("Sales Target Approver", "Sales Performance Admin", "System Manager"):
		frappe.throw("Not permitted to approve sales target plans")
	doc = frappe.get_doc("Sales Target Planning", name)
	doc.approve()
	return doc.status


@frappe.whitelist()
def reject_plan(name, reason=None):
	if not _has_role("Sales Target Approver", "Sales Target Manager", "Sales Performance Admin", "System Manager"):
		frappe.throw("Not permitted to reject sales target plans")
	doc = frappe.get_doc("Sales Target Planning", name)
	doc.status = "Rejected"
	if reason:
		doc.notes = (doc.notes or "") + f"\nRejected: {reason}"
	doc.save()
	return doc.status


@frappe.whitelist()
def create_revision(name):
	src = frappe.get_doc("Sales Target Planning", name)
	src.check_permission("read")
	if src.status != "Approved":
		frappe.throw("Only approved plans can be revised")
	new = frappe.copy_doc(src)
	new.status = "Draft"
	new.planning_version = (src.planning_version or 1) + 1
	new.previous_planning = src.name
	new.approved_by = None
	new.approved_on = None
	new.erpnext_targets_synced_on = None
	new.title = f"{src.title or src.name} (v{new.planning_version})"
	new.naming_series = src.naming_series or "STP-.YYYY.-"
	new.insert()
	return new.name


@frappe.whitelist()
def apply_targets(name):
	if not _has_role("Sales Target Approver", "Sales Performance Admin", "System Manager"):
		frappe.throw("Not permitted to apply ERPNext targets")
	doc = frappe.get_doc("Sales Target Planning", name)
	return {"synced": sync_official_targets(doc)}


@frappe.whitelist()
def apply_override(name, row_name, approved_qty, approved_rate, reason):
	if not _has_role("Sales Target Manager", "Sales Target Approver", "Sales Performance Admin", "System Manager"):
		frappe.throw("Not permitted to override targets")
	if not reason:
		frappe.throw("Override reason is required")
	doc = frappe.get_doc("Sales Target Planning", name)
	if doc.status in ("Approved", "Cancelled", "Superseded"):
		frappe.throw("Approved plans cannot be modified. Create a revision.")
	row = next((r for r in doc.proposal_details if r.name == row_name), None)
	if not row:
		frappe.throw("Proposal row not found")
	row.approved_target_qty = approved_qty
	row.approved_target_rate = approved_rate
	row.override_reason = reason
	row.override_by = frappe.session.user
	row.override_on = now_datetime()
	apply_row_override(row)
	from sales_performance.services.planning_engine import refresh_summary

	refresh_summary(doc)
	doc.save()
	return row.as_dict()


def _has_role(*roles):
	user_roles = set(frappe.get_roles())
	return bool(user_roles.intersection(roles))
