# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Procedures requested to Theatre (from the consultation or the ward) that
are not booked yet; Book opens a Theatre Booking filled from the request
(theatre.theatre_requests, theatre.from_request)."""

from frappe import _

from royce_health_ke.theatre import theatre_requests


def execute(filters=None):
	columns = [
		{"fieldname": "urgency", "label": _("Urgency"), "fieldtype": "Data", "width": 95},
		{"fieldname": "order_date", "label": _("Requested"), "fieldtype": "Date", "width": 100},
		{"fieldname": "order_time", "label": _("Time"), "fieldtype": "Time", "width": 80},
		{"fieldname": "patient_name", "label": _("Patient"), "fieldtype": "Data", "width": 180},
		{"fieldname": "location", "label": _("From"), "fieldtype": "Data", "width": 200},
		{"fieldname": "template_dn", "label": _("Procedure"), "fieldtype": "Data", "width": 190},
		{"fieldname": "practitioner_name", "label": _("Requested By"), "fieldtype": "Data", "width": 150},
		{"fieldname": "comment", "label": _("Doctor's Note"), "fieldtype": "Data", "width": 180},
		{"fieldname": "book", "label": _("Book"), "fieldtype": "Data", "width": 90},
		{
			"fieldname": "name",
			"label": _("Request"),
			"fieldtype": "Link",
			"options": "Service Request",
			"width": 130,
		},
	]
	return columns, theatre_requests()
