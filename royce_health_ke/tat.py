# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Turnaround time (TAT) for lab tests and imaging: when each step happened,
for the Turnaround Time report.

Lab test: ordered (its Service Request, or the lab test itself for a walk-in)
-> sample collected (Sample Collection) -> received (lab test created) ->
result (ke_result_at, stamped here on submit). Marley keeps the submit date
without a time, so lab tests resulted before v0.22 use their last change
instead, marked approximate.

Imaging: ordered (Service Request) -> performed (ke_performed_at) ->
reported (ke_reported_at), stamped by radiology.py."""

import statistics

import frappe
from frappe.utils import get_datetime, now_datetime, time_diff_in_seconds


def lab_test_submitted(doc, method=None):
	"""Lab Test on_submit."""
	if not doc.get("ke_result_at"):
		doc.db_set("ke_result_at", now_datetime(), update_modified=False)


def minutes(start, end):
	if not (start and end):
		return None
	value = round(time_diff_in_seconds(get_datetime(end), get_datetime(start)) / 60)
	return value if value >= 0 else None  # steps recorded out of order


def _ordered_at(request, fallback, started=None):
	"""The order's stated date and time; when that is after the work began
	(typed in later, or back-dated records), when the order was entered."""
	if request:
		r = frappe.db.get_value(
			"Service Request", request, ["order_date", "order_time", "creation"], as_dict=True
		)
		if r:
			if r.order_date and r.order_time:
				stated = get_datetime(f"{r.order_date} {r.order_time}")
				if not started or stated <= get_datetime(started):
					return stated
			return get_datetime(r.creation)
	return get_datetime(fallback)


def lab_rows(from_date, to_date, company=None, template=None):
	filters = {"docstatus": 1}
	if company:
		filters["company"] = company
	if template:
		filters["template"] = template
	tests = frappe.get_all(
		"Lab Test",
		filters=filters,
		fields=[
			"name",
			"patient_name",
			"template",
			"lab_test_name",
			"service_request",
			"sample",
			"creation",
			"modified",
			"ke_result_at",
		],
	)
	targets = dict(
		frappe.get_all("Lab Test Template", fields=["name", "ke_target_tat_minutes"], as_list=True)
	)
	rows = []
	start, end = get_datetime(f"{from_date} 00:00:00"), get_datetime(f"{to_date} 23:59:59")
	for t in tests:
		result = t.ke_result_at or t.modified
		if not (start <= get_datetime(result) <= end):
			continue
		ordered = _ordered_at(t.service_request, t.creation, t.creation)
		collected = t.sample and frappe.db.get_value("Sample Collection", t.sample, "collected_time")
		rows.append(
			{
				"department": "Laboratory",
				"test": t.lab_test_name or t.template,
				"template": t.template,
				"record_type": "Lab Test",
				"record": t.name,
				"patient_name": t.patient_name,
				"ordered_at": ordered,
				"collected_at": collected,
				"started_at": t.creation,
				"result_at": result,
				"approximate": 0 if t.ke_result_at else 1,
				"target": targets.get(t.template) or None,
			}
		)
	return rows


def imaging_rows(from_date, to_date, company=None, template=None):
	if not frappe.get_meta("Observation").has_field("ke_reported_at"):
		return []
	filters = {
		"ke_reported_at": ["between", [f"{from_date} 00:00:00", f"{to_date} 23:59:59"]],
	}
	if company:
		filters["company"] = company
	if template:
		filters["observation_template"] = template
	exams = frappe.get_all(
		"Observation",
		filters=filters,
		fields=[
			"name",
			"patient_name",
			"observation_template",
			"service_request",
			"creation",
			"ke_performed_at",
			"ke_reported_at",
		],
	)
	targets = dict(
		frappe.get_all(
			"Observation Template",
			filters={"observation_category": "Imaging"},
			fields=["name", "ke_target_tat_minutes"],
			as_list=True,
		)
	)
	return [
		{
			"department": "Radiology",
			"test": e.observation_template,
			"template": e.observation_template,
			"record_type": "Observation",
			"record": e.name,
			"patient_name": e.patient_name,
			"ordered_at": _ordered_at(e.service_request, e.creation, e.ke_performed_at or e.ke_reported_at),
			"collected_at": None,
			"started_at": e.ke_performed_at,
			"result_at": e.ke_reported_at,
			"approximate": 0,
			"target": targets.get(e.observation_template) or None,
		}
		for e in exams
		if e.observation_template in targets
	]


def with_minutes(row):
	row["total_minutes"] = minutes(row["ordered_at"], row["result_at"])
	row["wait_minutes"] = minutes(row["ordered_at"], row["started_at"])
	row["work_minutes"] = minutes(row["started_at"], row["result_at"])
	target = row.get("target")
	row["within_target"] = (
		""
		if not target or row["total_minutes"] is None
		else ("Yes" if row["total_minutes"] <= target else "No")
	)
	return row


def summarise(rows):
	"""Per test: count, median, average and 90th percentile of order-to-result
	minutes, and the share within target."""
	by_test = {}
	for r in rows:
		if r["total_minutes"] is not None:
			by_test.setdefault((r["department"], r["test"]), []).append(r)
	out = []
	for (department, test), group in by_test.items():
		times = sorted(r["total_minutes"] for r in group)
		judged = [r for r in group if r["within_target"]]
		out.append(
			{
				"department": department,
				"test": test,
				"count": len(times),
				"median_minutes": statistics.median(times),
				"average_minutes": round(sum(times) / len(times)),
				"p90_minutes": times[min(len(times) - 1, round(0.9 * (len(times) - 1)))],
				"target": group[0].get("target"),
				"within_target_pct": (
					round(100 * sum(1 for r in judged if r["within_target"] == "Yes") / len(judged))
					if judged
					else None
				),
				"approximate": 1 if any(r["approximate"] for r in group) else 0,
			}
		)
	out.sort(key=lambda r: (r["department"], -r["median_minutes"]))
	return out
