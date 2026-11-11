# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""The patient's medical history in the consultation: the consultation shows
the patient's allergies, medication, medical, surgical, family and social
history (fetched when the patient is chosen) and the clinician can edit them
there. What changed is saved back to the patient's record, with a note on
the patient naming the consultation, so the next clinician sees it."""

import frappe
from frappe import _

# consultation field -> patient field
HISTORY = {
	"ke_hx_allergies": "allergies",
	"ke_hx_medication": "medication",
	"ke_hx_medical": "medical_history",
	"ke_hx_surgical": "surgical_history",
	"ke_hx_family": "ke_family_history",
	"ke_hx_social": "ke_social_history",
}


def _clean(value):
	return (value or "").strip()


def save_history_to_patient(doc, method=None):
	"""Patient Encounter on_update / on_submit."""
	if not doc.get("patient") or doc.docstatus == 2:
		return
	meta = frappe.get_meta("Patient")
	fields = {e: p for e, p in HISTORY.items() if doc.meta.has_field(e) and meta.has_field(p)}
	if not fields:
		return
	current = frappe.db.get_value("Patient", doc.patient, list(fields.values()), as_dict=True) or {}
	changes = {
		p: _clean(doc.get(e))
		for e, p in fields.items()
		if doc.get(e) is not None and _clean(doc.get(e)) != _clean(current.get(p))
	}
	if not changes:
		return
	frappe.db.set_value("Patient", doc.patient, changes)
	labels = ", ".join(_(meta.get_label(p)) for p in changes)
	frappe.get_doc(
		{
			"doctype": "Comment",
			"comment_type": "Info",
			"reference_doctype": "Patient",
			"reference_name": doc.patient,
			"content": _("{0} updated from consultation {1}").format(labels, doc.name),
		}
	).insert(ignore_permissions=True)
