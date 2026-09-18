import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

from sales_performance.services.growth_engine import get_item_group_ancestors, item_group_in_subtree
from sales_performance.services.planning_engine import (
	apply_row_override,
	recalculate_proposal,
	refresh_summary,
)
from sales_performance.services.target_sync import sync_official_targets

LOCKED = ("Approved", "Cancelled", "Superseded")


class SalesTargetPlanning(Document):
	def before_insert(self):
		if not self.naming_series:
			self.naming_series = "STP-.YYYY.-"
		if self.uniform_growth_percent in (None, ""):
			self.uniform_growth_percent = 0
			if frappe.db.exists("DocType", "Sales Performance Settings"):
				self.uniform_growth_percent = (
					frappe.db.get_single_value("Sales Performance Settings", "default_growth_percent") or 0
				)
		if not self.distribution_method:
			self.distribution_method = "Equal Monthly"
			if frappe.db.exists("DocType", "Sales Performance Settings"):
				self.distribution_method = (
					frappe.db.get_single_value("Sales Performance Settings", "default_distribution_method")
					or "Equal Monthly"
				)

	def validate(self):
		self._guard_locked_edits()
		self._validate_business_rules()
		for row in self.proposal_details or []:
			if row.approved_target_qty not in (None, "") and row.approved_target_rate not in (None, ""):
				apply_row_override(row)
		refresh_summary(self)

	def on_trash(self):
		if self.status == "Approved":
			frappe.throw(_("Approved plans cannot be deleted. Cancel or supersede them instead."))

	def _guard_locked_edits(self):
		if self.is_new():
			return
		previous = self.get_doc_before_save()
		if not previous:
			return
		if previous.status in LOCKED and self.status == previous.status:
			frappe.throw(_("Approved, cancelled, or superseded plans cannot be modified. Create a revision."))

	def _validate_business_rules(self):
		if not self.company:
			frappe.throw(_("Company is required"))
		if not self.fiscal_year:
			frappe.throw(_("Fiscal Year is required"))
		if self.from_date and self.to_date and self.from_date > self.to_date:
			frappe.throw(_("From Date cannot be after To Date"))
		if self.pricing_method == "Specific Price List" and not self.price_list:
			frappe.throw(_("Price List is required when Pricing Method is Specific Price List"))
		if self.pricing_method == "Specific Price List" and self.price_list:
			if not frappe.db.exists("Price List", self.price_list):
				frappe.throw(_("Invalid Price List"))

		if self.growth_method == "Item Group Rules" and not self.growth_rules:
			frappe.throw(_("Add at least one Item Group Growth Rule to set targets for selected groups"))
		seen_groups = set()
		for rule in self.growth_rules or []:
			if not rule.item_group:
				frappe.throw(_("Each Item Group Growth Rule must have an Item Group"))
			if rule.item_group in seen_groups:
				frappe.throw(_("Duplicate growth rule for Item Group {0}").format(rule.item_group))
			seen_groups.add(rule.item_group)
			if self.item_group:
				ancestors = get_item_group_ancestors(rule.item_group)
				if not item_group_in_subtree(rule.item_group, self.item_group, ancestors):
					frappe.throw(
						_("Growth rule Item Group {0} must be {1} or a child of it").format(
							rule.item_group, self.item_group
						)
					)

		if self.distribution_method == "Custom Percentage Distribution":
			total = sum(float(p.distribution_percent or 0) for p in (self.custom_percents or []))
			if abs(total - 100) > 0.01:
				frappe.throw(_("Custom distribution percentages must equal 100%"))

		if self.distribution_method == "Manual Monthly" and self.monthly_details and self.status in (
			"Under Review",
			"Approved",
		):
			self._validate_manual_monthly_totals()

		if self.status == "Approved":
			self._validate_approval_readiness()

	def _validate_manual_monthly_totals(self):
		from collections import defaultdict
		from frappe.utils import flt

		from sales_performance.services.precision import get_currency_precision, get_qty_precision

		qty_by_key = defaultdict(float)
		amt_by_key = defaultdict(float)
		for m in self.monthly_details or []:
			qty_by_key[m.row_key] += flt(m.target_qty)
			amt_by_key[m.row_key] += flt(m.target_amount)
		for row in self.proposal_details or []:
			pq = get_qty_precision(row.uom)
			pa = get_currency_precision()
			if abs(flt(qty_by_key[row.row_key], pq) - flt(row.approved_target_qty, pq)) > (10 ** -max(pq, 1)):
				frappe.throw(
					_("Monthly target qty for {0} does not equal the annual approved qty").format(row.item_code)
				)
			if abs(flt(amt_by_key[row.row_key], pa) - flt(row.approved_target_amount, pa)) > (10 ** -max(pa, 1)):
				frappe.throw(
					_("Monthly target amount for {0} does not equal the annual approved amount").format(
						row.item_code
					)
				)

	def _validate_approval_readiness(self):
		from frappe.utils import flt

		if not self.proposal_details:
			frappe.throw(_("Cannot approve a plan with no proposal details"))
		block_price = True
		if frappe.db.exists("DocType", "Sales Performance Settings"):
			block_price = frappe.db.get_single_value("Sales Performance Settings", "block_approval_without_price")
			if block_price is None:
				block_price = True
		critical = []
		for row in self.proposal_details:
			if flt(row.approved_target_qty) < 0:
				frappe.throw(_("Approved target quantity cannot be negative ({0})").format(row.item_code))
			if row.override_percent and not row.override_reason:
				frappe.throw(_("Override reason is required for {0}").format(row.item_code))
			if block_price and not flt(row.approved_target_rate) and flt(row.approved_target_qty):
				critical.append(row.item_code)
		if critical:
			frappe.throw(
				_("Cannot approve: unresolved pricing for items: {0}").format(", ".join(critical[:20]))
			)

	@frappe.whitelist()
	def recalculate(self):
		self.check_permission("write")
		recalculate_proposal(self)
		self.save()
		return self.name

	@frappe.whitelist()
	def approve(self):
		roles = set(frappe.get_roles())
		if not roles.intersection({"Sales Target Approver", "Sales Performance Admin", "System Manager", "Administrator"}):
			frappe.throw(_("Not permitted to approve"))
		if self.status == "Approved":
			return self.name
		if self.status not in ("Calculated", "Under Review"):
			frappe.throw(_("Calculate and review the plan before approval"))
		if self.status in LOCKED and self.status != "Approved":
			frappe.throw(_("This plan cannot be approved"))
		self.status = "Approved"
		self.approved_by = frappe.session.user
		self.approved_on = now_datetime()
		self._validate_approval_readiness()
		self.save()
		if self.previous_planning:
			prev = frappe.get_doc("Sales Target Planning", self.previous_planning)
			if prev.status == "Approved":
				prev.db_set("status", "Superseded")
		sync_official_targets(self)
		return self.name
