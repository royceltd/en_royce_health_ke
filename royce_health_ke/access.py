# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Who opened which patient record: a Patient Record Access entry each time a
user opens (desk form load) or prints a record that belongs to a patient.

- Tracked records: the Patient and the clinical records that carry a
  `patient` field (TRACKED). Billing documents aren't tracked.
- A user re-opening the same record within REPEAT_MINUTES isn't logged
  again (a form refresh is not a new look); every print is logged.
- Written after the response is sent, as Frappe writes its own View Log, so
  opening a record is never slowed or blocked by the log.
- Entries can't be changed or deleted, and aren't cleared by Frappe's log
  cleanup. What isn't covered: lists and reports that show patient data
  without opening a record."""

import frappe
from frappe.database.utils import commit_after_response
from frappe.utils import now_datetime

REPEAT_MINUTES = 10
TRACKED = (
	"Patient",
	# Marley
	"Patient Encounter",
	"Vital Signs",
	"Lab Test",
	"Sample Collection",
	"Observation",
	"Diagnostic Report",
	"Clinical Procedure",
	"Inpatient Record",
	"Inpatient Medication Order",
	"Discharge Summary",
	"Emergency Record",
	"Medication Request",
	"Service Request",
	"Patient Medical Record",
	"Nursing Care Plan",
	"Intake Output Entry",
	"Therapy Session",
	"Therapy Plan",
	"Patient Assessment",
	# Kenya Health
	"Pregnancy Record",
	"ANC Visit",
	"Delivery Record",
	"PNC Visit",
	"Family Planning Visit",
	"Theatre Booking",
	"Surgical Consent",
	"Surgical Safety Checklist",
	"Anaesthesia Record",
	"Treatment Sheet",
	"Diet Order",
	"Insurance Claim",
)


def enabled():
	value = frappe.db.get_single_value("Kenya Health Settings", "track_record_access")
	return value is None or bool(value)


def patient_of(doc):
	if doc.doctype == "Patient":
		return doc.name, doc.get("patient_name")
	if doc.get("patient"):
		return doc.patient, doc.get("patient_name") or frappe.db.get_value(
			"Patient", doc.patient, "patient_name"
		)
	return None, None


def log_view(doc, method=None):
	"""doc_events onload (every desk form load)."""
	_log(doc, "View")


def log_print(doc, method=None, *args, **kwargs):
	"""doc_events before_print."""
	_log(doc, "Print")


def _log(doc, action):
	if doc.doctype not in TRACKED or doc.is_new() or frappe.session.user == "Guest":
		return
	try:
		if not enabled():
			return
		patient, patient_name = patient_of(doc)
		if not patient:
			return
		user = frappe.session.user
		if action == "View":
			# marked in the cache at once: the entry itself is written after the
			# response, too late for a second load a moment later to see it
			key = f"royce_health_ke:record_access:{user}:{doc.doctype}:{doc.name}"
			if frappe.cache.get_value(key):
				return
			frappe.cache.set_value(key, 1, expires_in_sec=REPEAT_MINUTES * 60)
		entry = frappe.get_doc(
			{
				"doctype": "Patient Record Access",
				"patient": patient,
				"patient_name": patient_name,
				"reference_doctype": doc.doctype,
				"reference_name": doc.name,
				"action": action,
				"user": user,
				"full_name": frappe.utils.get_fullname(user),
				"ip_address": getattr(frappe.local, "request_ip", None),
				"accessed_at": now_datetime(),
			}
		)
	except Exception:
		# never stop a clinician opening a record because the audit failed
		frappe.log_error(
			title="Patient Record Access not logged", reference_doctype=doc.doctype, reference_name=doc.name
		)
		return
	if frappe.flags.read_only:
		entry.deferred_insert()
	else:
		commit_after_response(lambda: entry.insert(ignore_permissions=True))
