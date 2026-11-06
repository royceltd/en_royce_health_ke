# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

from frappe import _

from royce_health_ke.moh.moh705 import compute


def execute(filters=None):
	filters = filters or {}
	columns = [
		{"fieldname": "code", "label": _("Code"), "fieldtype": "Data", "width": 70},
		{"fieldname": "indicator", "label": _("Indicator"), "fieldtype": "Data", "width": 260},
		*[{"fieldname": f"d{d}", "label": str(d), "fieldtype": "Int", "width": 45} for d in range(1, 32)],
		{"fieldname": "total", "label": _("Total"), "fieldtype": "Int", "width": 70},
	]
	data = compute(filters["company"], filters["year"], filters["month"], filters.get("form") or "705A")
	return columns, data
