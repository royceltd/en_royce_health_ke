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

# The stations and each visit type's first station live with the patient flow.
from royce_health_ke.flow import FIRST_STATION, STATIONS
from royce_health_ke.vitals import age_in_years


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
	# without a member number, validate asks for it
	if doc.payment_method == "Insurance" and not doc.insurance_policy and doc.member_number:
		doc.insurance_policy = find_or_create_policy(doc)
	from royce_health_ke import flow

	flow.check_in(doc)
	if not doc.fee_first:
		_warn_no_fee(doc)


def _warn_no_fee(doc):
	"""A cash consultation that should pay first but has no fee set up: say
	why, instead of sending the patient on without a word."""
	from royce_health_ke import fees
	from royce_health_ke.visit_bill import FEE_VISIT_TYPES, TRIAGE, enforced

	if (
		doc.get("payment_method") != "Cash"
		or doc.get("visit_type") not in FEE_VISIT_TYPES
		or doc.get("appointment")
		or doc.get("allow_credit")
		or not enforced(TRIAGE)
	):
		return
	reason = fees.explain(
		frappe._dict(
			practitioner=doc.get("practitioner"),
			appointment_type=doc.get("appointment_type"),
			department=doc.get("department"),
			company=doc.get("company"),
		)
	)
	if reason:
		frappe.msgprint(
			reason
			+ " "
			+ _("The patient goes straight to triage, without paying the consultation fee first."),
			title=_("No consultation fee"),
			indicator="orange",
		)


def after_insert_visit(doc):
	"""An appointment the patient arrived for is checked in; a cash
	consultation's fee goes on its draft bill."""
	from royce_health_ke.visit_bill import draft_visit_fee

	draft_visit_fee(doc)
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
		["name", "policy_expiry_date"],
		as_dict=True,
	)
	if existing:
		renew_policy(existing, doc.get("policy_expiry"))
		return existing.name
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


def renew_policy(policy, valid_until):
	"""Reception saw a renewed card: the policy is valid until the later date."""
	if not valid_until or (
		policy.policy_expiry_date and getdate(valid_until) <= getdate(policy.policy_expiry_date)
	):
		return
	frappe.db.set_value("Patient Insurance Policy", policy.name, "policy_expiry_date", getdate(valid_until))
	frappe.get_doc("Patient Insurance Policy", policy.name).add_comment(
		"Info",
		_("Cover renewed at check-in: valid until {0}.").format(frappe.format(getdate(valid_until), "Date")),
	)


def _open_visit(name):
	doc = frappe.get_doc("Patient Visit", name)
	doc.check_permission("write")
	if doc.status != "Open":
		frappe.throw(_("Visit {0} is {1}.").format(doc.name, _(doc.status)))
	return doc


@frappe.whitelist()
def send_to(visit: str, station: str, practitioner: str | None = None, note: str | None = None):
	"""Send the patient to another station's waiting list (flow.py: the rules, then the move)."""
	from royce_health_ke import flow

	return flow.send(_open_visit(visit), station, practitioner, note)


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
	from royce_health_ke.flow import _consultation_result

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
def complete(visit: str, reason: str | None = None):
	"""Complete Visit: refused while anything is open (visit_close), unless a
	manager gives a reason."""
	from royce_health_ke import visit_close

	visit_close.close(_open_visit(visit), reason)


@frappe.whitelist()
def cancel(visit: str, reason: str):
	"""Cancel Visit: only while nothing has been done on it (visit_close)."""
	from royce_health_ke import visit_close

	visit_close.cancel(_open_visit(visit), reason)


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
	"""Triage records the vital signs: the visit shows their flag, the patient
	is seen at Triage on the first save, and submitting them sends the patient
	to the doctor (Kenya Health Settings > Vital signs send the patient to the
	doctor; IT demo, 17 Nov 2026: no Seen or Send To clicks at triage)."""
	if not doc.get("ke_patient_visit") or doc.docstatus == 2:
		return
	frappe.db.set_value(
		"Patient Visit",
		doc.ke_patient_visit,
		{"vitals_status": doc.get("ke_vitals_status") or "", "vital_signs": doc.name},
		update_modified=False,
	)
	if not _triage_moves_on():
		return
	visit = frappe.get_doc("Patient Visit", doc.ke_patient_visit)
	if visit.status != "Open" or visit.current_station != "Triage":
		return
	visit.flags.ignore_permissions = True
	if method == "on_submit" and _vitals_send_to_doctor():
		_send_to_doctor(visit)
	elif visit.queue_status != "Seen":
		_acknowledge(visit)
		visit.save()


def _triage_moves_on():
	f = frappe.flags
	if f.in_import or f.in_install or f.in_migrate or f.ke_demo:
		return False
	# tests of other areas record vital signs without moving the patient
	return not f.in_test or bool(f.ke_test_triage_moves)


def _vitals_send_to_doctor():
	return bool(frappe.db.get_single_value("Kenya Health Settings", "vitals_send_to_doctor"))


