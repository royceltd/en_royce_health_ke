# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""The patient's way through the hospital, in one place.

A Patient Visit is at one station at a time (current_station) and every move
is a row of its Movements table, with the reason it happened. This module is
the only code that moves a patient: check-in, Send To (from any station or
the consultation), the moves that follow a payment, and the pharmacy sending
a patient back to the doctor.

Before a move, the RULES below are checked, in order. Each rule is a
hospital's choice in Kenya Health Settings > Payment Before Service:

	to Triage or Consultation   the consultation fee is paid first
	                            (Consultation fee before triage)
	to Laboratory, Radiology    a cash patient whose requests there aren't
	or Pharmacy                 paid goes to the Cashier first, and on to the
	                            service point once paid
	                            (Cashier before the lab, radiology and pharmacy)
	to the Cashier              where the patient goes once paid is remembered
	                            (the visit's After Paying, Goes To)

Automatic moves, by event:

	check-in        to the visit type's first station (FIRST_STATION), or the
	                Cashier when the consultation fee comes first
	payment         from the Cashier to Triage (fee paid), or to the service
	                point the patient was going to (requests paid)
	pharmacy        back to the doctor, with the pharmacist's note

What is paid is billing's business (visit_bill: needs_fee_first, fee_due,
awaiting_stations, from each order's stored payment status)."""

import frappe
from frappe import _
from frappe.utils import cint, now_datetime

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
SERVICE_POINTS = ("Laboratory", "Radiology", "Pharmacy")
RECEPTION = "Reception"

# Why a patient moved (Movements > Reason)
CHECKED_IN = "Checked in"
FEE_FIRST = "Consultation fee first"
FEE_PAID = "Consultation fee paid"
SENT = "Sent"
PAY_FIRST = "To pay first"
PAID = "Paid at the Cashier"
SENT_BACK = "Sent back by the pharmacy"
REASONS = (CHECKED_IN, FEE_FIRST, FEE_PAID, SENT, PAY_FIRST, PAID, SENT_BACK)

SETTINGS = "Kenya Health Settings"


def setting(field):
	return cint(frappe.db.get_single_value(SETTINGS, field))


def first_station(visit_type):
	return FIRST_STATION.get(visit_type, "Triage")


# The one way to move a patient


def move(doc, to_station, reason, practitioner=None, note=None, room=None, from_station=None):
	"""Put the visit on `to_station`'s waiting list and record the move. The
	caller saves the visit."""
	now, user = now_datetime(), frappe.session.user
	doc.append(
		"movements",
		{
			"from_station": from_station or doc.current_station or _(RECEPTION),
			"to_station": to_station,
			"reason": reason,
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


# Rules checked before a move


def _fee_first(doc, station, note):
	from royce_health_ke.visit_bill import fee_due

	if fee_due(doc):
		frappe.throw(
			_(
				"{0} has not paid the consultation fee. Bill and take the fee at the Cashier first: "
				"the patient then joins the triage list. A manager can allow services before payment."
			).format(doc.patient_name),
			title=_("Consultation fee first"),
		)
	return station, SENT, note


def _cashier_before_service(doc, station, note):
	"""A cash patient whose requests at that service point aren't paid goes to
	the Cashier first, and on to it once paid (after_payment)."""
	from royce_health_ke.visit_bill import awaiting_stations

	if not setting("cashier_before_service"):
		return station, SENT, note
	waiting = awaiting_stations(doc.name)
	if station not in waiting:
		return station, SENT, note
	if doc.current_station == "Cashier":
		frappe.throw(
			_(
				"{0}'s {1} requests are not paid yet. Take the payment first: the patient then joins the "
				"{1} list. A manager can allow services before payment."
			).format(doc.patient_name, _(station)),
			title=_("Not paid yet"),
		)
	doc.after_payment = ", ".join([station] + [s for s in waiting if s != station])
	why = _("To the Cashier first: the {0} requests are not paid").format(_(station))
	return "Cashier", PAY_FIRST, f"{note} · {why}" if note else why


def _remember_next(doc, station, note):
	from royce_health_ke.visit_bill import awaiting_stations

	doc.after_payment = ", ".join(awaiting_stations(doc.name))
	return station, SENT, note


# (to these stations, the check, what it is for)
RULES = (
	(("Triage", "Consultation"), _fee_first, "consultation fee before triage and the doctor"),
	(SERVICE_POINTS, _cashier_before_service, "cash patients pay before the lab, radiology and pharmacy"),
	(("Cashier",), _remember_next, "where the patient goes once paid"),
)


def _apply_rules(doc, station, note):
	"""(station, reason, note, the station asked for when redirected)."""
	reason = SENT
	for stations, check, _purpose in RULES:
		if station in stations:
			new_station, reason, note = check(doc, station, note)
			if new_station != station:
				return new_station, reason, note, station
	return station, reason, note, None


# Moves


def check_in(doc):
	"""A new visit's first station (before_insert)."""
	from royce_health_ke.visit_bill import needs_fee_first

	if needs_fee_first(doc):
		# Cash consultation: the fee is paid at the Cashier, then the patient joins the triage list.
		doc.fee_first = 1
		move(doc, "Cashier", FEE_FIRST, note=_("Consultation fee before triage"), from_station=_(RECEPTION))
		return
	move(doc, first_station(doc.visit_type), CHECKED_IN, from_station=_(RECEPTION))


def send(doc, station, practitioner=None, note=None):
	"""Send To: the rules, then the move. Returns where the patient went."""
	if station not in STATIONS:
		frappe.throw(_("Unknown station {0}.").format(station))
	station, reason, note, redirected = _apply_rules(doc, station, note)
	if station == doc.current_station and doc.queue_status == "Waiting":
		frappe.throw(_("{0} is already waiting at {1}.").format(doc.patient_name, _(station)))
	if station == "Consultation":
		return _to_consultation(doc, practitioner, note, reason)
	if practitioner:
		doc.practitioner = practitioner
	move(doc, station, reason, practitioner, note)
	doc.save()
	return {"station": doc.current_station, "redirected_from": redirected}


def _consultation_result(doc):
	return {
		"station": doc.current_station,
		"practitioner": doc.practitioner,
		"practitioner_name": doc.practitioner_name,
		"room": doc.consultation_room,
	}


def _to_consultation(doc, practitioner, note, reason=SENT):
	"""The doctor named, else the appointment's, else the next doctor on duty."""
	from frappe.utils.synchronization import filelock

	from royce_health_ke import assign

	if not practitioner and doc.appointment:
		practitioner = frappe.db.get_value("Patient Appointment", doc.appointment, "practitioner")
	if practitioner:
		if practitioner != doc.practitioner or not doc.consultation_room:
			doc.consultation_room = assign.room_of(practitioner, doc.company, doc.get("facility"))
		doc.practitioner = practitioner
		move(doc, "Consultation", reason, practitioner, note, doc.consultation_room)
		doc.save()
		return _consultation_result(doc)
	# One assignment at a time, committed before the next is worked out, so
	# two nurses sending at once don't both pick the same doctor.
	with filelock("ke_next_consultant", timeout=20):
		assign.assign(doc)
		move(doc, "Consultation", reason, doc.practitioner, note, doc.consultation_room)
		doc.save()
		if not frappe.flags.in_test:
			frappe.db.commit()
	return _consultation_result(doc)


def after_payment(visit):
	"""A payment on the visit: the patient waiting at the Cashier moves on.
	The consultation fee paid: to the first station (Triage). Requests paid:
	to the first service point the patient was going to whose requests are
	now paid. Saves the visit when it moves."""
	from royce_health_ke.visit_bill import awaiting_stations, fee_due, fee_reference, is_paid

	if visit.get("fee_first") and not visit.get("fee_paid") and is_paid(*fee_reference(visit)):
		visit.fee_paid = 1
		if visit.status == "Open" and visit.current_station == "Cashier":
			move(visit, first_station(visit.visit_type), FEE_PAID, note=_("Consultation fee paid"))
		visit.flags.ignore_permissions = True
		visit.save()
		return
	if visit.status != "Open" or visit.current_station != "Cashier" or not visit.get("after_payment"):
		return
	if fee_due(visit):
		return
	planned = [s.strip() for s in visit.after_payment.split(",") if s.strip()]
	waiting = set(awaiting_stations(visit.name))
	ready = [s for s in planned if s not in waiting]
	if not ready:
		return
	move(visit, ready[0], PAID, note=_("Paid at the Cashier"))
	visit.after_payment = ", ".join(s for s in planned if s != ready[0])
	visit.flags.ignore_permissions = True
	visit.save()


def sent_back(visit, practitioner, note):
	"""The pharmacy sends the patient back to the doctor (a substitute is needed).
	Saves the visit."""
	if visit.status != "Open":
		return
	move(visit, "Consultation", SENT_BACK, practitioner, note, visit.consultation_room)
	visit.practitioner = practitioner or visit.practitioner
	visit.flags.ignore_permissions = True
	visit.save()
