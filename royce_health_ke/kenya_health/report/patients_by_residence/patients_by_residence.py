# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Where patients come from: per residence, the patients registered and the
patients seen (visits checked in) in the period, busiest first. Places with
few patients show where marketing could do more."""

import frappe
from frappe import _

NOT_RECORDED = "(not recorded)"


def execute(filters=None):
	filters = frappe._dict(filters or {})
	rows = data(filters)
	return columns(), rows, None, chart(rows)


def columns():
	return [
		{
			"fieldname": "residence",
			"label": _("Residence"),
			"fieldtype": "Link",
			"options": "Residence",
			"width": 220,
		},
		{"fieldname": "residence_type", "label": _("Type"), "fieldtype": "Data", "width": 90},
		{"fieldname": "county", "label": _("County"), "fieldtype": "Data", "width": 130},
		{"fieldname": "sub_county", "label": _("Sub-County"), "fieldtype": "Data", "width": 150},
		{"fieldname": "new_patients", "label": _("New Patients"), "fieldtype": "Int", "width": 120},
		{"fieldname": "patients_seen", "label": _("Patients Seen"), "fieldtype": "Int", "width": 120},
		{"fieldname": "visits", "label": _("Visits"), "fieldtype": "Int", "width": 90},
	]


def data(filters):
	period = {"from_date": filters.from_date, "to_date": filters.to_date, "company": filters.company}
	new = dict(
		frappe.db.sql(
			"""select ifnull(ke_residence, ''), count(*) from `tabPatient`
			where date(creation) between %(from_date)s and %(to_date)s group by 1""",
			period,
		)
	)
	company = "and v.company = %(company)s" if filters.company else ""
	seen = {
		r[0]: (r[1], r[2])
		for r in frappe.db.sql(
			f"""select ifnull(p.ke_residence, ''), count(distinct v.patient), count(*)
			from `tabPatient Visit` v join `tabPatient` p on p.name = v.patient
			where v.visit_date between %(from_date)s and %(to_date)s and v.status != 'Cancelled' {company}
			group by 1""",
			period,
		)
	}
	places = {
		r.name: r
		for r in frappe.get_all(
			"Residence", fields=["name", "residence_type", "county", "sub_county"], order_by="name"
		)
	}
	rows = []
	for name in set(new) | set(seen) | set(places):
		place = places.get(name) or frappe._dict()
		if filters.county and (place.county or "").lower() != filters.county.strip().lower():
			continue
		if filters.residence_type and place.residence_type != filters.residence_type:
			continue
		patients, visits = seen.get(name, (0, 0))
		rows.append(
			{
				"residence": name or None,
				"residence_type": place.residence_type,
				"county": place.county,
				"sub_county": place.sub_county,
				"new_patients": new.get(name, 0),
				"patients_seen": patients,
				"visits": visits,
			}
		)
		if not name:
			rows[-1]["residence_type"] = _(NOT_RECORDED)
	rows.sort(key=lambda r: (-r["patients_seen"], -r["new_patients"], r["residence"] or "~"))
	return rows


def chart(rows):
	top = [r for r in rows if r["residence"] and (r["patients_seen"] or r["new_patients"])][:15]
	if not top:
		return None
	return {
		"data": {
			"labels": [r["residence"] for r in top],
			"datasets": [
				{"name": _("Patients Seen"), "values": [r["patients_seen"] for r in top]},
				{"name": _("New Patients"), "values": [r["new_patients"] for r in top]},
			],
		},
		"type": "bar",
		"colors": ["#2490ef", "#9ccdf7"],
	}
