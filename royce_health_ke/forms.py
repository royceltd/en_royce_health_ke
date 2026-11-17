# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Fields taken off Marley's outpatient forms because they are recorded once,
elsewhere (hospital feedback on the outpatient flow, November 2026):

- Patient: one contact number. Mobile stays; Phone is hidden (identity.py
  still accepts either, for records that only have Phone).
- Patient Encounter: symptoms, appointment type and source are captured at
  reception (the visit's Service Type fills the consultation's appointment
  type, visits.link_encounter), so the doctor does not see them.
- Vital Signs: height is taken in centimetres (ke_height_cm); Marley's Height
  in metres is worked out from it and hidden.
- Sales Invoice payments: the Reference No (M-Pesa or card code) is a column
  of the payments table, where the cashier types it (cashier.py requires it).
- Consultation lab requests (Lab Prescription): Marley lists only its
  Observation column, so doctors ordered haemograms and vitals as
  Observations, which no department picks up (IT demo, 17 Nov 2026). The
  Lab Test column is listed and named "Lab Test", the Observation column is
  named "Imaging" (consultation.check_lab_rows refuses anything else there).
- Patient: "Invite as User" (a patient portal login) starts unticked.

Each property is set only where the hospital has not set it itself, so a
field shown again with Customize Form stays shown (ADR-023)."""

import frappe

HIDDEN = {
	"Patient": ("phone",),
	"Patient Encounter": ("symptoms", "symptoms_in_print", "appointment_type", "sb_source", "source"),
	"Vital Signs": ("height",),
}
# Hidden fields a hospital can't fill in must not be mandatory either.
NOT_REQUIRED = {"Patient Encounter": ("appointment_type",)}
NOT_IN_LIST = {"Vital Signs": ("height",)}
IN_LIST = {"Sales Invoice Payment": ("reference_no",), "Lab Prescription": ("lab_test_code",)}
LABELS = {"Lab Prescription": {"lab_test_code": "Lab Test", "observation_template": "Imaging"}}
DEFAULTS = {"Patient": {"invite_user": "0"}}


def apply():
	# Optional before hidden: Frappe refuses a hidden field that is still
	# mandatory (it failed installing on a fresh site, found by CI).
	for prop, fields, value in (
		("reqd", NOT_REQUIRED, "0"),
		("hidden", HIDDEN, "1"),
		("in_list_view", NOT_IN_LIST, "0"),
		("in_list_view", IN_LIST, "1"),
	):
		for doctype, fieldnames in fields.items():
			for fieldname in fieldnames:
				_set_once(doctype, fieldname, prop, value)
	for prop, fields, kind in (("label", LABELS, "Data"), ("default", DEFAULTS, "Text")):
		for doctype, values in fields.items():
			for fieldname, value in values.items():
				_set_once(doctype, fieldname, prop, value, kind)


def _set_once(doctype, fieldname, prop, value, property_type="Check"):
	if frappe.db.exists("Property Setter", {"doc_type": doctype, "field_name": fieldname, "property": prop}):
		return
	frappe.make_property_setter(
		{
			"doctype": doctype,
			"doctype_or_field": "DocField",
			"fieldname": fieldname,
			"property": prop,
			"value": value,
			"property_type": property_type,
		},
		is_system_generated=False,
	)
