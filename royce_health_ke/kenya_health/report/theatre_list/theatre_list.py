# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""The day's theatre list: what is booked where, with whom, and whether
consent, checklist and anaesthesia record are in place."""

import frappe
from frappe import _
from frappe.utils import getdate


def execute(filters=None):
	filters = filters or {}
	day = getdate(filters.get("date"))
	conditions = {"scheduled_start": ["between", [f"{day} 00:00:00", f"{day} 23:59:59"]]}
	for field in ("company", "theatre", "surgeon"):
		if filters.get(field):
			conditions[field] = filters[field]
	bookings = frappe.get_all(
		"Theatre Booking",
		filters=conditions,
		fields=[
			"name",
			"scheduled_start",
			"scheduled_end",
			"theatre",
			"patient_name",
			"procedure_template",
			"priority",
			"surgeon",
			"anaesthetist",
			"status",
			"surgical_consent",
			"safety_checklist",
			"anaesthesia_record",
			"pre_authorisation",
		],
		order_by="theatre asc, scheduled_start asc",
	)
	for b in bookings:
		b.consent = (
			"Yes"
			if b.surgical_consent
			and frappe.db.get_value("Surgical Consent", b.surgical_consent, "docstatus") == 1
			else "No"
		)
		checklist = (
			frappe.db.get_value(
				"Surgical Safety Checklist",
				b.safety_checklist,
				["sign_in_status", "time_out_status", "sign_out_status"],
				as_dict=True,
			)
			if b.safety_checklist
			else None
		)
		b.checklist = (
			" / ".join(
				f"{label} {'done' if checklist and checklist[f] == 'Done' else '-'}"
				for f, label in (
					("sign_in_status", _("In")),
					("time_out_status", _("Out")),
					("sign_out_status", _("Off")),
				)
			)
			if checklist
			else _("Not started")
		)
		b.anaesthesia = "Yes" if b.anaesthesia_record else "No"
	columns = [
		{"fieldname": "scheduled_start", "label": _("Start"), "fieldtype": "Datetime", "width": 150},
		{
			"fieldname": "theatre",
			"label": _("Theatre"),
			"fieldtype": "Link",
			"options": "Healthcare Service Unit",
			"width": 140,
		},
		{
			"fieldname": "name",
			"label": _("Booking"),
			"fieldtype": "Link",
			"options": "Theatre Booking",
			"width": 130,
		},
		{"fieldname": "patient_name", "label": _("Patient"), "fieldtype": "Data", "width": 170},
		{"fieldname": "procedure_template", "label": _("Procedure"), "fieldtype": "Data", "width": 170},
		{"fieldname": "priority", "label": _("Priority"), "fieldtype": "Data", "width": 90},
		{
			"fieldname": "surgeon",
			"label": _("Surgeon"),
			"fieldtype": "Link",
			"options": "Healthcare Practitioner",
			"width": 130,
		},
		{
			"fieldname": "anaesthetist",
			"label": _("Anaesthetist"),
			"fieldtype": "Link",
			"options": "Healthcare Practitioner",
			"width": 130,
		},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 100},
		{"fieldname": "consent", "label": _("Consent"), "fieldtype": "Data", "width": 75},
		{"fieldname": "checklist", "label": _("WHO Checklist"), "fieldtype": "Data", "width": 170},
		{"fieldname": "anaesthesia", "label": _("Anaesthesia"), "fieldtype": "Data", "width": 90},
		{"fieldname": "pre_authorisation", "label": _("Pre-auth"), "fieldtype": "Data", "width": 100},
	]
	return columns, bookings
