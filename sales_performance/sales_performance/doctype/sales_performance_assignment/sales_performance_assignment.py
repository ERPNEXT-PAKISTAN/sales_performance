import frappe
from frappe.model.document import Document

class SalesPerformanceAssignment(Document):
    def validate(self):
        if self.user == "Guest":
            frappe.throw("Guest cannot receive Sales Performance access")
        if frappe.db.exists(self.doctype, {"user": self.user, "company": self.company, "sales_person": self.sales_person, "name": ["!=", self.name]}):
            frappe.throw("This assignment already exists")
