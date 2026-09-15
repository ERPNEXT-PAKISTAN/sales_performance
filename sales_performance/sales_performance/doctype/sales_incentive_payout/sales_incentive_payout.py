import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, today

from sales_performance.services.incentive_engine import (
	collect_period_incentive_rows,
	scheme_settings,
	summarize_payout_by_sales_person,
)
from sales_performance.services.planning_engine import fiscal_year_dates


class SalesIncentivePayout(Document):
	def validate(self):
		self._drop_empty_items()
		self._apply_account_defaults()
		if not self.pay_on:
			self.pay_on = "Amount"
		self._refresh_incentive_totals()
		if self.from_date and self.to_date and getdate(self.from_date) > getdate(self.to_date):
			frappe.throw(_("From Date cannot be after To Date"))
		if getattr(self, "_action", None) == "submit":
			if not self.items:
				frappe.throw(_("Add incentive rows or click Get Incentives"))
			if self.total_incentive_amount <= 0:
				frappe.throw(_("Total incentive must be greater than zero"))
		if self.docstatus == 0:
			self.payment_status = "Draft"

	def _refresh_incentive_totals(self):
		self.total_incentive_on_amount = sum(flt(row.incentive_on_amount) for row in self.items or [])
		self.total_incentive_on_qty = sum(flt(row.incentive_on_qty) for row in self.items or [])
		self.total_incentive_amount = sum(flt(row.incentive_amount) for row in self.items or [])

	def _drop_empty_items(self):
		"""Grid placeholder rows have no amount; they must not block Get Incentives / Save."""
		for row in list(self.get("items") or []):
			if flt(row.incentive_amount) <= 0 and not row.incentive_band:
				self.remove(row)

	def on_submit(self):
		self.db_set("journal_entry", _post_accrual_journal_entry(self))
		self.db_set("payment_status", "Not Paid")
		frappe.msgprint(
			_("GL posted: Incentive Expense Dr / Incentive Payable Cr. Status is Not Paid until you click Pay Now."),
			alert=True,
			indicator="orange",
		)

	def on_cancel(self):
		self._cancel_voucher(getattr(self, "payment_journal_entry", None), "Journal Entry")
		self._cancel_voucher(self.payment_entry, "Payment Entry")
		self._cancel_voucher(self.journal_entry, "Journal Entry")
		self.db_set("payment_status", "Draft")

	def _cancel_voucher(self, name, doctype):
		if not name or not frappe.db.exists(doctype, name):
			return
		voucher = frappe.get_doc(doctype, name)
		if voucher.docstatus == 1:
			voucher.cancel()

	def before_insert(self):
		if not self.naming_series:
			self.naming_series = "SIP-.YYYY.-"
		self._apply_account_defaults()

	def _apply_account_defaults(self):
		if not self.cost_center and self.company:
			self.cost_center = frappe.db.get_value("Company", self.company, "cost_center")
		if self.expense_account and self.payable_account and self.paid_from_account and self.cost_center:
			return
		if not frappe.db.exists("DocType", "Sales Performance Settings"):
			return
		meta = frappe.get_meta("Sales Performance Settings")
		def setting(fieldname):
			if not meta.has_field(fieldname):
				return None
			return frappe.db.get_single_value("Sales Performance Settings", fieldname)

		if not self.expense_account:
			self.expense_account = setting("incentive_expense_account")
		if not self.payable_account:
			self.payable_account = setting("incentive_payable_account")
		if not self.paid_from_account:
			self.paid_from_account = setting("incentive_paid_from_account")
		if not self.cost_center:
			self.cost_center = setting("incentive_cost_center") or frappe.db.get_value(
				"Company", self.company, "cost_center"
			)

	@frappe.whitelist()
	def get_incentives(self):
		self.check_permission("write")
		if not self.company or not self.fiscal_year:
			frappe.throw(_("Company and Fiscal Year are required"))
		start, end = fiscal_year_dates(self.fiscal_year, self.company)
		if not self.from_date or not self.to_date:
			self.from_date = self.from_date or start
			self.to_date = self.to_date or end
		# Always read actuals for the full fiscal year so Month / Quarter filters
		# can split correctly. Header From/To is posting context only.
		rows = collect_period_incentive_rows(
			{
				"company": self.company,
				"fiscal_year": self.fiscal_year,
				"from_date": start,
				"to_date": end,
				"sales_person": self.sales_person,
				"customer_group": self.customer_group,
				"period": self.period or "Monthly",
				"month": self.month,
				"quarter": self.quarter,
				"pay_on": self.pay_on or "Amount",
			}
		)
		slabs, based_on, pay_on = scheme_settings(
			{
				"company": self.company,
				"fiscal_year": self.fiscal_year,
				"pay_on": self.pay_on or "Amount",
			}
		)
		summary = summarize_payout_by_sales_person(rows, slabs, based_on, pay_on)
		self.set("items", [])
		for row in summary:
			employee = None
			if row.get("sales_person"):
				employee = frappe.db.get_value("Sales Person", row["sales_person"], "employee")
			amount = flt(row.get("incentive_amount"))
			if amount <= 0:
				continue
			child = self.append("items", {})
			child.sales_person = row.get("sales_person") or None
			child.customer_group = row.get("customer_group") or self.customer_group or None
			child.employee = employee
			child.period = row.get("period")
			child.incentive_band = row.get("incentive_band")
			child.incentive_rate_percent = flt(row.get("incentive_rate_percent"))
			child.incentive_qty = flt(row.get("incentive_qty"))
			child.incentive_on_amount = flt(row.get("incentive_on_amount"))
			child.incentive_on_qty = flt(row.get("incentive_on_qty"))
			child.incentive_amount = amount
		self._refresh_incentive_totals()
		on_amount = flt(self.total_incentive_on_amount)
		on_qty = flt(self.total_incentive_on_qty)
		frappe.msgprint(
			_(
				"Pay Incentive On: {0}<br>"
				"Incentive on Amount: {1}<br>"
				"Incentive on Qty: {2}<br>"
				"Payable Incentive: {3}"
			).format(
				self.pay_on or "Amount",
				frappe.format_value(on_amount, {"fieldtype": "Currency"}),
				frappe.format_value(on_qty, {"fieldtype": "Float"}),
				frappe.format_value(self.total_incentive_amount, {"fieldtype": "Currency"}),
			),
			title=_("Incentives loaded"),
			indicator="blue",
		)
		if not self.items:
			frappe.msgprint(
				_(
					"No incentive to pay for {0} / {1} {2}. "
					"Incentive is paid only on surplus above target when achievement meets the scheme slab."
				).format(
					self.sales_person or _("all sales persons"),
					self.period or _("Annual"),
					self.month or self.quarter or self.fiscal_year,
				)
			)
		self.flags.ignore_mandatory = True
		self.save()
		self.flags.ignore_mandatory = False
		return self.as_dict()

	@frappe.whitelist()
	def mark_as_paid(self):
		self.check_permission("write")
		if self.docstatus != 1:
			frappe.throw(_("Submit the payout first to post accrual GL, then Pay Now"))
		if self.payment_status == "Paid" and (self.payment_journal_entry or self.payment_entry):
			return self.payment_journal_entry or self.payment_entry
		if not self.paid_from_account:
			frappe.throw(_("Set Pay From Account (Bank / Cash) before paying"))
		if self.payment_journal_entry:
			return self.payment_journal_entry
		je_name = _post_payment_journal_entry(self)
		self.db_set("payment_journal_entry", je_name)
		self.db_set("payment_status", "Paid")
		self.db_set("paid_on", today())
		frappe.msgprint(
			_("GL posted: Incentive Payable Dr / {0} Cr. Status is Paid.").format(self.paid_from_account),
			alert=True,
			indicator="green",
		)
		return je_name

	@frappe.whitelist()
	def create_payment_entry(self):
		self.check_permission("write")
		if self.docstatus != 1:
			frappe.throw(_("Submit the payout before creating a Payment Entry"))
		if self.payment_entry:
			return self.payment_entry
		if not self.paid_from_account:
			frappe.throw(_("Set Pay From Account (Bank / Cash) on this payout or in Sales Performance Settings"))
		pe = frappe.get_doc(
			{
				"doctype": "Payment Entry",
				"payment_type": "Internal Transfer",
				"company": self.company,
				"posting_date": self.posting_date or today(),
				"paid_from": self.paid_from_account,
				"paid_to": self.payable_account,
				"paid_amount": self.total_incentive_amount,
				"received_amount": self.total_incentive_amount,
				"reference_no": self.name,
				"reference_date": self.posting_date or today(),
				"remarks": _("Sales incentive payment for {0}").format(self.name),
			}
		)
		pe.insert(ignore_permissions=True)
		self.db_set("payment_entry", pe.name)
		return pe.name


