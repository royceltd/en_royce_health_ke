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

VERSION = 2

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

# v2: the Cashier takes patients' payments (see cashier.py) and needs only
# billing; give accountants their usual roles as well.
CASHIER_ACCESS = {
	"Sales Invoice": (*READ, "write", "create", "submit", "print", "email"),
	"Payment Entry": (*READ, "write", "create", "submit", "print", "email"),
	"Customer": READ,
	"Patient": READ,
	"Mode of Payment": READ,
	"Account": READ,
	"Cost Center": READ,
	"Company": READ,
	"Currency": READ,
	"Price List": READ,
	"Item": READ,
	"Healthcare Practitioner": READ,
	"Patient Insurance Policy": READ,
	"Insurance Payor": READ,
}


def apply_defaults():
	done = frappe.db.get_single_value("Kenya Health Settings", "role_defaults_version") or 0
	if done >= VERSION:
		return
	from frappe.permissions import add_permission, update_permission_property

	from royce_health_ke.cashier import CASHIER

	for role, access in ((RECEPTIONIST, RECEPTIONIST_ACCESS), (CASHIER, CASHIER_ACCESS)):
		ensure_role(role)
		for doctype, ptypes in access.items():
			if not frappe.db.exists("DocType", doctype):
				continue
			if frappe.db.exists("Custom DocPerm", {"parent": doctype, "role": role, "permlevel": 0}):
				continue
			add_permission(doctype, role, 0)
			for ptype in ptypes:
				update_permission_property(doctype, role, 0, ptype, 1, validate=False)
	frappe.db.set_single_value("Kenya Health Settings", "role_defaults_version", VERSION)
	frappe.clear_cache()
