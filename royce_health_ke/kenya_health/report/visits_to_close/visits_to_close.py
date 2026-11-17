# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Visits to Close (managers): visits still open after a day, with what each
is waiting for (visit_close.open_items), so none is lost or left half-done;
or completed visits of the last 30 days that still have open items (closed
before the rules, or by a manager with a reason)."""

import frappe
from frappe import _
from frappe.utils import add_days, now_datetime, nowdate

from royce_health_ke.visit_close import open_items

LIMIT = 300


def execute(filters=None):
	filters = frappe._dict(filters or {})
	completed = filters.get("show") == "Completed with open items"
	columns = [
		{
			"fieldname": "visit",
			"label": _("Visit"),
			"fieldtype": "Link",
			"options": "Patient Visit",
			"width": 140,
		},
		{"fieldname": "patient_name", "label": _("Patient"), "fieldtype": "Data", "width": 170},
		{"fieldname": "visit_date", "label": _("Date"), "fieldtype": "Date", "width": 95},
		{"fieldname": "visit_type", "label": _("Type"), "fieldtype": "Data", "width": 100},
		{"fieldname": "payment_method", "label": _("Payment"), "fieldtype": "Data", "width": 85},
		{"fieldname": "current_station", "label": _("Station"), "fieldtype": "Data", "width": 110},
		{"fieldname": "open_items", "label": _("Still open"), "fieldtype": "Small Text", "width": 420},
	]
	if completed:
		columns.append(
			{
				"fieldname": "status_reason",
				"label": _("Closing note"),
				"fieldtype": "Small Text",
				"width": 260,
			}
		)
		visit_filters = {"status": "Completed", "visit_date": [">=", add_days(nowdate(), -30)]}
	else:
		visit_filters = {"status": "Open", "creation": ["<", add_days(now_datetime(), -1)]}
	rows = []
	for v in frappe.get_all(
		"Patient Visit",
		filters=visit_filters,
		fields=[
			"name",
			"patient_name",
			"visit_date",
			"visit_type",
			"payment_method",
			"current_station",
			"status_reason",
		],
		order_by="visit_date asc",
		limit=LIMIT,
	):
		items = open_items(v.name)
		if completed and not items:
			continue
		rows.append({**v, "visit": v.name, "open_items": "; ".join(items) or _("nothing: close it")})
	return columns, rows


def notify_managers():
	"""Daily: tell the managers how many visits have been open more than a day."""
	count = frappe.db.count(
		"Patient Visit", {"status": "Open", "creation": ["<", add_days(now_datetime(), -1)]}
	)
	if not count:
		return
	users = frappe.get_all(
		"Has Role",
		filters={"role": "Healthcare Administrator", "parenttype": "User"},
		pluck="parent",
		distinct=True,
	)
	for user in users:
		if not frappe.db.get_value("User", user, "enabled"):
			continue
		frappe.get_doc(
			{
				"doctype": "Notification Log",
				"for_user": user,
				"type": "Alert",
				"document_type": "Report",
				"document_name": "Visits to Close",
				"subject": _("{0} visit(s) open for more than a day: see Visits to Close").format(count),
			}
		).insert(ignore_permissions=True)