@frappe.whitelist()
def mark_as_paid(name=None, doc=None, docs=None):
	payout = _payout_from_request(name, doc, docs)
	return payout.mark_as_paid()


@frappe.whitelist()
def get_incentives(name=None, doc=None, docs=None):
	"""Module entry for Button / frm.call (Frappe resolves method as a module function)."""
	payout = _payout_from_request(name, doc, docs)
	payout.check_permission("write")
	payout.get_incentives()
	return payout.as_dict()


@frappe.whitelist()
def create_payment_entry(name=None, doc=None, docs=None):
	payout = _payout_from_request(name, doc, docs)
	return payout.create_payment_entry()


def _payout_from_request(name=None, doc=None, docs=None):
	if not doc and docs:
		doc = docs
	if name:
		return frappe.get_doc("Sales Incentive Payout", name)
	if doc:
		data = frappe.parse_json(doc) if isinstance(doc, str) else doc
		if isinstance(data, list):
			data = data[0]
		if data.get("name") and not str(data.get("name")).startswith("new-"):
			payout = frappe.get_doc("Sales Incentive Payout", data.get("name"))
			payout.update(data)
			return payout
		return frappe.get_doc(data)
	name = frappe.form_dict.get("name") or frappe.form_dict.get("docname")
	if not name:
		frappe.throw(_("Payout document name is required"))
	return frappe.get_doc("Sales Incentive Payout", name)


