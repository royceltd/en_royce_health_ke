# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

from frappe import _

from royce_health_ke.moh.moh717 import compute


def execute(filters=None):
	filters = filters or {}
	columns = [
		{"fieldname": "indicator", "label": _("Indicator"), "fieldtype": "Data", "width": 380},
		{"fieldname": "value", "label": _("Value"), "fieldtype": "Int", "width": 90},
		{"fieldname": "note", "label": _("Note"), "fieldtype": "Data", "width": 160},
	]
	return columns, compute(filters["company"], filters["year"], filters["month"])
