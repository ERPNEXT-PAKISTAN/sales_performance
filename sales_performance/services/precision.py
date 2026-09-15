from sales_performance.services.numbers import ncint, nflt


def round_qty(qty, precision=3, whole_number=False):
	if whole_number:
		return float(round(nflt(qty)))
	return nflt(qty, ncint(precision))


def round_amount(amount, precision=2):
	return nflt(amount, ncint(precision))


def get_qty_precision(uom=None, fallback=3):
	"""Use UOM whole-number flag and System Settings float precision. Do not hardcode."""
	try:
		import frappe

		if uom and frappe.db.get_value("UOM", uom, "must_be_whole_number"):
			return 0
		fp = frappe.db.get_single_value("System Settings", "float_precision")
		if fp not in (None, ""):
			return ncint(fp)
	except Exception:
		pass
	return fallback


def get_currency_precision(fallback=2):
	try:
		import frappe

		cp = frappe.db.get_single_value("System Settings", "currency_precision")
		if cp not in (None, ""):
			return ncint(cp)
	except Exception:
		pass
	return fallback
