# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Data minimisation (Data Protection Act): patients' phone numbers, email
and ID numbers are masked (shown as XXXXXXXX) for staff who don't need them -
clinical, lab and pharmacy staff - and shown in full to reception, records
and administrators. Lists show only what is needed to pick the right patient.

Uses Frappe's own field masking: a field marked "Mask" is masked in lists,
reports and forms for every role without the "Mask" permission on that
document type. Server code (SMS, prints, claims) still reads the real value.

Applied once per site, then the hospital owns it (ADR-023): change who sees
what in Role Permissions Manager (the Mask column) and which fields in
Customize Form (the Mask checkbox)."""

import frappe

RECEPTIONIST = "Receptionist"
# Roles that see the full details.
UNMASKED_ROLES = ("System Manager", "Healthcare Administrator", RECEPTIONIST)

MASKED_FIELDS = {
	"Patient": ("mobile", "phone", "email", "ke_id_number", "uid", "ke_nok_phone"),
	# Copies of the patient's contact details on other records.
	"Inpatient Record": ("mobile", "phone", "email"),
	"Lab Test": ("mobile", "email"),
}

# Patient list: name, sex and status are enough to pick the right patient.
HIDDEN_LIST_COLUMNS = {"Patient": ("mobile", "email")}

FULL_ACCESS = ("read", "write", "create", "print", "report", "email", "share", "export")


def apply_defaults():
	"""Once per site; afterwards the hospital's own permission choices stand."""
	if frappe.db.get_single_value("Kenya Health Settings", "privacy_defaults_applied"):
		return
	ensure_role(RECEPTIONIST)
	for doctype, fields in MASKED_FIELDS.items():
		if not frappe.db.exists("DocType", doctype):
			continue
		meta = frappe.get_meta(doctype)
		for fieldname in fields:
			if meta.has_field(fieldname):
				_property(doctype, fieldname, "mask", 1, "Check")
		_grant_unmasked(doctype)
	for doctype, fields in HIDDEN_LIST_COLUMNS.items():
		for fieldname in fields:
			_property(doctype, fieldname, "in_list_view", 0, "Check")
	frappe.db.set_single_value("Kenya Health Settings", "privacy_defaults_applied", 1)
	frappe.clear_cache()


def ensure_role(role):
	if not frappe.db.exists("Role", role):
		frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(
			ignore_permissions=True
		)


def _property(doctype, fieldname, prop, value, property_type):
	if frappe.db.exists("Property Setter", {"doc_type": doctype, "field_name": fieldname, "property": prop}):
		return
	frappe.make_property_setter(
		{
			"doctype": doctype,
			"fieldname": fieldname,
			"property": prop,
			"value": value,
			"property_type": property_type,
		},
		validate_fields_for_doctype=False,
	)


def _grant_unmasked(doctype):
	"""Mask permission (level 0) for the unmasked roles. Reception also gets to
	register and edit patients; the other roles only where they already have
	access, except the Healthcare Administrator on Patient."""
	from frappe.permissions import add_permission, setup_custom_perms, update_permission_property

	setup_custom_perms(doctype)
	for role in UNMASKED_ROLES:
		exists = frappe.db.exists("Custom DocPerm", {"parent": doctype, "role": role, "permlevel": 0})
		if not exists:
			if doctype != "Patient":
				continue
			add_permission(doctype, role, 0)
			for ptype in FULL_ACCESS:
				update_permission_property(doctype, role, 0, ptype, 1, validate=False)
		update_permission_property(doctype, role, 0, "mask", 1, validate=False)
