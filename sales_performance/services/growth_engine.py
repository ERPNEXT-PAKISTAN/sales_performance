"""Item Group growth application. Pure math is isolated for tests."""

from sales_performance.services.numbers import ncint, nflt
from sales_performance.services.precision import round_qty


def apply_growth(previous_qty, growth_percent, precision=3, whole_number=False):
	"""Target Qty = Previous Year Net Qty × (1 + Growth % / 100)."""
	return round_qty(
		nflt(previous_qty) * (1 + nflt(growth_percent) / 100.0),
		precision=precision,
		whole_number=whole_number,
	)


def resolve_growth_percent(item_group, rules, item_group_ancestors=None):
	"""Pick the highest-priority matching rule.

	rules: list of dicts with item_group, growth_percent, apply_to_children, priority
	item_group_ancestors: list from leaf to root (inclusive), used when apply_to_children
	"""
	if not rules:
		return 0.0, None

	ancestors = item_group_ancestors or [item_group]
	ranked = sorted(rules, key=lambda r: ncint(r.get("priority") or 0), reverse=True)

	for rule in ranked:
		rule_group = rule.get("item_group")
		if not rule_group:
			continue
		if rule_group == item_group:
			return nflt(rule.get("growth_percent")), rule_group
		if ncint(rule.get("apply_to_children")) and rule_group in ancestors:
			return nflt(rule.get("growth_percent")), rule_group

	return 0.0, None


def item_group_in_subtree(item_group, root_group, item_group_ancestors=None):
	"""True when item_group is root_group or a descendant of it."""
	if not root_group:
		return True
	if not item_group:
		return False
	if item_group == root_group:
		return True
	ancestors = item_group_ancestors if item_group_ancestors is not None else [item_group]
	return root_group in ancestors


def growth_rule_covers_item_group(item_group, rules, item_group_ancestors=None):
	"""True when a growth rule applies to this item group (exact or children)."""
	_pct, source = resolve_growth_percent(item_group, rules, item_group_ancestors)
	return bool(source)


def get_item_group_subtree_names(item_group):
	"""Item group plus all descendants (nested-set)."""
	import frappe

	if not item_group:
		return []
	bounds = frappe.db.get_value("Item Group", item_group, ["lft", "rgt"], as_dict=True)
	if not bounds:
		return [item_group]
	return frappe.get_all(
		"Item Group",
		filters={"lft": [">=", bounds.lft], "rgt": ["<=", bounds.rgt]},
		pluck="name",
	)


def get_customer_group_subtree_names(customer_group):
	"""Customer group plus all descendants (nested-set)."""
	import frappe

	if not customer_group:
		return []
	bounds = frappe.db.get_value("Customer Group", customer_group, ["lft", "rgt"], as_dict=True)
	if not bounds:
		return [customer_group]
	return frappe.get_all(
		"Customer Group",
		filters={"lft": [">=", bounds.lft], "rgt": ["<=", bounds.rgt]},
		pluck="name",
	)


def get_item_group_ancestors(item_group):
	"""Return [leaf, parent, ..., root] using ERPNext Item Group tree."""
	import frappe

	if not item_group:
		return []

	chain = []
	current = item_group
	seen = set()
	while current and current not in seen:
		seen.add(current)
		chain.append(current)
		current = frappe.db.get_value("Item Group", current, "parent_item_group")
	return chain
