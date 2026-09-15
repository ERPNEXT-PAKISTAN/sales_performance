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
