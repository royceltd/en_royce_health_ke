# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""MOH 710: immunisation, vitamin A and EPI summary for a month, from the
Immunisation register (royce_health_ke/immunisation.py)."""

import frappe
from frappe import _

from royce_health_ke.immunisation import moh710


def execute(filters=None):
	filters = frappe._dict(filters or {})
	columns = [
		{"fieldname": "indicator", "label": _("Antigen / Dose"), "fieldtype": "Data", "width": 320},
		{"fieldname": "under_1", "label": _("Under 1 Year"), "fieldtype": "Int", "width": 120},
		{"fieldname": "over_1", "label": _("1 Year and Over"), "fieldtype": "Int", "width": 130},
		{"fieldname": "total", "label": _("Total"), "fieldtype": "Int", "width": 100},
	]
	if not (filters.from_date and filters.to_date):
		return columns, []
	return columns, moh710(filters.from_date, filters.to_date, filters.company)
