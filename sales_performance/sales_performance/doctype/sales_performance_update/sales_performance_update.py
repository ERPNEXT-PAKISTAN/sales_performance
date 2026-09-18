import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime
from sales_performance.services.access import require_manager, scope

class SalesPerformanceUpdate(Document):
    def validate(self):
        scope(self.company, self.sales_person)
        if not self.flags.personal_action:
            require_manager(self.company, self.sales_person)
        if self.response and self.has_value_changed("response"):
            require_manager(self.company, self.sales_person)
            self.responded_by = frappe.session.user
            self.responded_on = now_datetime()
            self.status = "Answered"
