"""Server-side scope shared by every Sales Performance entry point."""
import frappe
from frappe import _

ADMIN_ROLES = {"System Manager", "Sales Performance Admin"}
MANAGER_ROLES = {"Sales Manager", "Sales Target Manager", "Sales Target Approver", "Sales Performance Manager", "Accounts Manager"}


def is_admin(user=None):
    user = user or frappe.session.user
    return user == "Administrator" or bool(ADMIN_ROLES.intersection(frappe.get_roles(user)))


def assignments(user=None):
    user = user or frappe.session.user
    if not user or user == "Guest":
        return []
    result = []
    if frappe.db.exists("DocType", "Sales Performance Assignment"):
        result.extend(frappe.get_all("Sales Performance Assignment", filters={"user": user, "enabled": 1},
                                    fields=["company", "sales_person", "include_team"]))
    employees = frappe.get_all("Employee", filters={"user_id": user, "status": "Active"}, fields=["name", "company"])
    for employee in employees:
        for person in frappe.get_all("Sales Person", filters={"employee": employee.name, "enabled": 1}, pluck="name"):
            result.append(frappe._dict(company=employee.company, sales_person=person, include_team=0))
    return result


def scope(company=None, requested=None, user=None):
    user = user or frappe.session.user
    if not user or user == "Guest":
        frappe.throw(_("Please sign in"), frappe.PermissionError)
    if is_admin(user):
        return [requested] if requested else None
    people = set()
    for assignment in assignments(user):
        if company and assignment.company != company:
            continue
        people.add(assignment.sales_person)
        if assignment.include_team:
            bounds = frappe.db.get_value("Sales Person", assignment.sales_person, ["lft", "rgt"], as_dict=True)
            if bounds:
                people.update(frappe.get_all("Sales Person", filters={"lft": [">=", bounds.lft], "rgt": ["<=", bounds.rgt], "enabled": 1}, pluck="name"))
    if not people:
        frappe.throw(_("Your account has no Sales Person assignment for this company. Ask your administrator to link your Employee or create a Sales Performance Assignment."), frappe.PermissionError)
    if requested:
        if not isinstance(requested, str) or requested not in people:
            frappe.throw(_("You cannot view this Sales Person"), frappe.PermissionError)
        return [requested]
    return sorted(people)


def scoped_filters(filters):
    filters = frappe._dict(filters or {})
    filters._allowed_sales_persons = scope(filters.get("company"), filters.get("sales_person"))
    return filters


def require_manager(company=None, sales_person=None):
    if not is_admin() and not MANAGER_ROLES.intersection(frappe.get_roles()):
        frappe.throw(_("Manager access is required"), frappe.PermissionError)
    return scope(company, sales_person)


def document_permission(doc, user=None, ptype=None):
    if is_admin(user):
        return True
    try:
        allowed = set(scope(doc.get("company"), user=user))
    except frappe.PermissionError:
        return False
    if ptype not in (None, "read", "print", "export", "email", "select"):
        roles = set(frappe.get_roles(user))
        planning_author = doc.doctype == "Sales Target Planning" and "Sales Target User" in roles
        if not MANAGER_ROLES.intersection(roles) and not planning_author:
            return False
    person = doc.get("sales_person")
    if not person or person not in allowed:
        return False
    for field in ("proposal_details", "monthly_details", "items"):
        for row in doc.get(field) or []:
            if row.get("sales_person") and row.sales_person not in allowed:
                return False
    return True  # Frappe still enforces the underlying role permissions.


def query_conditions(user=None, doctype="Sales Target Planning"):
    if is_admin(user):
        return ""
    try:
        people = scope(user=user)
    except frappe.PermissionError:
        return "1=0"
    esc = frappe.db.escape
    table = "`tab" + doctype + "`"
    clauses = []
    child = {"Sales Target Planning": "Target Proposal Detail", "Sales Incentive Payout": "Sales Incentive Payout Item"}.get(doctype)
    for company in sorted({a.company for a in assignments(user)}):
        people_sql = ",".join(esc(p) for p in scope(company, user=user))
        clause = f"({table}.sales_person in ({people_sql}) and {table}.company={esc(company)}"
        if child:
            clause += f" and not exists (select 1 from `tab{child}` detail where detail.parent={table}.name and detail.parenttype={esc(doctype)} and ifnull(detail.sales_person, '') != '' and detail.sales_person not in ({people_sql}))"
        clauses.append(clause + ")")
    return "(" + " or ".join(clauses) + ")" if clauses else "1=0"


def payout_query(user=None):
    return query_conditions(user, "Sales Incentive Payout")


def update_query(user=None):
    return query_conditions(user, "Sales Performance Update")
