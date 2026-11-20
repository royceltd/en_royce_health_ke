# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Patients served per payment mode, for the day's work (Bethesda, 20 Nov
2026): Cash 30, SHA - PHC 10, SHA - MWALIMU 2. A visit paid by insurance is
counted under its scheme (insurance plan), else its insurer; a cancelled
visit is not counted."""

import frappe
from frappe import _
from frappe.utils import getdate, nowdate

CASH = _("Cash")


def mode(visit):
	if visit.payment_method == "Insurance":
		return visit.insurance_plan or visit.insurance_payor or _("Insurance (no insurer)")
	return visit.payment_method or CASH


def rows(filters):
	from_date = getdate(filters.get("from_date") or nowdate())
	to_date = getdate(filters.get("to_date") or from_date)
	conditions = {"visit_date": ["between", [from_date, to_date]], "status": ["!=", "Cancelled"]}
	for field in ("company", "visit_type"):
		if filters.get(field):
			conditions[field] = filters[field]
	visits = frappe.get_all(
		"Patient Visit",
		filters=conditions,
		fields=["name", "patient", "payment_method", "insurance_payor", "insurance_plan"],
	)
	counts = {}
	for v in visits:
		c = counts.setdefault(mode(v), {"visits": 0, "patients": set()})
		c["visits"] += 1
		c["patients"].add(v.patient)
	order = sorted(counts, key=lambda m: (m != CASH, -counts[m]["visits"], m))
	total = sum(c["visits"] for c in counts.values()) or 1
	return [
		{
			"payment_mode": m,
			"visits": counts[m]["visits"],
			"patients": len(counts[m]["patients"]),
			"share": round(100.0 * counts[m]["visits"] / total, 1),
		}
		for m in order
	]


def execute(filters=None):
	filters = filters or {}
	columns = [
		{"fieldname": "payment_mode", "label": _("Payment Mode"), "fieldtype": "Data", "width": 260},
		{"fieldname": "visits", "label": _("Visits"), "fieldtype": "Int", "width": 100},
		{"fieldname": "patients", "label": _("Patients"), "fieldtype": "Int", "width": 100},
		{"fieldname": "share", "label": _("Share (%)"), "fieldtype": "Percent", "width": 100},
	]
	data = rows(filters)
	chart = (
		{
			"data": {
				"labels": [r["payment_mode"] for r in data],
				"datasets": [{"name": _("Visits"), "values": [r["visits"] for r in data]}],
			},
			"type": "bar",
		}
		if data
		else None
	)
	return columns, data, None, chart
