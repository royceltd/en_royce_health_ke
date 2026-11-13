# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Patient Visit: one per arrival at the hospital, from reception through
triage, consultation, lab, radiology, pharmacy and the cashier.

Reception checks the patient in (service type, practitioner, cash or
insurance with the member's details) and the visit goes to its first
station. Each station sees its waiting list (the Patient Visit list filtered
by station), marks the patient Seen, and sends them on with Send To. Every
move is kept in the visit's Movements table.

Sent to Consultation without a doctor, the visit goes to the next doctor on
duty and their room (assign.py); the patient's queue slip shows both.

Vital signs and consultations recorded the same day link to the open visit,
so the triage list shows each patient's vitals flag and opening the
consultation marks the patient seen."""

import frappe
from frappe import _
from frappe.utils import getdate, now_datetime, nowdate

from royce_health_ke.vitals import age_in_years

STATIONS = (
	"Triage",
	"Consultation",
	"Casualty",
	"Laboratory",
	"Radiology",
	"Pharmacy",
	"Procedure Room",
	"Cashier",
	"Admission",
)
FIRST_STATION = {
	"Outpatient": "Triage",
	"Review": "Triage",
	"Casualty": "Casualty",
	"Lab only": "Laboratory",
	"Radiology only": "Radiology",
	"Pharmacy only": "Pharmacy",
}


def age_label(dob, on=None):
	"""'34 y', '7 m', '12 d' - short enough for a queue list."""
	if not dob:
		return ""
	dob, on = getdate(dob), getdate(on or nowdate())
	years = age_in_years(dob, on)
	if years:
		return _("{0} y").format(years)
	months = (on.year - dob.year) * 12 + on.month - dob.month - (on.day < dob.day)
	if months:
		return _("{0} m").format(months)
	return _("{0} d").format((on - dob).days)


def validate_visit(doc):
	dob = frappe.db.get_value("Patient", doc.patient, "dob")
	doc.age = age_label(dob, doc.visit_date)
	if doc.is_new():
		other = frappe.db.get_value(
			"Patient Visit",
			{
				"patient": doc.patient,
				"status": "Open",
				"visit_date": doc.visit_date,
				"name": ["!=", doc.name],
			},
			["name", "current_station"],
			as_dict=True,
		)
		if other:
			frappe.throw(
				_("{0} already has an open visit today ({1}, at {2}). Send that visit on instead.").format(
					doc.patient_name or doc.patient, other.name, _(other.current_station or "")
				),
				title=_("Already checked in"),
			)
	if doc.payment_method == "Insurance":
		validate_insurance(doc)


def validate_insurance(doc):
	if not doc.insurance_payor:
		frappe.throw(_("Choose the payer (insurer or scheme)."))
	if doc.insurance_policy:
		policy = frappe.db.get_value(
			"Patient Insurance Policy",
			doc.insurance_policy,
			["patient", "insurance_payor", "policy_expiry_date", "docstatus", "policy_number"],
			as_dict=True,
		)
		if not policy or policy.patient != doc.patient or policy.docstatus != 1:
			frappe.throw(_("{0} is not an active policy of this patient.").format(doc.insurance_policy))
		if policy.insurance_payor != doc.insurance_payor:
			frappe.throw(_("Policy {0} is with {1}.").format(doc.insurance_policy, policy.insurance_payor))
		if policy.policy_expiry_date and getdate(policy.policy_expiry_date) < getdate(doc.visit_date):
			frappe.throw(
				_("Policy {0} expired on {1}. Renew it, or check the patient in as cash.").format(
					policy.policy_number, frappe.format(policy.policy_expiry_date, "Date")
				),
				title=_("Cover expired"),
			)
		doc.member_number = policy.policy_number
	elif not (doc.member_number and doc.policy_expiry):
		frappe.throw(_("Enter the member number and the date the cover is valid until."))
	elif getdate(doc.policy_expiry) < getdate(doc.visit_date):
		frappe.throw(_("The cover expired on {0}.").format(frappe.format(doc.policy_expiry, "Date")))


def before_insert_visit(doc):
	if not doc.get("facility"):
		from royce_health_ke.assign import default_facility

		doc.facility = default_facility(doc.company)
	if doc.payment_method == "Insurance" and not doc.insurance_policy:
		doc.insurance_policy = find_or_create_policy(doc)
	station = FIRST_STATION.get(doc.visit_type, "Triage")
	_move(doc, _("Reception"), station)


def after_insert_visit(doc):
	"""An appointment the patient arrived for is checked in."""
	if doc.appointment and frappe.db.get_value("Patient Appointment", doc.appointment, "status") in (
		"Scheduled",
		"Open",
		"Confirmed",
	):
		frappe.db.set_value("Patient Appointment", doc.appointment, "status", "Checked In")
	if doc.appointment and doc.payment_method == "Insurance" and doc.insurance_policy:
		from royce_health_ke.schemes import cover_appointment

		cover_appointment(doc.appointment, doc.insurance_policy)


def find_or_create_policy(doc):
	"""The patient's submitted policy with this payer and member number, or a
	new one from what reception entered."""
	existing = frappe.db.get_value(
		"Patient Insurance Policy",
		{
			"patient": doc.patient,
			"insurance_payor": doc.insurance_payor,
			"policy_number": doc.member_number,
			"docstatus": 1,
		},
		"name",
	)
	if existing:
		return existing
	policy = frappe.get_doc(
		{
			"doctype": "Patient Insurance Policy",
			"patient": doc.patient,
			"insurance_payor": doc.insurance_payor,
			"insurance_plan": doc.insurance_plan,
			"policy_number": doc.member_number,
			"policy_expiry_date": doc.policy_expiry,
			"ke_relation": doc.relation,
			"ke_principal_member": doc.principal_member,
			"ke_principal_member_number": doc.principal_member_number,
		}
	)
	policy.insert(ignore_permissions=True)
	policy.submit()
	return policy.name


def _move(doc, from_station, to_station, practitioner=None, note=None, room=None):
	now, user = now_datetime(), frappe.session.user
	doc.append(
		"movements",
		{
			"from_station": from_station,
			"to_station": to_station,
			"sent_at": now,
			"sent_by": user,
			"practitioner": practitioner,
			"service_unit": room,
			"note": note,
		},
	)
	doc.current_station = to_station
	doc.queue_status = "Waiting"
	doc.sent_at, doc.sent_by = now, user
	doc.acknowledged_at = doc.acknowledged_by = None


def _open_visit(name):
	doc = frappe.get_doc("Patient Visit", name)
	doc.check_permission("write")
	if doc.status != "Open":
		frappe.throw(_("Visit {0} is {1}.").format(doc.name, _(doc.status)))
	return doc


@frappe.whitelist()
def send_to(visit: str, station: str, practitioner: str | None = None, note: str | None = None):
	"""Send the patient to another station's waiting list."""
	doc = _open_visit(visit)
	if station not in STATIONS:
		frappe.throw(_("Unknown station {0}.").format(station))
	if station == doc.current_station and doc.queue_status == "Waiting":
		frappe.throw(_("{0} is already waiting at {1}.").format(doc.patient_name, _(station)))
	if station == "Consultation":
		return _send_to_consultation(doc, practitioner, note)
	if practitioner:
		doc.practitioner = practitioner
	_move(doc, doc.current_station, station, practitioner, note)
	doc.save()
	return {"station": doc.current_station}


def _consultation_result(doc):
	return {
		"station": doc.current_station,
		"practitioner": doc.practitioner,
		"practitioner_name": doc.practitioner_name,
		"room": doc.consultation_room,
	}


def _send_to_consultation(doc, practitioner, note):
	"""The doctor named, else the appointment's, else the next doctor on duty."""
	from frappe.utils.synchronization import filelock

	from royce_health_ke import assign

	if not practitioner and doc.appointment:
		practitioner = frappe.db.get_value("Patient Appointment", doc.appointment, "practitioner")
	if practitioner:
		if practitioner != doc.practitioner or not doc.consultation_room:
			doc.consultation_room = assign.room_of(practitioner, doc.company, doc.get("facility"))
		doc.practitioner = practitioner
		_move(doc, doc.current_station, "Consultation", practitioner, note, doc.consultation_room)
		doc.save()
		return _consultation_result(doc)
	# One assignment at a time, committed before the next is worked out, so
	# two nurses sending at once don't both pick the same doctor.
	with filelock("ke_next_consultant", timeout=20):
		assign.assign(doc)
		_move(doc, doc.current_station, "Consultation", doc.practitioner, note, doc.consultation_room)
		doc.save()
		if not frappe.flags.in_test:
			frappe.db.commit()
	return _consultation_result(doc)


@frappe.whitelist()
def reassign(visit: str):
	"""Give a patient waiting at Consultation to the next doctor on duty
	(their doctor left, or is held up). Their place in the queue is kept."""
	from frappe.utils.synchronization import filelock

	from royce_health_ke import assign

	doc = _open_visit(visit)
	if doc.current_station != "Consultation" or doc.queue_status != "Waiting":
		frappe.throw(_("Only a patient waiting at Consultation can be reassigned."))
	before = doc.practitioner_name or doc.practitioner
	with filelock("ke_next_consultant", timeout=20):
		assign.assign(doc, exclude=(doc.practitioner,) if doc.practitioner else ())
		if doc.movements:
			last = doc.movements[-1]
			last.practitioner, last.service_unit = doc.practitioner, doc.consultation_room
			last.note = _("Reassigned from {0}").format(before) if before else last.note
		doc.save()
		if not frappe.flags.in_test:
			frappe.db.commit()
	return _consultation_result(doc)


@frappe.whitelist()
def acknowledge(visit: str):
	"""The station has the patient: they leave the waiting list."""
	doc = _open_visit(visit)
	_acknowledge(doc)
	doc.save()


def _acknowledge(doc):
	if doc.queue_status == "Seen":
		return
	now, user = now_datetime(), frappe.session.user
	doc.queue_status = "Seen"
	doc.acknowledged_at, doc.acknowledged_by = now, user
	if doc.movements:
		doc.movements[-1].acknowledged_at = now
		doc.movements[-1].acknowledged_by = user


@frappe.whitelist()
def complete(visit: str):
	doc = _open_visit(visit)
	_acknowledge(doc)
	doc.status = "Completed"
	doc.save()


@frappe.whitelist()
def cancel(visit: str, reason: str):
	doc = _open_visit(visit)
	doc.status = "Cancelled"
	doc.status_reason = reason
	doc.save()


def open_visit_for(patient, on=None):
	if not patient:
		return None
	return frappe.db.get_value(
		"Patient Visit",
		{"patient": patient, "status": "Open", "visit_date": getdate(on or nowdate())},
		"name",
		order_by="creation desc",
	)


# Vital signs and consultations link to the day's open visit.


def link_vital_signs(doc, method=None):
	if not doc.get("ke_patient_visit"):
		doc.ke_patient_visit = open_visit_for(doc.patient, doc.get("signs_date"))


def vital_signs_saved(doc, method=None):
	if doc.get("ke_patient_visit") and doc.docstatus < 2:
		frappe.db.set_value(
			"Patient Visit",
			doc.ke_patient_visit,
			{"vitals_status": doc.get("ke_vitals_status") or "", "vital_signs": doc.name},
			update_modified=False,
		)


def link_encounter(doc, method=None):
	"""Link the day's visit and fill what the consultation can take from it."""
	if not doc.get("ke_patient_visit"):
		doc.ke_patient_visit = open_visit_for(doc.patient, doc.get("encounter_date"))
	if doc.ke_patient_visit:
		visit = frappe.db.get_value(
			"Patient Visit",
			doc.ke_patient_visit,
			[
				"appointment_type",
				"practitioner",
				"department",
				"payment_method",
				"insurance_policy",
				"appointment",
			],
			as_dict=True,
		)
		# The visit's first consultation is the appointment's: linked, Marley
		# bills the consultation fee once (on the appointment), not again on
		# the consultation. A later review in the same visit stays separate.
		if (
			visit.appointment
			and not doc.get("appointment")
			and not frappe.db.exists(
				"Patient Encounter",
				{"appointment": visit.appointment, "docstatus": ["<", 2], "name": ["!=", doc.name]},
			)
		):
			doc.appointment = visit.appointment
		# An insured visit's orders are covered: Marley gives the consultation's
		# service requests insurance cover (and the scheme's prices) from its
		# policy.
		policy = visit.insurance_policy if visit.payment_method == "Insurance" else None
		for field, value in (
			("appointment_type", visit.appointment_type),
			("practitioner", visit.practitioner),
			("medical_department", visit.department),
			("insurance_policy", policy),
		):
			if value and not doc.get(field):
				doc.set(field, value)


def encounter_saved(doc, method=None):
	"""The consultation is open: the patient is seen at Consultation."""
	if not doc.get("ke_patient_visit") or doc.docstatus == 2:
		return
	visit = frappe.get_doc("Patient Visit", doc.ke_patient_visit)
	if visit.status != "Open":
		return
	visit.encounter = doc.name
	if visit.current_station == "Consultation":
		_acknowledge(visit)
	visit.flags.ignore_permissions = True
	visit.save()


@frappe.whitelist()
def patient_policies(patient: str) -> list[dict]:
	"""Active policies of a patient, newest first, for check-in."""
	frappe.has_permission("Patient Visit", "create", throw=True)
	return frappe.get_all(
		"Patient Insurance Policy",
		filters={"patient": patient, "docstatus": 1, "policy_expiry_date": [">=", nowdate()]},
		fields=["name", "insurance_payor", "insurance_plan", "policy_number", "policy_expiry_date"],
		order_by="creation desc",
	)
