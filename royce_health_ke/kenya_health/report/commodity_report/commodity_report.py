# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""An MOH commodity report (F-CDRR) for a month: MOH 747A, 730A/730B, 643B,
TB and leprosy. The engine and how each column is worked out:
royce_health_ke/moh/commodities.py."""

import frappe
from frappe import _

from royce_health_ke.moh.commodities import report


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not (filters.form and filters.from_date and filters.to_date and filters.company):
		return columns(), []
	return columns(), report(
		filters.form, filters.from_date, filters.to_date, filters.company, filters.warehouse
	)


def columns():
	number = {"fieldtype": "Float", "width": 105, "precision": 2}
	return [
		{"fieldname": "commodity", "label": _("Commodity"), "fieldtype": "Data", "width": 300},
		{"fieldname": "unit", "label": _("Unit of Issue"), "fieldtype": "Data", "width": 110},
		{"fieldname": "item", "label": _("Our Item"), "fieldtype": "Link", "options": "Item", "width": 140},
		{"fieldname": "beginning", "label": _("Beginning Balance"), **number},
		{"fieldname": "received", "label": _("Received"), **number},
		{"fieldname": "dispensed", "label": _("Dispensed / Used"), **number},
		{"fieldname": "losses", "label": _("Losses"), **number},
		{"fieldname": "adjust_plus", "label": _("Adjustments (+)"), **number},
		{"fieldname": "adjust_minus", "label": _("Adjustments (-)"), **number},
		{"fieldname": "ending", "label": _("Ending Balance (Physical Count)"), **number, "width": 130},
		{"fieldname": "expiring", "label": _("Expiring in 6 Months"), **number},
		{"fieldname": "days_out", "label": _("Days Out of Stock"), "fieldtype": "Int", "width": 95},
		{"fieldname": "requested", "label": _("Quantity Requested"), **number},
	]
