# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Turnaround time of lab tests and imaging, from order to result: per test
type (median, average, 90th percentile, share within target), or each
request with its steps. See royce_health_ke.tat."""

import frappe
from frappe import _

from royce_health_ke import tat


def execute(filters=None):
	f = frappe._dict(filters or {})
	template = (f.template or "").strip() or None
	rows = []
	if f.department in (None, "", "Laboratory"):
		rows += tat.lab_rows(f.from_date, f.to_date, f.company, template)
	if f.department in (None, "", "Radiology"):
		rows += tat.imaging_rows(f.from_date, f.to_date, f.company, template)
	rows = [tat.with_minutes(r) for r in rows]
	note = None
	if any(r["approximate"] for r in rows):
		note = _(
			"Lab tests resulted before the result time was recorded (v0.22) use their last change as the result time: those times are approximate."
		)
	if f.each_request:
		rows.sort(key=lambda r: r["result_at"], reverse=True)
		return detail_columns(), rows, note
	summary = tat.summarise(rows)
	return summary_columns(), summary, note, chart(summary)


def summary_columns():
	return [
		{"fieldname": "department", "label": _("Department"), "fieldtype": "Data", "width": 110},
		{"fieldname": "test", "label": _("Test or Exam"), "fieldtype": "Data", "width": 220},
		{"fieldname": "count", "label": _("Done"), "fieldtype": "Int", "width": 70},
		{
			"fieldname": "median_minutes",
			"label": _("Median (min)"),
			"fieldtype": "Float",
			"precision": 0,
			"width": 110,
		},
		{"fieldname": "average_minutes", "label": _("Average (min)"), "fieldtype": "Int", "width": 110},
		{"fieldname": "p90_minutes", "label": _("90% within (min)"), "fieldtype": "Int", "width": 130},
		{"fieldname": "target", "label": _("Target (min)"), "fieldtype": "Int", "width": 100},
		{
			"fieldname": "within_target_pct",
			"label": _("Within Target %"),
			"fieldtype": "Percent",
			"width": 120,
		},
	]


def detail_columns():
	return [
		{"fieldname": "department", "label": _("Department"), "fieldtype": "Data", "width": 100},
		{"fieldname": "test", "label": _("Test or Exam"), "fieldtype": "Data", "width": 180},
		{"fieldname": "record_type", "label": _("Type"), "fieldtype": "Data", "hidden": 1},
		{
			"fieldname": "record",
			"label": _("Record"),
			"fieldtype": "Dynamic Link",
			"options": "record_type",
			"width": 150,
		},
		{"fieldname": "patient_name", "label": _("Patient"), "fieldtype": "Data", "width": 160},
		{"fieldname": "ordered_at", "label": _("Ordered"), "fieldtype": "Datetime", "width": 150},
		{"fieldname": "collected_at", "label": _("Sample Collected"), "fieldtype": "Datetime", "width": 150},
		{
			"fieldname": "started_at",
			"label": _("Received / Performed"),
			"fieldtype": "Datetime",
			"width": 150,
		},
		{"fieldname": "result_at", "label": _("Result"), "fieldtype": "Datetime", "width": 150},
		{"fieldname": "wait_minutes", "label": _("Waiting (min)"), "fieldtype": "Int", "width": 100},
		{
			"fieldname": "work_minutes",
			"label": _("In Lab / Radiology (min)"),
			"fieldtype": "Int",
			"width": 120,
		},
		{"fieldname": "total_minutes", "label": _("Order to Result (min)"), "fieldtype": "Int", "width": 130},
		{"fieldname": "target", "label": _("Target (min)"), "fieldtype": "Int", "width": 90},
		{"fieldname": "within_target", "label": _("Within Target"), "fieldtype": "Data", "width": 100},
		{"fieldname": "approximate", "label": _("Approx."), "fieldtype": "Check", "width": 70},
	]


def chart(summary):
	top = summary[:15]
	if not top:
		return None
	return {
		"data": {
			"labels": [r["test"] for r in top],
			"datasets": [
				{"name": _("Median minutes, order to result"), "values": [r["median_minutes"] for r in top]}
			],
		},
		"type": "bar",
		"colors": ["#2490ef"],
	}
