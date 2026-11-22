# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Casualty (Bethesda, PDF (12) points 6-7, 19 Nov 2026): after triage the
patient goes to casualty, where they are managed from arrival through
treatment to discharge or admission to a ward.

A casualty stay is a short stay on a Casualty Unit: a ward (group Healthcare
Service Unit) ticked "Casualty Unit", with its beds. It is an Inpatient Record
marked ke_casualty, so every tab of the ward's patient screen works for it,
with the Casualty tab set (Patient Workspace Profile "Casualty": Casualty
Drugs, Care Plan, ...). What is data, the hospital's: which units are casualty,
the tabs, and the bed's charge (its Healthcare Service Unit Type: per hour,
per day, or none).

- Sent to Casualty (Send To from triage, or a Casualty visit at check-in):
  the patient waits on the Casualty list; a nurse gives a bed and their
  screen opens.
- Admit to a ward: the screen's Transfer to Ward; once the ward takes the
  patient, the stay is an admission (ke_casualty cleared).
- Discharge: as from a ward.
- Not an admission: casualty stays are left out of MOH 717 admissions and
  discharges, inpatient deaths and bed occupancy."""

import frappe
from frappe import _
from frappe.utils import now_datetime, nowdate

IR = "Inpatient Record"
UNIT = "Healthcare Service Unit"
STATION = "Casualty"
PROFILE = "Casualty"
# Bethesda's casualty navigation bar (PDF (12) point 7); Admission List is the
# Casualty list itself (the screen's back button)
PANELS = (
	("Patient File", "Patient File"),
	("Vitals", "Vitals"),
	("TB Screening", "TB Screening"),
	("Diagnosis", "Diagnosis"),
	("Nursing Notes", "Nursing Notes"),
	("Nursing Care", "Nursing Charts and Care Plan"),
	("Doctor Notes", "Doctor Notes"),
	("Doctor Instructions", "Doctor Instructions"),
	("Requests", "Requests"),
	("Results", "Results"),
	("Billing", "Billing"),
	("Drug Administration", "Casualty Drugs"),
	("Disposition", "Disposition"),
	("Discharge", "Discharge"),
)


def units():
	"""The Casualty Units (wards ticked Casualty Unit)."""
	if not frappe.get_meta(UNIT).has_field("ke_casualty"):
		return []
	return sorted(frappe.get_all(UNIT, filters={"ke_casualty": 1, "is_group": 1}, pluck="name"))


def is_unit(ward):
	return bool(ward) and ward in units()


def is_stay(ip):
	"""A casualty stay: marked so, or on a Casualty Unit's bed now."""
	from royce_health_ke.inpatient import ward_of

	name = ip if isinstance(ip, str) else ip.name
	return bool(frappe.db.get_value(IR, name, "ke_casualty")) or is_unit(ward_of(name))


def seed():
	"""The Casualty tab set, once (afterwards the hospital's)."""
	from royce_health_ke.inpatient import SETTINGS

	if not frappe.db.exists("Patient Workspace Profile", PROFILE):
		frappe.get_doc(
			{
				"doctype": "Patient Workspace Profile",
				"profile_name": PROFILE,
				"care_setting": "Casualty",
				"tabs": [{"panel": p, "label": label} for p, label in PANELS],
			}
		).insert(ignore_permissions=True)
	meta = frappe.get_meta(SETTINGS)
	if meta.has_field("casualty_workspace_profile") and not frappe.db.get_single_value(
		SETTINGS, "casualty_workspace_profile"
	):
		frappe.db.set_single_value(SETTINGS, "casualty_workspace_profile", PROFILE)


def profile():
	from royce_health_ke.inpatient import _setting

	meta = frappe.get_meta("Kenya Health Settings")
	if meta.has_field("casualty_workspace_profile"):
		return _setting("casualty_workspace_profile", PROFILE)
	return PROFILE


# Sent to Casualty


def _open_stay(patient):
	return frappe.db.get_value(
		IR,
		{"patient": patient, "status": ["in", ("Admission Scheduled", "Admitted", "Discharge Scheduled")]},
		"name",
	)


def open_stay(visit, unit=None, reason=None, urgency="Urgent"):
	"""The patient's casualty stay, waiting on the Casualty list for a bed.
	An open admission or stay is kept (returned as it is)."""
	from royce_health_ke.inpatient import URGENCIES, _bed_type

	existing = _open_stay(visit.patient)
	if existing:
		return existing
	unit = unit or next(iter(units()), None)
	if not unit:
		return None
	patient = frappe.db.get_value(
		"Patient",
		visit.patient,
		["patient_name", "sex", "dob", "blood_group", "mobile", "email", "phone"],
		as_dict=True,
	)
	reason = (reason or "").strip() or _(visit.get("ke_chief_complaint") or "") or _("Casualty")
	ip = frappe.get_doc(
		{
			"doctype": IR,
			"patient": visit.patient,
			"patient_name": patient.patient_name,
			"gender": patient.sex,
			"dob": patient.dob,
			"blood_group": patient.blood_group,
			"mobile": patient.mobile,
			"email": patient.email,
			"phone": patient.phone,
			"company": visit.company,
			"scheduled_date": nowdate(),
			"admission_ordered_for": nowdate(),
			"admission_service_unit_type": _bed_type(unit),
			"primary_practitioner": visit.get("practitioner"),
			"ke_ward": unit,
			"ke_urgency": urgency if urgency in URGENCIES else "Urgent",
			"ke_admission_reason": reason[:140],
			"ke_patient_visit": visit.name,
			"ke_casualty": 1,
		}
	)
	ip.flags.ignore_permissions = True
	ip.insert()
	ip.add_comment("Info", _("Sent to {0} from {1}").format(unit, visit.name))
	return ip.name


def visit_updated(doc, method=None):
	"""Patient Visit on_update: a visit sent to Casualty (or checked in there)
	puts the patient on the Casualty list."""
	if doc.status != "Open" or doc.get("current_station") != STATION:
		return
	before = doc.get_doc_before_save()
	if before and before.get("current_station") == STATION:
		return
	if not units():
		return
	note = doc.movements[-1].get("note") if doc.get("movements") else None
	open_stay(doc, reason=note)


# Out of the casualty unit: to a ward


def received_on_ward(ip_name, ward):
	"""After a transfer: a casualty stay received on a ward is an admission."""
	if frappe.db.get_value(IR, ip_name, "ke_casualty") and not is_unit(ward):
		frappe.db.set_value(IR, ip_name, "ke_casualty", 0)
		frappe.get_doc(IR, ip_name).add_comment(
			"Info",
			_("Admitted to {0} from casualty, {1}").format(ward, now_datetime().strftime("%Y-%m-%d %H:%M")),
		)


def not_casualty_filter(filters):
	"""Inpatient statistics: casualty stays left out."""
	if frappe.get_meta(IR).has_field("ke_casualty"):
		filters["ke_casualty"] = 0
	return filters
