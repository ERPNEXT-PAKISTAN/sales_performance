"""Achievement metrics. Safe with zero targets."""

from sales_performance.services.numbers import nflt


def achievement_percent(actual, target):
	if not nflt(target):
		return None
	return nflt(nflt(actual) / nflt(target) * 100.0, 2)


def compute_metrics(target_qty, actual_qty, target_amount, actual_amount):
	qty_var = nflt(actual_qty) - nflt(target_qty)
	amt_var = nflt(actual_amount) - nflt(target_amount)
	return {
		"target_qty": nflt(target_qty),
		"actual_qty": nflt(actual_qty),
		"variance_qty": qty_var,
		"qty_achievement_percent": achievement_percent(actual_qty, target_qty),
		"target_amount": nflt(target_amount),
		"actual_amount": nflt(actual_amount),
		"variance_amount": amt_var,
		"amount_achievement_percent": achievement_percent(actual_amount, target_amount),
		"remaining_qty": max(nflt(target_qty) - nflt(actual_qty), 0),
		"remaining_amount": max(nflt(target_amount) - nflt(actual_amount), 0),
	}


def remaining_target(target, actual):
	return max(nflt(target) - nflt(actual), 0)
