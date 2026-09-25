"""Shared selection of active plans for achievement and analytics."""


def applicable_plans(plans):
	"""Keep every approved allocation; otherwise use latest provisional scopes.

	Approval explicitly supersedes the previous revision. Independent approved
	plans can share header dimensions and must not suppress one another.
	"""
	approved = [plan for plan in plans if plan.get("status") == "Approved"]
	if approved:
		return approved
	latest = {}
	for plan in sorted(plans, key=lambda p: p.get("planning_version") or 0, reverse=True):
		if plan.get("status") not in ("Calculated", "Under Review"):
			continue
		key = (plan.get("sales_person") or "", plan.get("territory") or "")
		latest.setdefault(key, plan)
	return list(latest.values())
