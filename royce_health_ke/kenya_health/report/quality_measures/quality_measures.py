# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

from frappe import _

from royce_health_ke.quality import calculate


def execute(filters=None):
	filters = filters or {}
	columns = [
		{
			"fieldname": "measure",
			"label": _("Code"),
			"fieldtype": "Link",
			"options": "Quality Measure",
			"width": 140,
		},
		{"fieldname": "measure_name", "label": _("Measure"), "fieldtype": "Data", "width": 360},
		{"fieldname": "domain", "label": _("Domain"), "fieldtype": "Data", "width": 170},
		{"fieldname": "numerator", "label": _("Numerator"), "fieldtype": "Int", "width": 100},
		{"fieldname": "denominator", "label": _("Denominator"), "fieldtype": "Int", "width": 110},
		{"fieldname": "rate", "label": _("Rate %"), "fieldtype": "Percent", "width": 90},
		{"fieldname": "target", "label": _("Target %"), "fieldtype": "Percent", "width": 90},
		{"fieldname": "met", "label": _("Met"), "fieldtype": "Data", "width": 60},
		{"fieldname": "source", "label": _("Source"), "fieldtype": "Data", "width": 110},
	]
	return columns, calculate(filters["company"], filters["from_date"], filters["to_date"])
