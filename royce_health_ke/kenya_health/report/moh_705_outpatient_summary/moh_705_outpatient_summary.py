# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

import calendar

from frappe import _

from royce_health_ke.moh.moh705 import compute
from royce_health_ke.moh.periods import MONTH, months_in


def execute(filters=None):
	filters = filters or {}
	form = filters.get("form") or "705A"
	head = [
		{"fieldname": "code", "label": _("Code"), "fieldtype": "Data", "width": 70},
		{"fieldname": "indicator", "label": _("Indicator"), "fieldtype": "Data", "width": 260},
	]
	total = {"fieldname": "total", "label": _("Total"), "fieldtype": "Int", "width": 70}
	if (filters.get("period") or MONTH) == MONTH:
		days = [
			{"fieldname": f"d{d}", "label": str(d), "fieldtype": "Int", "width": 45} for d in range(1, 32)
		]
		return [*head, *days, total], compute(filters["company"], filters["year"], filters["month"], form)

	# Quarter / year: one column per month (each month's total, as on its monthly form).
	months = months_in(filters)
	columns = [
		{"fieldname": f"m{m}", "label": _(calendar.month_abbr[m]), "fieldtype": "Int", "width": 70}
		for _y, m in months
	]
	rows = {}
	for y, m in months:
		for row in compute(filters["company"], y, m, form):
			out = rows.setdefault(
				row["code"], {"code": row["code"], "indicator": row["indicator"], "total": 0}
			)
			out[f"m{m}"] = row["total"]
			out["total"] += row["total"]
	return [*head, *columns, total], list(rows.values())
