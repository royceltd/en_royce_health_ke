# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Site-data corrections for known Marley Health defects. Runs after install
and after every migrate; each fix only touches what is still broken, so a
hospital's own choices are never overwritten (ADR-023)."""

import json

import frappe

HISTORY_TABLES = ("Patient History Standard Document Type", "Patient History Custom Document Type")


def apply():
	fixed = fix_patient_history_field_types()
	if fixed:
		frappe.logger("royce_health_ke").info(f"marley_fixes: patient history field types corrected: {fixed}")


def fix_patient_history_field_types():
	"""Patient History Settings stores, per document type, the fields shown on
	the patient's timeline, each with its fieldtype. Marley v16 ships Lab Test's
	`lab_test_comment` (a Text field) as fieldtype "Table", so submitting any
	lab test with a comment crashes with "DocType None not found" - FOUND
	2026-11-05 on the hospital demo. Re-reads each entry's fieldtype from the
	doctype itself; which fields are selected is left alone."""
	fixed = []
	for table in HISTORY_TABLES:
		if not frappe.db.table_exists(table):
			continue
		for row in frappe.get_all(table, fields=["name", "document_type", "selected_fields"]):
			corrected = corrected_selected_fields(row.document_type, row.selected_fields)
			if corrected is not None:
				frappe.db.set_value(table, row.name, "selected_fields", corrected, update_modified=False)
				fixed.append(row.document_type)
	return fixed


def corrected_selected_fields(document_type, selected_fields):
	"""The JSON with each entry's fieldtype matched to the doctype, or None when
	nothing needs changing (or it can't be checked)."""
	if not selected_fields or not frappe.db.exists("DocType", document_type):
		return None
	try:
		entries = json.loads(selected_fields)
	except ValueError:
		return None
	meta = frappe.get_meta(document_type)
	changed = False
	for entry in entries:
		field = meta.get_field(entry.get("fieldname"))
		if field and entry.get("fieldtype") != field.fieldtype:
			entry["fieldtype"] = field.fieldtype
			changed = True
	return json.dumps(entries) if changed else None
