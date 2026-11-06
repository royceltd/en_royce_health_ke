# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

from frappe import _

from royce_health_ke.moh.moh711 import AGE_BANDS, compute


def execute(filters=None):
	filters = filters or {}
	columns = [{"fieldname": "indicator", "label": _("Indicator"), "fieldtype": "Data", "width": 400}]
	columns += [{"fieldname": band, "label": band, "fieldtype": "Int", "width": 70} for band in AGE_BANDS]
	columns += [
		{"fieldname": "value", "label": _("Total"), "fieldtype": "Int", "width": 80},
		{"fieldname": "note", "label": _("Note"), "fieldtype": "Data", "width": 220},
	]
	return columns, compute(filters["company"], filters["year"], filters["month"])
