# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Imaging exams to do and to report: STAT first, then oldest first."""

import frappe
from frappe import _
from frappe.utils import now_datetime, time_diff_in_hours

PRIORITY = {"STAT": 0, "Urgent": 1, "Routine": 2}


def execute(filters=None):
	filters = filters or {}
	conditions = {
		"observation_category": "Imaging",
		"docstatus": ["!=", 2],
		"parent_observation": ["in", ["", None]],
	}
	statuses = filters.get("exam_status") or "Open"
	if statuses == "Open":
		conditions["ke_exam_status"] = ["in", ["Requested", "Performed", "Reported"]]
	elif statuses != "All":
		conditions["ke_exam_status"] = statuses
	for field, key in (("company", "company"), ("ke_modality", "modality")):
		if filters.get(key):
			conditions[field] = filters[key]
	rows = frappe.get_all(
		"Observation",
		filters=conditions,
		fields=[
			"name",
			"ke_accession_number",
			"creation",
			"patient_name",
			"observation_template",
			"ke_modality",
			"ke_priority",
			"ke_exam_status",
			"healthcare_practitioner",
			"ke_radiographer",
			"ke_reported_by",
		],
	)
	now = now_datetime()
	for r in rows:
		r.waiting_hours = round(time_diff_in_hours(now, r.creation), 1)
	rows.sort(key=lambda r: (PRIORITY.get(r.ke_priority, 3), r.creation))
	columns = [
		{"fieldname": "ke_accession_number", "label": _("Accession"), "fieldtype": "Data", "width": 150},
		{
			"fieldname": "name",
			"label": _("Observation"),
			"fieldtype": "Link",
			"options": "Observation",
			"width": 140,
		},
		{"fieldname": "ke_priority", "label": _("Priority"), "fieldtype": "Data", "width": 80},
		{"fieldname": "patient_name", "label": _("Patient"), "fieldtype": "Data", "width": 170},
		{"fieldname": "observation_template", "label": _("Exam"), "fieldtype": "Data", "width": 170},
		{"fieldname": "ke_modality", "label": _("Modality"), "fieldtype": "Data", "width": 100},
		{"fieldname": "ke_exam_status", "label": _("Status"), "fieldtype": "Data", "width": 100},
		{"fieldname": "waiting_hours", "label": _("Waiting (h)"), "fieldtype": "Float", "width": 90},
		{
			"fieldname": "healthcare_practitioner",
			"label": _("Requested By"),
			"fieldtype": "Link",
			"options": "Healthcare Practitioner",
			"width": 130,
		},
		{"fieldname": "ke_radiographer", "label": _("Radiographer"), "fieldtype": "Data", "width": 120},
		{
			"fieldname": "ke_reported_by",
			"label": _("Reported By"),
			"fieldtype": "Link",
			"options": "Healthcare Practitioner",
			"width": 130,
		},
	]
	return columns, rows
