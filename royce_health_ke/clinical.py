# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Allied clinical services a clinician orders from the consultation:
physiotherapy, occupational therapy, counselling and medical social work.

They are Marley Therapy Types: the clinician adds them on the consultation's
Therapies table (order entry), Marley makes a Therapy Plan, and each visit to
the therapist / counsellor / social worker is a Therapy Session, with the
session notes on it. Longer write-ups (a social work assessment, a counselling
record) are Clinical Notes of the matching type on the patient's record.

Marley creates a billing Item for every Therapy Type, so the types are added
by an explicit action (Kenya Health Settings > Add Therapy and Counselling
Services), never by a migrate; the hospital then sets each one's price and
whether it is billed (ADR-023). Clinical Note Types create nothing billable
and are added on migrate."""

import frappe
from frappe import _

SERVICES = (
	# therapy type, item code, description
	("Physiotherapy", "THERAPY-PHYSIO", "Physiotherapy session"),
	("Occupational Therapy", "THERAPY-OT", "Occupational therapy session"),
	("Counselling", "THERAPY-COUNSEL", "Counselling session (psychosocial, HIV, adherence, ...)"),
	(
		"Medical Social Work",
		"THERAPY-SOCIAL",
		"Medical social work: assessment, support, waiver and referral",
	),
)

NOTE_TYPES = (
	"Social Work Assessment",
	"Counselling Session",
	"Occupational Therapy Note",
	"Physiotherapy Note",
)


def ensure_note_types():
	for name in NOTE_TYPES:
		if not frappe.db.exists("Clinical Note Type", name):
			frappe.get_doc({"doctype": "Clinical Note Type", "clinical_note_type": name}).insert(
				ignore_permissions=True
			)


@frappe.whitelist()
def setup_services():
	"""Create the therapy types the hospital doesn't have yet (not billed until
	the hospital sets a price and ticks Is Billable). Returns what was created."""
	frappe.only_for(("System Manager", "Healthcare Administrator"))
	ensure_note_types()
	group = "Services" if frappe.db.exists("Item Group", "Services") else "All Item Groups"
	created = []
	for name, item_code, description in SERVICES:
		if frappe.db.exists("Therapy Type", name) or frappe.db.exists("Item", item_code):
			continue
		frappe.get_doc(
			{
				"doctype": "Therapy Type",
				"therapy_type": name,
				"item_code": item_code,
				"item_name": name,
				"item_group": group,
				"description": description,
				"default_duration": 30,
				"is_billable": 0,
			}
		).insert(ignore_permissions=True)
		created.append(name)
	if created:
		frappe.msgprint(
			_("Added: {0}. Set each one's price and tick Is Billable on the Therapy Type to bill it.").format(
				", ".join(created)
			)
		)
	else:
		frappe.msgprint(_("All therapy and counselling services already exist."))
	return created
