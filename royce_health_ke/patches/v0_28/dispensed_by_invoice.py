# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Prescriptions already issued by a bill with Update Stock (before the
pharmacy worklist) count as dispensed, so they don't wait on the worklist.
Custom fields are created in after_migrate, which runs after patches, so they
are applied here first."""

import frappe

from royce_health_ke import pharmacy
from royce_health_ke.setup import custom_fields


def execute():
	custom_fields.apply()
	for mr in frappe.get_all(
		"Sales Invoice Item",
		filters={"reference_dt": "Medication Request", "docstatus": 1},
		pluck="reference_dn",
		distinct=True,
	):
		if frappe.db.exists("Medication Request", mr):
			pharmacy.refresh_dispensed(mr)