def _post_accrual_journal_entry(doc):
	if not doc.expense_account or not doc.payable_account:
		frappe.throw(_("Incentive Expense Account and Incentive Payable Account are required"))
	cost_center = doc.cost_center or frappe.db.get_value("Company", doc.company, "cost_center")
	amount = flt(doc.total_incentive_amount)
	je = frappe.get_doc(
		{
			"doctype": "Journal Entry",
			"voucher_type": "Journal Entry",
			"company": doc.company,
			"posting_date": doc.posting_date or today(),
			"user_remark": _("Sales incentive accrual for {0} / {1}").format(doc.name, doc.fiscal_year),
		}
	)
	je.append(
		"accounts",
		{
			"account": doc.expense_account,
			"debit_in_account_currency": amount,
			"credit_in_account_currency": 0,
			"cost_center": cost_center,
			"user_remark": _("Sales incentive expense"),
		},
	)
	je.append(
		"accounts",
		{
			"account": doc.payable_account,
			"debit_in_account_currency": 0,
			"credit_in_account_currency": amount,
			"cost_center": cost_center,
			"user_remark": _("Sales incentive payable"),
		},
	)
	je.insert(ignore_permissions=True)
	je.submit()
	return je.name


def _post_payment_journal_entry(doc):
	if not doc.payable_account or not doc.paid_from_account:
		frappe.throw(_("Incentive Payable Account and Pay From Account are required to mark Paid"))
	cost_center = doc.cost_center or frappe.db.get_value("Company", doc.company, "cost_center")
	amount = flt(doc.total_incentive_amount)
	je = frappe.get_doc(
		{
			"doctype": "Journal Entry",
			"voucher_type": "Journal Entry",
			"company": doc.company,
			"posting_date": today(),
			"user_remark": _("Sales incentive payment for {0}").format(doc.name),
		}
	)
	je.append(
		"accounts",
		{
			"account": doc.payable_account,
			"debit_in_account_currency": amount,
			"credit_in_account_currency": 0,
			"cost_center": cost_center,
			"user_remark": _("Clear incentive payable"),
		},
	)
	je.append(
		"accounts",
		{
			"account": doc.paid_from_account,
			"debit_in_account_currency": 0,
			"credit_in_account_currency": amount,
			"cost_center": cost_center,
			"user_remark": _("Pay sales incentive"),
		},
	)
	je.insert(ignore_permissions=True)
	je.submit()
	return je.name


def on_payment_entry_submit(doc, method=None):
	name = frappe.db.get_value("Sales Incentive Payout", {"payment_entry": doc.name, "docstatus": 1}, "name")
	if not name:
		return
	frappe.db.set_value("Sales Incentive Payout", name, "payment_status", "Paid")
	frappe.db.set_value("Sales Incentive Payout", name, "paid_on", doc.posting_date or today())


def on_payment_entry_cancel(doc, method=None):
	name = frappe.db.get_value("Sales Incentive Payout", {"payment_entry": doc.name, "docstatus": 1}, "name")
	if not name:
		return
	if frappe.db.get_value("Sales Incentive Payout", name, "payment_journal_entry"):
		return
	frappe.db.set_value("Sales Incentive Payout", name, "payment_status", "Not Paid")
	frappe.db.set_value("Sales Incentive Payout", name, "paid_on", None)
