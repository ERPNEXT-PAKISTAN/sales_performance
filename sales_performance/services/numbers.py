"""Numeric helpers that work without a Frappe site context."""


def nflt(value, precision=None):
	try:
		if value is None or value == "":
			number = 0.0
		else:
			number = float(value)
	except (TypeError, ValueError):
		number = 0.0
	if precision is None:
		return number
	return round(number, int(precision))


def ncint(value):
	try:
		return int(float(value or 0))
	except (TypeError, ValueError):
		return 0
