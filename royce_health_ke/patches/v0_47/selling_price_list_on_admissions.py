# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Open admissions with a buying price list (Marley's Admit dialog offers any
list) couldn't charge their beds, and the patient's visit bill failed with
them. Cleared: Marley then prices from the selling price list."""

import frappe


def execute():
	buying = frappe.get_all("Price List", filters={"selling": 0}, pluck="name")
	if not buying:
		return
	for name in frappe.get_all(
		"Inpatient Record",
		filters={"price_list": ["in", buying], "status": ["not in", ("Discharged", "Cancelled")]},
		pluck="name",
	):
		frappe.db.set_value("Inpatient Record", name, "price_list", None, update_modified=False)
