# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""What the Receptionist role needs to check patients in: choose the service
type, practitioner, department and insurer, record the patient's insurance
policy, and see appointments. Marley gives none of these to a reception role.

Each version of these defaults is applied once per site (Kenya Health
Settings keeps the version), and only adds a Receptionist rule where the
document type has none; afterwards permissions are the hospital's to change
in Role Permissions Manager (ADR-023)."""

import frappe

from royce_health_ke.privacy import RECEPTIONIST, ensure_role

VERSION = 1

READ = ("read", "select", "report")
RECEPTIONIST_ACCESS = {
	"Appointment Type": READ,
	"Healthcare Practitioner": READ,
	"Medical Department": READ,
	"Insurance Payor": READ,
	"Insurance Payor Eligibility Plan": READ,
	"Healthcare Service Unit": READ,
	"Patient Insurance Policy": (*READ, "write", "create", "submit", "print"),
	"Patient Appointment": (*READ, "write", "create", "print"),
}


def apply_defaults():
	done = frappe.db.get_single_value("Kenya Health Settings", "role_defaults_version") or 0
	if done >= VERSION:
		return
	from frappe.permissions import add_permission, update_permission_property

	ensure_role(RECEPTIONIST)
	for doctype, ptypes in RECEPTIONIST_ACCESS.items():
		if not frappe.db.exists("DocType", doctype):
			continue
		if frappe.db.exists("Custom DocPerm", {"parent": doctype, "role": RECEPTIONIST, "permlevel": 0}):
			continue
		add_permission(doctype, RECEPTIONIST, 0)
		for ptype in ptypes:
			update_permission_property(doctype, RECEPTIONIST, 0, ptype, 1, validate=False)
	frappe.db.set_single_value("Kenya Health Settings", "role_defaults_version", VERSION)
	frappe.clear_cache()
