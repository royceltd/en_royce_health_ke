# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Flag vital signs recorded before v0.19 Normal / Abnormal, so the triage
list shows every row. Custom fields are created in after_migrate, which runs
after patches, so they are applied here first."""

import frappe

from royce_health_ke import vitals
from royce_health_ke.setup import custom_fields


def execute():
	custom_fields.apply()
	fields = ["name", "patient", "signs_date"] + [f for f, _l, _u in vitals.READINGS]
	dobs = {}
	for row in frappe.get_all("Vital Signs", filters={"ke_vitals_status": ["in", ["", None]]}, fields=fields):
		if row.patient not in dobs:
			dobs[row.patient] = frappe.db.get_value("Patient", row.patient, "dob")
		if not any(vitals._number(row.get(f)) for f, _l, _u in vitals.READINGS):
			continue
		flags = vitals.abnormal_readings(row, vitals.age_in_years(dobs[row.patient], row.signs_date))
		frappe.db.set_value(
			"Vital Signs",
			row.name,
			{
				"ke_vitals_status": "Abnormal" if flags else "Normal",
				"ke_vitals_flags": "\n".join(text for _f, text in flags),
				"ke_abnormal_fields": ",".join(f for f, _t in flags),
			},
			update_modified=False,
		)
