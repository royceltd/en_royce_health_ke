# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""The kitchen's list for a day: every admitted patient, bed, diet, meals,
instructions and allergies, with a count per diet to cook for."""

from collections import Counter

import frappe
from frappe import _

from royce_health_ke.kitchen import ward_diet_list


def execute(filters=None):
	filters = frappe._dict(filters or {})
	rows = ward_diet_list(filters.company, filters.date, filters.ward)
	columns = [
		{
			"fieldname": "ward",
			"label": _("Ward"),
			"fieldtype": "Link",
			"options": "Healthcare Service Unit",
			"width": 160,
		},
		{
			"fieldname": "bed",
			"label": _("Bed"),
			"fieldtype": "Link",
			"options": "Healthcare Service Unit",
			"width": 140,
		},
		{"fieldname": "patient_name", "label": _("Patient"), "fieldtype": "Data", "width": 180},
		{
			"fieldname": "diet_type",
			"label": _("Diet"),
			"fieldtype": "Link",
			"options": "Diet Type",
			"width": 130,
		},
		{"fieldname": "meals_per_day", "label": _("Meals"), "fieldtype": "Int", "width": 70},
		{"fieldname": "instructions", "label": _("Instructions"), "fieldtype": "Data", "width": 240},
		{"fieldname": "allergies", "label": _("Allergies"), "fieldtype": "Data", "width": 180},
		{
			"fieldname": "diet_order",
			"label": _("Diet Order"),
			"fieldtype": "Link",
			"options": "Diet Order",
			"width": 120,
		},
	]
	counts = Counter(r.diet_type or _("No diet order") for r in rows)
	summary = [{"label": diet, "value": n, "datatype": "Int"} for diet, n in sorted(counts.items())]
	return columns, rows, None, None, summary
