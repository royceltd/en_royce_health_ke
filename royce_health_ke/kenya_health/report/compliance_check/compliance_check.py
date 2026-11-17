# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""The security and privacy safeguards, checked live on this site: what DHA's
certification tests and ODPC's technical safeguards ask for, with what this
site has. Pass, Fail, or Advice (recommended, not required)."""

import frappe
from frappe import _

from royce_health_ke.compliance import checks


def execute(filters=None):
	columns = [
		{"fieldname": "area", "label": _("Area"), "fieldtype": "Data", "width": 120},
		{"fieldname": "safeguard", "label": _("Safeguard"), "fieldtype": "Data", "width": 300},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 90},
		{"fieldname": "current", "label": _("This Site"), "fieldtype": "Data", "width": 200},
		{"fieldname": "expected", "label": _("Expected"), "fieldtype": "Data", "width": 200},
		{"fieldname": "where", "label": _("Where to Change It"), "fieldtype": "Data", "width": 260},
	]
	rows = checks()
	failing = sum(1 for r in rows if r["status"] == "Fail")
	message = (
		_("{0} safeguard(s) need attention.").format(failing) if failing else _("Every safeguard passes.")
	)
	return columns, rows, message