def _send_to_doctor(visit):
	"""Triage done: on to the doctor's queue (the visit's doctor, else the next
	on duty), by the patient flow's rules. A move that can't happen leaves the
	patient at Triage with the reason; the vital signs stay submitted."""
	from royce_health_ke import flow

	_acknowledge(visit)
	frappe.db.savepoint("ke_vitals_to_doctor")
	try:
		r = flow.send(visit, "Consultation", visit.practitioner, _("Triage done"))
	except Exception as e:
		frappe.db.rollback(save_point="ke_vitals_to_doctor")
		frappe.clear_last_message()
		seen = frappe.get_doc("Patient Visit", visit.name)
		_acknowledge(seen)
		seen.flags.ignore_permissions = True
		seen.save()
		frappe.msgprint(
			_("Vital signs saved, but {0} was not sent to the doctor: {1}").format(
				visit.patient_name, frappe.utils.strip_html(str(e))
			),
			indicator="orange",
			alert=True,
		)
		return
	if r.get("station") == "Consultation":
		who = ", ".join(x for x in (r.get("practitioner_name") or r.get("practitioner"), r.get("room")) if x)
		message = _("Sent to the doctor: {0}").format(who) if who else _("Sent to the doctor's queue")
	else:
		message = _("Sent to the {0} first").format(_(r.get("station")))
	frappe.msgprint(message, indicator="green", alert=True)


@frappe.whitelist()
def open_station(visit: str) -> dict:
	"""What a queue opens for this visit (the Triage and Doctor's queues): the
	visit's draft vital signs or consultation, or a new one filled from the
	visit. {"doctype", "name"} for a saved record, {"doctype", "new": values}
	for a new one; the visit itself when the user doesn't work that station."""
	doc = frappe.get_doc("Patient Visit", visit)
	doc.check_permission("read")
	stay = {"doctype": "Patient Visit", "name": doc.name}
	if doc.status != "Open":
		return stay
	if doc.current_station == "Triage" and frappe.has_permission("Vital Signs", "create"):
		draft = frappe.db.get_value(
			"Vital Signs", {"ke_patient_visit": doc.name, "docstatus": 0}, "name", order_by="creation desc"
		)
		if draft:
			return {"doctype": "Vital Signs", "name": draft}
		if frappe.db.exists("Vital Signs", {"ke_patient_visit": doc.name, "docstatus": 1}):
			return stay
		return {
			"doctype": "Vital Signs",
			"new": {"patient": doc.patient, "company": doc.company, "ke_patient_visit": doc.name},
		}
	if doc.current_station == "Cashier" and frappe.has_permission("Sales Invoice", "create"):
		# the Cashier Queue opens the bill to pay: the draft, else an unpaid one
		for filters in (
			{"ke_patient_visit": doc.name, "docstatus": 0, "is_return": 0},
			{"ke_patient_visit": doc.name, "docstatus": 1, "outstanding_amount": [">", 0], "is_return": 0},
		):
			bill = frappe.db.get_value("Sales Invoice", filters, "name", order_by="creation desc")
			if bill:
				return {"doctype": "Sales Invoice", "name": bill}
		return stay
	if doc.current_station == "Consultation" and frappe.has_permission("Patient Encounter", "create"):
		draft = frappe.db.get_value(
			"Patient Encounter",
			{"ke_patient_visit": doc.name, "docstatus": 0},
			"name",
			order_by="creation desc",
		)
		if draft:
			return {"doctype": "Patient Encounter", "name": draft}
		mine = frappe.db.get_value("Healthcare Practitioner", {"user_id": frappe.session.user}, "name")
		return {
			"doctype": "Patient Encounter",
			"new": {
				"patient": doc.patient,
				"practitioner": doc.practitioner or mine,
				"appointment_type": doc.appointment_type,
				"medical_department": doc.department,
				"company": doc.company,
				"ke_patient_visit": doc.name,
			},
		}
	return stay


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
				"fee_first",
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
		# The fee paid at check-in (billed on the visit) is this consultation's:
		# the visit's first consultation is not billed again.
		if (
			doc.is_new()
			and visit.fee_first
			and not visit.appointment
			and not frappe.db.exists(
				"Patient Encounter", {"ke_patient_visit": doc.ke_patient_visit, "docstatus": ["<", 2]}
			)
		):
			doc.invoiced = 1
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
		# a patient sent while nobody was on duty: the doctor who opens the consultation takes them
		if not visit.practitioner and doc.get("practitioner"):
			from royce_health_ke.assign import room_of

			visit.practitioner = doc.practitioner
			visit.consultation_room = room_of(doc.practitioner, visit.company, visit.get("facility"))
	visit.flags.ignore_permissions = True
	visit.save()


@frappe.whitelist()
def patient_policies(patient: str) -> list[dict]:
	"""Active policies of a patient, newest first, for check-in."""
	frappe.has_permission("Patient Visit", "create", throw=True)
	return frappe.get_all(
		"Patient Insurance Policy",
		filters={"patient": patient, "docstatus": 1, "policy_expiry_date": [">=", nowdate()]},
		fields=[
			"name",
			"insurance_payor",
			"insurance_plan",
			"policy_number",
			"policy_expiry_date",
			"ke_relation",
			"ke_principal_member",
			"ke_principal_member_number",
		],
		order_by="creation desc",
	)
