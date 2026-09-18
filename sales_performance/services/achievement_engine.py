"""Achievement metrics. Safe with zero targets."""

from sales_performance.services.numbers import nflt
from sales_performance.services.precision import get_currency_precision, get_qty_precision, round_percent


def achievement_percent(actual, target):
	if not nflt(target):
		return None
	return round_percent(nflt(actual) / nflt(target) * 100.0)


def compute_metrics(target_qty, actual_qty, target_amount, actual_amount):
	qp, ap = get_qty_precision(), get_currency_precision()
	qty_var = nflt(nflt(actual_qty) - nflt(target_qty), qp)
	amt_var = nflt(nflt(actual_amount) - nflt(target_amount), ap)
	return {
		"raw_target_qty": nflt(target_qty), "raw_actual_qty": nflt(actual_qty),
		"raw_target_amount": nflt(target_amount), "raw_actual_amount": nflt(actual_amount),
		"target_qty": nflt(target_qty, qp),
		"actual_qty": nflt(actual_qty, qp),
		"variance_qty": qty_var,
		"qty_achievement_percent": achievement_percent(actual_qty, target_qty),
		"target_amount": nflt(target_amount, ap),
		"actual_amount": nflt(actual_amount, ap),
		"variance_amount": amt_var,
		"amount_achievement_percent": achievement_percent(actual_amount, target_amount),
		"remaining_qty": nflt(max(nflt(target_qty) - nflt(actual_qty), 0), qp),
		"remaining_amount": nflt(max(nflt(target_amount) - nflt(actual_amount), 0), ap),
	}


def remaining_target(target, actual):
	return max(nflt(target) - nflt(actual), 0)
