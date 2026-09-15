from sales_performance.services.numbers import ncint, nflt

QTY_PRECISION = 0
AMOUNT_PRECISION = 0
PERCENT_PRECISION = 1


def round_qty(qty, precision=None, whole_number=False):
	if whole_number or precision == 0:
		return float(round(nflt(qty)))
	return nflt(qty, ncint(precision if precision is not None else QTY_PRECISION))


def round_amount(amount, precision=None):
	return nflt(amount, ncint(precision if precision is not None else AMOUNT_PRECISION))


def round_percent(value, precision=None):
	if value in (None, ""):
		return None
	return nflt(value, ncint(precision if precision is not None else PERCENT_PRECISION))


def get_qty_precision(uom=None, fallback=None):
	return QTY_PRECISION


def get_currency_precision(fallback=None):
	return AMOUNT_PRECISION


def get_percent_precision(fallback=None):
	return PERCENT_PRECISION
