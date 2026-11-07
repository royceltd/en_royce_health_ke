# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

from frappe import _

from royce_health_ke.moh.moh706 import compute


def execute(filters=None):
	filters = filters or {}
	columns = [
		{"fieldname": "code", "label": _("Code"), "fieldtype": "Data", "width": 90},
		{"fieldname": "indicator", "label": _("Indicator"), "fieldtype": "Data", "width": 420},
		{"fieldname": "value", "label": _("Value"), "fieldtype": "Int", "width": 90},
		{"fieldname": "note", "label": _("Note"), "fieldtype": "Data", "width": 200},
	]
	return columns, compute(filters["company"], filters["year"], filters["month"])
