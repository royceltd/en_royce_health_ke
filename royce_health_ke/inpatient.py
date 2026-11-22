# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""The inpatient journey (Bethesda proposals, 18 Nov 2026), on Marley's records.

Marley keeps the admission (Inpatient Record, beds and bed charges), the ward
medication order and its doses (Inpatient Medication Order / Entry,
Medication Administration), nursing notes, fluid charts, handover, care plans
and the discharge summary, and its Nursing Dialog records them at the bedside.
This module joins them into the hospital's workflow:

- Admit to Ward from the consultation: ward, urgency, date, reason and notes
  make Marley's admission order; the visit moves to Admission.
- The Ward page: patients awaiting admission (a bed is given) and those on
  the ward, by ward.
- One patient screen per admission with a horizontal tab bar; the tabs are
  data (Patient Workspace Profile), so another care setting reuses it.
- Ward rounds prescribe: an inpatient consultation's medicines become the
  ward medication order (doses per frequency, duration and times), so they
  reach the pharmacy's ward issue and the nurses' round.
- Ward drugs are charged on issue or on administration (Kenya Health
  Settings, which sets Marley's ward stock switch); a dose can be given only
  once the pharmacy has sent the drug (Marley).
- Insured admissions that need the payer's pre-authorisation say so; cash
  admissions show the running bill against what is paid.

Every hospital choice is a setting or data with a default; the medication
chain (prescription, pharmacy issue, dose given) is the same for all."""

import math

import frappe
from frappe import _
from frappe.utils import add_days, add_to_date, cint, flt, get_datetime, getdate, now_datetime, nowdate

IR = "Inpatient Record"
SETTINGS = "Kenya Health Settings"
ON_ISSUE, ON_ADMINISTRATION = "On issue", "On administration"
URGENCIES = ("Routine", "Urgent", "Emergency")
ON_WARD = ("Admitted", "Discharge Scheduled")
WARD_ROLES = ("Nursing User", "Physician", "Healthcare Administrator", "System Manager")
ADMIT_ROLES = ("Nursing User", "Healthcare Administrator", "System Manager")
DEFAULT_PROFILE = "Inpatient"
THEATRE_PROFILE = "Theatre"
# The theatre's patient screen (opened from the Theatre List), Bethesda 20 Nov 2026
THEATRE_PANELS = ("Theatre Doctor Notes", "Drug Administration", "Vitals", "Results", "Patient File")
# The default tab bar (Bethesda's ward screen, PDF (9)); a hospital edits its
# own in Patient Workspace Profile.
PANELS = (
	"Patient File",
	"Vitals",
	"TB Screening",
	"Diagnosis",
	"Doctor Notes",
	"Doctor Instructions",
	"Nursing Notes",
	"Nursing Care",
	"Drug Administration",
	"Requests",
	"Results",
	"Consent",
	"Billing",
	"Disposition",
	"Discharge",
)
# v0.47's default, for sites still on it (patch v0_48.inpatient_tabs)
PANELS_V1 = (
	"Patient File",
	"Vitals",
	"Requests",
	"Results",
	"Diagnosis",
	"Nursing Notes",
	"Nursing Care",
	"Drug Administration",
	"Billing",
	"Discharge",
)
DOCTOR_NOTE, DOCTOR_INSTRUCTIONS = "Doctor's Note", "Doctor's Instructions"
DOCTOR_TYPES = (DOCTOR_NOTE, DOCTOR_INSTRUCTIONS)
TB_CHART = "TB Screening"
OUTCOMES = ("Discharged", "Referred Out", "Absconded", "Died")


def _setting(field, default=None):
	value = frappe.db.get_single_value(SETTINGS, field)
	return value if value not in (None, "") else default


def _check(roles):
	if not set(roles) & set(frappe.get_roles()):
		frappe.throw(_("Not permitted"), frappe.PermissionError)


# Settings: the ward drug charge (Marley's ward stock switch)


def sync_drug_charge(doc=None, method=None):
	"""Kenya Health Settings on_update and migrate: charging on administration
	means the pharmacy moves drugs to the bed and each dose given is issued
	and billed (Marley's ward stock); on issue, the pharmacy's issue charges
	them. Marley makes the nurses' doses from the order either way."""
	charge = (doc.get("ward_drug_charge") if doc else None) or _setting("ward_drug_charge", ON_ISSUE)
	frappe.db.set_single_value(
		"Healthcare Settings",
		{
			"manage_inpatient_medication_stock": 1 if charge == ON_ADMINISTRATION else 0,
			"auto_schedule_medication_doses": 1,
		},
	)


# Admissions price from a selling price list


def selling_price_list(doc, method=None):
	"""Inpatient Record validate: the admission's price list sells. Marley's
	Admit dialog offers every price list; a buying one (chosen on the demo, 19
	Nov 2026) made every bed charge fail and the visit's bill with it."""
	if doc.get("price_list") and not frappe.db.get_value("Price List", doc.price_list, "selling"):
		frappe.throw(
			_(
				"{0} is a buying price list. Choose a selling price list for the admission (or leave it blank)."
			).format(frappe.bold(doc.price_list)),
			title=_("Selling price list"),
		)


# Wards and beds


def wards():
	"""Wards: groups of beds (Healthcare Service Units with inpatient occupancy)."""
	parents = frappe.get_all(
		"Healthcare Service Unit",
		filters={"is_group": 0, "inpatient_occupancy": 1},
		pluck="parent_healthcare_service_unit",
		distinct=True,
	)
	return sorted(p for p in parents if p)


@frappe.whitelist()
def ward_list() -> list:
	_check(WARD_ROLES)
	return wards()


@frappe.whitelist()
def vacant_beds(ward: str) -> list:
	_check(WARD_ROLES)
	return frappe.get_all(
		"Healthcare Service Unit",
		filters={
			"parent_healthcare_service_unit": ward,
			"is_group": 0,
			"inpatient_occupancy": 1,
			"occupancy_status": "Vacant",
		},
		fields=["name", "healthcare_service_unit_name", "service_unit_type"],
		order_by="name",
	)


def current_bed(ip):
	rows = frappe.get_all(
		"Inpatient Occupancy",
		filters={"parent": ip, "parenttype": IR, "left": 0},
		fields=["service_unit", "check_in"],
		order_by="check_in desc",
		limit=1,
	)
	return rows[0] if rows else None


def ward_of(ip):
	bed = current_bed(ip)
	if bed:
		return frappe.db.get_value(
			"Healthcare Service Unit", bed.service_unit, "parent_healthcare_service_unit"
		)
	return frappe.db.get_value(IR, ip, "ke_ward")


# Admit to Ward (from the consultation)


def _bed_type(ward):
	return frappe.db.get_value(
		"Healthcare Service Unit",
		{"parent_healthcare_service_unit": ward, "is_group": 0, "inpatient_occupancy": 1},
		"service_unit_type",
	)


def _preauth_needed(visit):
	if not visit or visit.payment_method == "Cash" or not visit.insurance_payor:
		return None
	hours = frappe.db.get_value(
		"Insurance Payor", visit.insurance_payor, ["ke_admission_preauth", "ke_preauth_hours"], as_dict=True
	)
	if hours and cint(hours.ke_admission_preauth):
		return cint(hours.ke_preauth_hours) or 24
	return None


@frappe.whitelist()
def request_admission(
	encounter: str,
	ward: str,
	urgency: str,
	admission_date: str,
	reason: str,
	notes: str | None = None,
	expected_days: int | None = None,
) -> str:
	"""Admit to Ward: Marley's admission order with the ward, urgency, date,
	reason and notes. The patient appears on the ward's admission list."""
	from royce_health_ke.marley import create_inpatient_record

	frappe.has_permission("Inpatient Record", "create", throw=True)
	doc = frappe.get_doc("Patient Encounter", encounter)
	doc.check_permission("read")
	if urgency not in URGENCIES:
		frappe.throw(_("Choose the urgency."))
	if not (reason or "").strip():
		frappe.throw(_("Give the reason for admission."))
	if ward not in wards():
		frappe.throw(_("{0} is not a ward with beds.").format(ward))
	open_ip = frappe.db.get_value(
		IR, {"patient": doc.patient, "status": ["in", ("Admission Scheduled", *ON_WARD)]}, "name"
	)
	if open_ip:
		frappe.throw(_("{0} already has an admission: {1}.").format(doc.patient_name, open_ip))
	ip = create_inpatient_record(
		{
			"patient": doc.patient,
			"admission_encounter": doc.name,
			"admission_practitioner": doc.practitioner,
			"primary_practitioner": doc.practitioner,
			"medical_department": doc.get("medical_department"),
			"admission_ordered_for": admission_date or nowdate(),
			"admission_service_unit_type": _bed_type(ward),
			"admission_instruction": notes,
			"expected_length_of_stay": cint(expected_days) or None,
		}
	)
	visit = doc.get("ke_patient_visit") and frappe.get_doc("Patient Visit", doc.ke_patient_visit)
	values = {
		"company": doc.company,
		"ke_ward": ward,
		"ke_urgency": urgency,
		"ke_admission_reason": reason.strip(),
		"ke_patient_visit": visit.name if visit else None,
	}
	hours = _preauth_needed(visit)
	if hours:
		values.update(
			ke_preauth_status="Pending",
			ke_preauth_due=add_to_date(now_datetime(), hours=hours),
			insurance_payor=visit.insurance_payor,
			insurance_policy=visit.insurance_policy,
		)
	frappe.db.set_value(IR, ip, values)
	if visit and visit.status == "Open":
		_visit_to_admission(visit, ward, urgency)
	return ip


def _visit_to_admission(visit, ward, urgency):
	"""The visit's queue moves to Admission. A visit that can't be saved (its
	own details incomplete) never stops the admission: noted, not raised."""
	from royce_health_ke import flow

	frappe.db.savepoint("ke_visit_admission")
	try:
		flow.move(visit, "Admission", flow.SENT, note=_("Admitted to {0} ({1})").format(ward, _(urgency)))
		visit.flags.ignore_permissions = True
		visit.save()
	except frappe.ValidationError as e:
		frappe.db.rollback(save_point="ke_visit_admission")
		frappe.clear_last_message()
		frappe.msgprint(
			_("Admission requested, but visit {0} was not moved to Admission: {1}").format(visit.name, e),
			indicator="orange",
			alert=True,
		)


# The Ward page


def _days(since):
	if not since:
		return 0
	return max((getdate() - getdate(since)).days, 0)


@frappe.whitelist()
def admission_list(ward: str | None = None) -> dict:
	"""Awaiting admission, and on the ward, for the Ward page."""
	_check(WARD_ROLES)
	fields = [
		"name",
		"patient",
		"patient_name",
		"gender",
		"dob",
		"status",
		"scheduled_date",
		"admission_ordered_for",
		"admitted_datetime",
		"primary_practitioner",
		"ke_ward",
		"ke_urgency",
		"ke_admission_reason",
		"ke_preauth_status",
		"insurance_payor",
		"ke_transfer_to",
		"ke_transfer_reason",
		"ke_transfer_urgency",
		"ke_transfer_requested_at",
	]
	waiting = frappe.get_all(
		IR, filters={"status": "Admission Scheduled"}, fields=fields, order_by="creation"
	)
	on_ward = frappe.get_all(
		IR, filters={"status": ["in", ON_WARD]}, fields=fields, order_by="admitted_datetime"
	)
	urgency_rank = {u: i for i, u in enumerate(reversed(URGENCIES))}
	out_waiting, out_ward, incoming = [], [], []
	for r in waiting:
		if ward and r.ke_ward != ward:
			continue
		out_waiting.append(r)
	out_waiting.sort(key=lambda r: (urgency_rank.get(r.ke_urgency, 9), str(r.admission_ordered_for)))
	for r in on_ward:
		r.ward = ward_of(r.name)
		if r.ke_transfer_to and (not ward or r.ke_transfer_to == ward) and r.ke_transfer_to != r.ward:
			incoming.append(r)
		if ward and r.ward != ward:
			continue
		bed = current_bed(r.name)
		r.bed = bed.service_unit if bed else None
		r.days = _days(r.admitted_datetime)
		r.doses_due = frappe.db.count(
			"Medication Administration",
			{
				"inpatient_record": r.name,
				"status": "Scheduled",
				"scheduled_time": ["<=", add_to_date(now_datetime(), hours=1)],
			},
		)
		r.theatre = frappe.db.get_value(
			"Theatre Booking",
			{
				"inpatient_record": r.name,
				"status": ["in", ["Scheduled", "In Theatre"]],
				"docstatus": ["<", 2],
			},
			["status", "scheduled_start"],
			as_dict=True,
			order_by="scheduled_start asc",
		)
		out_ward.append(r)
	incoming.sort(key=lambda r: (urgency_rank.get(r.ke_transfer_urgency, 9), str(r.ke_transfer_requested_at)))
	for r in incoming:
		bed = current_bed(r.name)
		r.bed = bed.service_unit if bed else None
	return {"waiting": out_waiting, "on_ward": out_ward, "incoming": incoming, "wards": wards()}


@frappe.whitelist()
def admit(inpatient_record: str, bed: str) -> str:
	"""Receive the patient on the ward: a vacant bed (Marley's admission)."""
	_check(ADMIT_ROLES)
	doc = frappe.get_doc(IR, inpatient_record)
	if doc.status != "Admission Scheduled":
		frappe.throw(_("{0} is not waiting for admission.").format(doc.patient_name))
	doc.admit(bed, now_datetime())
	return doc.name


# Transfer to another ward (Bethesda, 20 Nov 2026: "we send patient and get as
# a request in the next tab/module"): the ward the patient is on asks, and the
# receiving ward sees the patient under Incoming Transfers and gives a bed.

TRANSFER_FIELDS = (
	"ke_transfer_to",
	"ke_transfer_reason",
	"ke_transfer_urgency",
	"ke_transfer_requested_by",
	"ke_transfer_requested_at",
)


@frappe.whitelist()
def request_transfer(inpatient_record: str, ward: str, reason: str, urgency: str = "Routine") -> str:
	_check(WARD_ROLES)
	doc = frappe.get_doc(IR, inpatient_record)
	doc.check_permission("read")
	if doc.status not in ON_WARD:
		frappe.throw(_("{0} is not on a ward.").format(doc.patient_name))
	if ward not in wards():
		frappe.throw(_("{0} is not a ward.").format(ward))
	if ward == ward_of(doc.name):
		frappe.throw(_("{0} is already on {1}.").format(doc.patient_name, ward))
	if not (reason or "").strip():
		frappe.throw(_("Give the reason for the transfer."))
	if urgency not in URGENCIES:
		frappe.throw(_("Choose the urgency."))
	frappe.db.set_value(
		IR,
		doc.name,
		{
			"ke_transfer_to": ward,
			"ke_transfer_reason": reason.strip(),
			"ke_transfer_urgency": urgency,
			"ke_transfer_requested_by": frappe.session.user,
			"ke_transfer_requested_at": now_datetime(),
		},
	)
	doc.add_comment("Info", _("Transfer to {0} requested: {1}").format(ward, reason.strip()))
	return ward


@frappe.whitelist()
def cancel_transfer(inpatient_record: str) -> None:
	_check(WARD_ROLES)
	doc = frappe.get_doc(IR, inpatient_record)
	doc.check_permission("read")
	if doc.get("ke_transfer_to"):
		doc.add_comment("Info", _("Transfer to {0} cancelled").format(doc.ke_transfer_to))
	frappe.db.set_value(IR, doc.name, dict.fromkeys(TRANSFER_FIELDS))


@frappe.whitelist()
def receive_transfer(inpatient_record: str, bed: str) -> str:
	"""The receiving ward gives a vacant bed: the old bed is left (checked out,
	vacant) and the new one taken (Marley's transfer)."""
	_check(ADMIT_ROLES)
	doc = frappe.get_doc(IR, inpatient_record)
	to = doc.get("ke_transfer_to")
	if not to:
		frappe.throw(_("No transfer was asked for {0}.").format(doc.patient_name))
	if frappe.db.get_value("Healthcare Service Unit", bed, "parent_healthcare_service_unit") != to:
		frappe.throw(_("{0} is not a bed on {1}.").format(bed, to))
	old = current_bed(doc.name)
	from_ward = ward_of(doc.name)
	doc.transfer(bed, now_datetime(), leave_from=old.service_unit if old else None)
	doc.reload()
	doc.db_set({"ke_ward": to, **dict.fromkeys(TRANSFER_FIELDS)})
	doc.add_comment("Info", _("Transferred from {0} to {1}, bed {2}").format(from_ward, to, bed))
	return bed


# The patient screen


@frappe.whitelist()
def workspace(inpatient_record: str, booking: str | None = None) -> dict:
	"""The banner and the tab bar of one admission; with a theatre booking,
	the theatre's tabs."""
	_check(WARD_ROLES)
	ip = frappe.get_doc(IR, inpatient_record)
	ip.check_permission("read")
	theatre = None
	if booking:
		from royce_health_ke.theatre import booking_banner

		theatre = booking_banner(booking, ip.patient)
	from royce_health_ke.visits import age_label

	patient = frappe.db.get_value(
		"Patient", ip.patient, ["patient_name", "sex", "dob", "allergies", "blood_group"], as_dict=True
	)
	bed = current_bed(ip.name)
	profile = (
		_setting("theatre_workspace_profile", THEATRE_PROFILE)
		if theatre
		else _setting("inpatient_workspace_profile", DEFAULT_PROFILE)
	)
	tabs = frappe.get_all(
		"Patient Workspace Tab",
		filters={"parent": profile, "parenttype": "Patient Workspace Profile", "hidden": 0},
		fields=["panel", "label"],
		order_by="idx",
	) or [{"panel": p, "label": p} for p in (THEATRE_PANELS if theatre else PANELS)]
	return {
		"name": ip.name,
		"patient": ip.patient,
		"patient_name": patient.patient_name,
		"sex": patient.sex,
		"age": age_label(patient.dob) if patient.dob else "",
		"allergies": patient.allergies,
		"blood_group": patient.blood_group,
		"status": ip.status,
		"ward": ward_of(ip.name),
		"bed": bed.service_unit if bed else None,
		"admitted": ip.admitted_datetime,
		"days": _days(ip.admitted_datetime),
		"practitioner": ip.primary_practitioner,
		"practitioner_name": frappe.db.get_value(
			"Healthcare Practitioner", ip.primary_practitioner, "practitioner_name"
		)
		if ip.primary_practitioner
		else None,
		"urgency": ip.get("ke_urgency"),
		"reason": ip.get("ke_admission_reason"),
		"payer": ip.insurance_payor or _("Cash"),
		"preauth": ip.get("ke_preauth_status"),
		"preauth_due": ip.get("ke_preauth_due"),
		"transfer_to": ip.get("ke_transfer_to"),
		"transfer_reason": ip.get("ke_transfer_reason"),
		"money": money(ip),
		"tabs": tabs,
		"theatre": theatre,
	}


def admission_encounters(ip):
	doc = frappe.db.get_value(IR, ip, ["patient", "admission_encounter"], as_dict=True)
	names = frappe.get_all(
		"Patient Encounter", filters={"inpatient_record": ip, "docstatus": ["<", 2]}, pluck="name"
	)
	if doc.admission_encounter and doc.admission_encounter not in names:
		names.insert(0, doc.admission_encounter)
	return names


@frappe.whitelist()
def panel(inpatient_record: str, panel: str, booking: str | None = None) -> dict:
	"""One tab's data."""
	_check(WARD_ROLES)
	ip = frappe.get_doc(IR, inpatient_record)
	ip.check_permission("read")
	if panel == "Theatre Doctor Notes":
		from royce_health_ke import theatre

		if not booking:
			return {"notes": [], "no_booking": 1}
		theatre.booking_banner(booking, ip.patient)
		return theatre.doctor_notes(booking)
	handler = PANEL_DATA.get(panel)
	return handler(ip) if handler else {}


def _requests(ip):
	encounters = admission_encounters(ip.name)
	rows = frappe.get_all(
		"Service Request",
		filters={"order_group": ["in", encounters or [""]], "docstatus": 1},
		fields=[
			"name",
			"template_dn",
			"status",
			"ke_service_point",
			"order_date",
			"order_time",
			"practitioner_name",
			"order_group",
		],
		order_by="creation desc",
	)
	for r in rows:
		r.status_label = r.status.split("-Request")[0].replace("-", " ").title() if r.status else ""
	return {"requests": rows, "encounters": encounters}


def _results(ip):
	since = ip.admitted_datetime or ip.scheduled_date or ip.creation
	from royce_health_ke.printing import lab_results

	labs = []
	for name in frappe.get_all(
		"Lab Test",
		filters={"patient": ip.patient, "docstatus": ["<", 2], "creation": [">=", since]},
		pluck="name",
		order_by="creation desc",
	):
		t = frappe.get_doc("Lab Test", name)
		labs.append(
			{
				"name": t.name,
				"test": t.lab_test_name or t.template,
				"validated": t.docstatus == 1,
				"rows": lab_results(t) if t.docstatus == 1 else [],
			}
		)
	imaging = frappe.get_all(
		"Observation",
		filters={
			"patient": ip.patient,
			"parent_observation": ["is", "not set"],
			"creation": [">=", since],
			"ke_exam_status": ["is", "set"],
		},
		fields=[
			"name",
			"observation_template",
			"ke_exam_status",
			"result",
			"ke_impression",
			"ke_accession_number",
			"ke_pacs_link",
			"patient",
		],
		order_by="creation desc",
	)
	from royce_health_ke.radiology import viewer_url

	for i in imaging:
		i.images = viewer_url(i)
	return {"labs": labs, "imaging": imaging}


def _diagnosis(ip):
	from royce_health_ke.printing import diagnosis_lines

	out = []
	for name in admission_encounters(ip.name):
		e = frappe.get_doc("Patient Encounter", name)
		for d in diagnosis_lines(e):
			out.append(
				{"diagnosis": d.name, "code": d.code, "date": e.encounter_date, "by": e.practitioner_name}
			)
	return {"diagnoses": out}


def _vitals(ip):
	from royce_health_ke.consultation import vitals_history

	return {"rows": vitals_history(ip.patient)}


def shift_of(when):
	"""The nursing shift a time falls in (Kenya Health Settings > Shifts)."""
	when = get_datetime(when)
	t = when.time()
	for s in shifts():
		start, end = s["start"], s["end"]
		inside = start <= t < end if start < end else (t >= start or t < end)
		if inside:
			return s["name"]
	return ""


def shifts():
	from datetime import time

	rows = frappe.get_all(
		"Nursing Shift",
		filters={"parenttype": SETTINGS},
		fields=["shift_name", "start_time", "end_time"],
		order_by="idx",
	)

	def as_time(value):
		if isinstance(value, time):
			return value
		seconds = int(value.total_seconds()) if hasattr(value, "total_seconds") else 0
		return time(seconds // 3600 % 24, seconds % 3600 // 60)

	if not rows:
		return [
			{"name": _("Day"), "start": time(7, 0), "end": time(19, 0)},
			{"name": _("Night"), "start": time(19, 0), "end": time(7, 0)},
		]
	return [{"name": r.shift_name, "start": as_time(r.start_time), "end": as_time(r.end_time)} for r in rows]


def _notes(ip):
	return {"notes": _clinical_notes(ip, exclude=DOCTOR_TYPES)}


def _clinical_notes(ip, only=None, exclude=None):
	since = ip.admitted_datetime or ip.creation
	filters = {"patient": ip.patient, "docstatus": ["<", 2], "creation": [">=", since]}
	if only:
		filters["clinical_note_type"] = ["in", only]
	elif exclude:
		filters["clinical_note_type"] = ["not in", exclude]
	notes = frappe.get_all(
		"Clinical Note",
		filters=filters,
		fields=[
			"name",
			"clinical_note_type",
			"posting_date",
			"creation",
			"user",
			"note",
			"fdar_focus",
			"fdar_data",
			"fdar_action",
			"fdar_response",
			"ke_patient_status",
		],
		order_by="creation desc",
		limit=200,
	)
	for n in notes:
		n.shift = shift_of(n.creation)
		n.by = frappe.utils.get_fullname(n.user) if n.user else ""
	return notes


def _care(ip):
	from royce_health_ke import charts, partograph

	out = charts.panel(ip, skip=[TB_CHART])
	if partograph.applies(ip):
		out["charts"].append(partograph.entry(ip))
	return out


def _tb(ip):
	from royce_health_ke import charts

	return charts.panel(ip, only=[TB_CHART])


def _doctor_notes(ip):
	return {"notes": _clinical_notes(ip, only=[DOCTOR_NOTE]), "note_type": DOCTOR_NOTE}


def _doctor_instructions(ip):
	return {"notes": _clinical_notes(ip, only=[DOCTOR_INSTRUCTIONS]), "note_type": DOCTOR_INSTRUCTIONS}


def _consent(ip):
	return {
		"consents": frappe.get_all(
			"Surgical Consent",
			filters={"patient": ip.patient, "docstatus": ["<", 2]},
			fields=[
				"name",
				"procedure_template",
				"consent_datetime",
				"consent_by",
				"consenter_name",
				"docstatus",
			],
			order_by="creation desc",
		)
	}


def _disposition(ip):
	return {
		"outcome": ip.get("ke_discharge_outcome"),
		"referred_to": ip.get("ke_referred_to"),
		"note": ip.get("ke_disposition_note"),
		"outcomes": OUTCOMES,
		"status": ip.status,
	}


@frappe.whitelist()
def record_note(
	inpatient_record: str,
	note_type: str,
	note: str,
	patient_status: str | None = None,
	posting_date: str | None = None,
) -> str:
	"""A note on the ward: the doctor's progress note or instructions to the nurses."""
	if note_type in DOCTOR_TYPES:
		_check(("Physician", "Healthcare Administrator", "System Manager"))
	else:
		_check(WARD_ROLES)
	if not (note or "").strip():
		frappe.throw(_("Write the note."))
	ip = frappe.get_doc(IR, inpatient_record)
	ip.check_permission("read")
	practitioner = frappe.db.get_value("Healthcare Practitioner", {"user_id": frappe.session.user}, "name")
	doc = frappe.get_doc(
		{
			"doctype": "Clinical Note",
			"patient": ip.patient,
			"clinical_note_type": note_type,
			"note": note.strip(),
			"posting_date": posting_date or now_datetime(),
			"practitioner": practitioner,
			"user": frappe.session.user,
			"reference_doc": IR,
			"reference_name": ip.name,
			"ke_patient_status": patient_status or None,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


@frappe.whitelist()
def set_disposition(
	inpatient_record: str, outcome: str, referred_to: str | None = None, note: str | None = None
) -> None:
	"""How the admission ends (MOH 717 counts it): discharged, referred out
	(and where), absconded or died."""
	_check(("Physician", "Healthcare Administrator", "System Manager"))
	if outcome not in OUTCOMES:
		frappe.throw(_("Choose the outcome."))
	if outcome == "Referred Out" and not (referred_to or "").strip():
		frappe.throw(_("Say which facility the patient is referred to."))
	frappe.get_doc(IR, inpatient_record).check_permission("write")
	frappe.db.set_value(
		IR,
		inpatient_record,
		{
			"ke_discharge_outcome": outcome,
			"ke_referred_to": (referred_to or "").strip() or None,
			"ke_disposition_note": note,
		},
	)


def _drugs(ip):
	orders = frappe.get_all(
		"Inpatient Medication Order",
		filters={"inpatient_record": ip.name, "docstatus": 1},
		fields=["name", "patient_encounter", "practitioner", "start_date", "end_date", "status"],
		order_by="creation desc",
	)
	entries = frappe.get_all(
		"Inpatient Medication Order Entry",
		filters={"parent": ["in", [o.name for o in orders] or [""]]},
		fields=["parent", "name", "drug", "drug_name", "dosage", "date", "time", "status", "instructions"],
		order_by="date, time",
	)
	by_drug = {}
	for e in entries:
		key = (e.parent, e.drug)
		d = by_drug.setdefault(
			key,
			{
				"order": e.parent,
				"drug": e.drug,
				"drug_name": e.drug_name,
				"dose": e.dosage,
				"instructions": e.instructions,
				"counts": {},
				"next": None,
			},
		)
		d["counts"][e.status] = d["counts"].get(e.status, 0) + 1
		when = get_datetime(f"{e.date} {e.time or '00:00:00'}")
		if e.status in ("Pending", "Transferred") and when >= now_datetime() and not d["next"]:
			d["next"] = when
	doses = frappe.get_all(
		"Medication Administration",
		filters={"inpatient_record": ip.name},
		fields=[
			"name",
			"drug_name",
			"dosage",
			"route",
			"scheduled_time",
			"administered_time",
			"status",
			"administered_by",
			"reason",
		],
		order_by="scheduled_time desc",
		limit=100,
	)
	for d in doses:
		d.by = frappe.utils.get_fullname(d.administered_by) if d.administered_by else ""
	return {
		"active": list(by_drug.values()),
		"doses": doses,
		"charge": _setting("ward_drug_charge", ON_ISSUE),
	}


def _billing(ip):
	return money(ip, detail=True)


def _discharge(ip):
	summary = frappe.db.get_value(
		"Discharge Summary",
		{"inpatient_record": ip.name, "docstatus": ["<", 2]},
		["name", "docstatus"],
		as_dict=True,
	)
	return {
		"status": ip.status,
		"discharge_ordered_date": ip.discharge_ordered_date,
		"discharge_instructions": ip.discharge_instructions,
		"followup_date": ip.followup_date,
		"summary": summary,
	}


def _patient_file(ip):
	return {
		"patient": ip.patient,
		"reason": ip.get("ke_admission_reason"),
		"instruction": ip.admission_instruction,
		"encounter": ip.admission_encounter,
	}


PANEL_DATA = {
	"Patient File": _patient_file,
	"Vitals": _vitals,
	"Requests": _requests,
	"Results": _results,
	"Diagnosis": _diagnosis,
	"Nursing Notes": _notes,
	"Nursing Care": _care,
	"TB Screening": _tb,
	"Doctor Notes": _doctor_notes,
	"Doctor Instructions": _doctor_instructions,
	"Consent": _consent,
	"Disposition": _disposition,
	"Drug Administration": _drugs,
	"Billing": _billing,
	"Discharge": _discharge,
}


# Money: the running bill and what is paid


def money(ip, detail=False):
	"""The admission's running cost (billed + not yet billed) against what is
	paid, and the deposit asked for cash admissions."""
	from royce_health_ke import fees

	since = getdate(ip.admitted_datetime or ip.scheduled_date or ip.creation)
	customer = frappe.db.get_value("Patient", ip.patient, "customer")
	invoices = (
		frappe.get_all(
			"Sales Invoice",
			filters={"patient": ip.patient, "docstatus": 1, "posting_date": [">=", since]},
			fields=["name", "posting_date", "grand_total", "outstanding_amount"],
		)
		if customer
		else []
	)
	billed = sum(flt(i.grand_total) for i in invoices)
	outstanding = sum(flt(i.outstanding_amount) for i in invoices)
	lines = []
	# beds: each occupancy's days at its bed type's price
	for occ in ip.inpatient_occupancies or []:
		if occ.invoiced:
			continue
		unit_type = frappe.db.get_value("Healthcare Service Unit", occ.service_unit, "service_unit_type")
		item = unit_type and frappe.db.get_value("Healthcare Service Unit Type", unit_type, "item")
		end = get_datetime(occ.check_out) if occ.left and occ.check_out else now_datetime()
		days = max(math.ceil((end - get_datetime(occ.check_in)).total_seconds() / 86400), 1)
		rate = fees.price(item, ip.company) if item else 0
		lines.append(
			{"what": _("Bed {0}").format(occ.service_unit), "qty": days, "rate": rate, "amount": days * rate}
		)
	for item in ip.items or []:
		# drugs and consumables issued (Marley bills a row once it carries its
		# stock entry); bed rent rows repeat the occupancy counted above
		if item.invoiced or not item.stock_entry:
			continue
		rate = flt(item.rate) or fees.price(item.item_code, ip.company)
		lines.append(
			{
				"what": item.item_name or item.item_code,
				"qty": flt(item.quantity),
				"rate": rate,
				"amount": flt(item.quantity) * rate,
			}
		)
	for r in _requests(ip)["requests"]:
		if r.status in ("revoked-Request Status", "entered-in-error-Request Status"):
			continue
		if frappe.db.exists(
			"Sales Invoice Item", {"reference_dt": "Service Request", "reference_dn": r.name, "docstatus": 1}
		):
			continue
		template = frappe.db.get_value(
			"Service Request", r.name, ["template_dt", "template_dn"], as_dict=True
		)
		item = template and frappe.db.get_value(template.template_dt, template.template_dn, "item")
		rate = fees.price(item, ip.company, ip.insurance_policy) if item else 0
		lines.append({"what": r.template_dn, "qty": 1, "rate": rate, "amount": rate})
	unbilled = sum(flt(line["amount"]) for line in lines)
	paid = 0
	if customer:
		paid = flt(
			frappe.db.sql(
				"""select sum(paid_amount) from `tabPayment Entry`
				where docstatus = 1 and payment_type = 'Receive' and party_type = 'Customer'
					and party = %s and posting_date >= %s""",
				(customer, since),
			)[0][0]
		)
	total = billed + unbilled
	cash = not ip.insurance_payor
	deposit = flt(_setting("admission_deposit", 0)) if cash else 0
	out = {
		"total": total,
		"billed": billed,
		"unbilled": unbilled,
		"outstanding": outstanding,
		"paid": paid,
		"deposit": deposit,
		"cash": cash,
		"over": bool(cash and total > paid),
		"short": max(total - paid, 0) if cash else 0,
	}
	if detail:
		out.update(lines=lines, invoices=invoices)
	return out


# Ward rounds prescribe: the medicines become the ward medication order

DAY_START = 6  # the first dose of the day, hours


def row_times(row):
	"""The day's dose times of a prescription row: every N hours from its start
	time (or 06:00) when scheduled by interval, else its frequency's times."""
	if cint(row.get("dosage_by_interval")) and cint(row.get("interval")):
		hours = cint(row.interval) * (24 if row.get("interval_uom") == "Day" else 1)
		if hours >= 24:
			first = str(row.get("ke_start_time") or f"{DAY_START:02d}:00:00")
			return [first if len(first) == 8 else first.zfill(8)]
		start = DAY_START
		if row.get("ke_start_time"):
			h, m = (int(x) for x in str(row.ke_start_time).split(":")[:2])
			start = h + m / 60
		times = sorted({(start + i * hours) % 24 for i in range(int(24 // hours))})
		return [f"{int(t):02d}:{round(t % 1 * 60) % 60:02d}:00" for t in times]
	return dose_times(row.dosage)


def dose_times(dosage):
	"""The times of a frequency's doses: those set on the Prescription Dosage,
	else spread over the day from 06:00 (three a day: 06:00, 14:00, 22:00)."""
	from royce_health_ke.dispensing import times_a_day

	doc = frappe.get_cached_doc("Prescription Dosage", dosage)
	times = [r.strength_time for r in doc.get("dosage_strength") or [] if r.strength_time]
	if times:
		return [str(t) for t in times]
	n = times_a_day(dosage) or 1
	step = 24 / n
	return [
		f"{int(DAY_START + i * step) % 24:02d}:{int((DAY_START + i * step) % 1 * 60):02d}:00"
		for i in range(n)
	]


def dose_quantity(row):
	"""Stock units given per dose: the dose over the pack size when written in
	clinical units, else Marley's strength (units per dose)."""
	from royce_health_ke.dispensing import item_for, pack_size

	item = row.get("drug_code") or item_for(row.get("medication"))
	if flt(row.get("ke_dose")):
		size = pack_size(row.get("medication"), row.get("ke_dose_uom"), item)
		if size:
			return round(flt(row.ke_dose) / size, 3)
	doc = frappe.get_cached_doc("Prescription Dosage", row.dosage) if row.get("dosage") else None
	strengths = [flt(r.strength) for r in (doc.get("dosage_strength") if doc else []) if flt(r.strength)]
	return strengths[0] if strengths else 1


def order_from_encounter(doc, method=None):
	"""Patient Encounter on_submit, inpatient: the medicines prescribed on the
	ward round become a submitted Inpatient Medication Order (its doses per
	day at the frequency's times, for the duration, from the start date)."""
	if not doc.get("inpatient_record") or frappe.db.exists(
		"Inpatient Medication Order", {"patient_encounter": doc.name, "docstatus": ["<", 2]}
	):
		return
	from royce_health_ke.dispensing import days as duration_days
	from royce_health_ke.dispensing import item_for

	rows = [
		d
		for d in doc.drug_prescription
		if (d.drug_code or d.medication)
		and d.period
		and (d.dosage or (cint(d.get("dosage_by_interval")) and cint(d.get("interval"))))
	]
	if not rows:
		return
	order = frappe.new_doc("Inpatient Medication Order")
	order.update(
		{
			"patient_encounter": doc.name,
			"patient": doc.patient,
			"patient_name": doc.patient_name,
			"inpatient_record": doc.inpatient_record,
			"practitioner": doc.practitioner,
			"company": doc.company,
			"start_date": doc.encounter_date,
		}
	)
	end = getdate(doc.encounter_date)
	for d in rows:
		item = d.drug_code or item_for(d.medication)
		if not item:
			continue
		start = getdate(d.get("ke_start_date") or doc.encounter_date)
		first_time = d.get("ke_start_time")
		n_days = max(math.ceil(duration_days(d.period)), 1)
		quantity = dose_quantity(d)
		for day in range(n_days):
			date = add_days(start, day)
			for t in row_times(d):
				if day == 0 and first_time and t < str(first_time):
					continue
				order.append(
					"medication_orders",
					{
						"drug": item,
						"drug_name": d.drug_name or frappe.db.get_value("Item", item, "item_name"),
						"dosage": quantity,
						"dosage_form": d.dosage_form,
						"date": date,
						"time": t,
						"instructions": d.comment,
						"medication_request": d.get("medication_request"),
					},
				)
			end = max(end, getdate(date))
	if not order.medication_orders:
		return
	order.end_date = end
	order.flags.ignore_permissions = True
	order.insert()
	order.submit()


@frappe.whitelist()
def stop_drug(order: str, drug: str, reason: str) -> int:
	"""Stop a drug on the ward round: its doses not yet given are stopped."""
	_check(("Physician", "Healthcare Administrator", "System Manager"))
	if not (reason or "").strip():
		frappe.throw(_("Give the reason for stopping."))
	doc = frappe.get_doc("Inpatient Medication Order", order)
	entries = [
		e.name for e in doc.medication_orders if e.drug == drug and e.status in ("Pending", "Transferred")
	]
	if not entries:
		frappe.throw(_("No doses of {0} left to stop.").format(drug))
	doc.stop_medication_orders(entries, reason.strip())
	return len(entries)


# Ward drugs charged on issue: the pharmacy's issue goes on the admission's bill


def bill_on_issue(doc, method=None):
	"""Inpatient Medication Entry on_submit, charging on issue (Marley's ward
	stock off): each issued drug becomes a billable row of its admission,
	carrying the stock entry, so the discharge invoice charges it."""
	from royce_health_ke.marley import manages_medication_stock

	if manages_medication_stock():
		return  # the dose given bills it (Marley)
	stock_entry = frappe.db.get_value(
		"Stock Entry", {"inpatient_medication_entry": doc.name, "docstatus": 1}, "name"
	)
	if not stock_entry:
		return
	by_admission = {}
	for row in doc.medication_orders:
		if row.get("inpatient_record"):
			key = (row.inpatient_record, row.drug_code)
			by_admission[key] = by_admission.get(key, 0) + flt(row.dosage)
	for (ip, item), qty in by_admission.items():
		admission = frappe.get_doc(IR, ip)
		item_name, uom = frappe.db.get_value("Item", item, ["item_name", "stock_uom"])
		admission.append(
			"items",
			{
				"item_code": item,
				"item_name": item_name,
				"quantity": qty,
				"uom": uom,
				"stock_uom": uom,
				"conversion_factor": 1,
				"stock_entry": stock_entry,
			},
		)
		admission.save(ignore_permissions=True)


# The pharmacy's ward requests


@frappe.whitelist()
def ward_requests(hours: int = 24) -> list:
	"""Ward medication not yet sent: per patient, the doses due within `hours`."""
	from royce_health_ke.pharmacy import _check_access

	_check_access()
	until = add_to_date(now_datetime(), hours=cint(hours) or 24)
	rows = frappe.db.sql(
		"""select o.patient, o.patient_name, o.inpatient_record, e.drug, e.drug_name,
			count(*) as doses, sum(e.dosage) as quantity, min(timestamp(e.date, e.time)) as first_due
		from `tabInpatient Medication Order Entry` e
		join `tabInpatient Medication Order` o on o.name = e.parent
		join `tabInpatient Record` ip on ip.name = o.inpatient_record
		where o.docstatus = 1 and e.status = 'Pending' and ip.status in ('Admitted', 'Discharge Scheduled')
			and timestamp(e.date, e.time) <= %s
		group by o.patient, o.patient_name, o.inpatient_record, e.drug, e.drug_name
		order by first_due""",
		until,
		as_dict=True,
	)
	for r in rows:
		r.ward = ward_of(r.inpatient_record)
		bed = current_bed(r.inpatient_record)
		r.bed = bed.service_unit if bed else None
	return rows


@frappe.whitelist()
def issue_to_ward(patient: str, warehouse: str, hours: int = 24) -> str:
	"""Send a patient's ward medication due within `hours`: Marley's Inpatient
	Medication Entry from the pharmacy store, submitted."""
	from royce_health_ke.pharmacy import _check_access

	_check_access()
	if not warehouse:
		frappe.throw(_("Choose the pharmacy store the drugs leave from."))
	until = add_to_date(now_datetime(), hours=cint(hours) or 24)
	ip = frappe.db.get_value(
		IR, {"patient": patient, "status": ["in", ON_WARD]}, ["name", "company"], as_dict=True
	)
	if not ip:
		frappe.throw(_("This patient is not on a ward."))
	entry = frappe.new_doc("Inpatient Medication Entry")
	entry.update(
		{
			"company": ip.company,
			"posting_date": nowdate(),
			"warehouse": warehouse,
			"patient": patient,
			"from_date": add_days(nowdate(), -7),
			"to_date": getdate(until),
			"update_stock": 1,
		}
	)
	entry.get_medication_orders()
	entry.medication_orders = [r for r in entry.medication_orders if get_datetime(r.datetime) <= until]
	if not entry.medication_orders:
		frappe.throw(_("No ward medication due for this patient."))
	entry.flags.ignore_permissions = True
	entry.insert()
	entry.submit()
	return entry.name


# Pre-authorisation


@frappe.whitelist()
def record_preauth(inpatient_record: str, code: str) -> None:
	"""The payer's pre-authorisation code for the admission."""
	_check(("Healthcare Administrator", "System Manager", "Receptionist", "Cashier", "Nursing User"))
	if not (code or "").strip():
		frappe.throw(_("Enter the pre-authorisation code."))
	frappe.db.set_value(
		IR, inpatient_record, {"ke_preauth_status": "Received", "ke_preauth_code": code.strip()}
	)


def hold_claim_without_preauth(doc, method=None):
	"""Insurance Claim before_submit: an admission waiting for its
	pre-authorisation holds the claim (never the care)."""
	ip = doc.get("inpatient_record")
	if ip and frappe.db.get_value(IR, ip, "ke_preauth_status") == "Pending":
		frappe.throw(
			_("Admission {0} is waiting for the payer's pre-authorisation code. Record it first.").format(ip),
			title=_("Pre-authorisation pending"),
		)


# Daily: the billing desk hears about cash admissions over what is paid


def notify_over_deposit():
	if _setting("over_deposit_action", "Warn") != "Warn and notify billing":
		return
	over = []
	for name in frappe.get_all(
		IR, filters={"status": ["in", ON_WARD], "insurance_payor": ["in", ("", None)]}, pluck="name"
	):
		m = money(frappe.get_doc(IR, name))
		if m["over"]:
			over.append(name)
	if not over:
		return
	users = frappe.get_all(
		"Has Role",
		filters={"role": ["in", ("Cashier", "Healthcare Administrator")], "parenttype": "User"},
		pluck="parent",
		distinct=True,
	)
	for user in users:
		if user in ("Administrator", "Guest") or not frappe.db.get_value("User", user, "enabled"):
			continue
		frappe.get_doc(
			{
				"doctype": "Notification Log",
				"for_user": user,
				"type": "Alert",
				"document_type": IR,
				"subject": _("{0} cash admission(s) with a bill above what is paid: {1}").format(
					len(over), ", ".join(over)
				),
			}
		).insert(ignore_permissions=True)


# Seeds


def seed():
	"""The default patient screens, ward and theatre (each once; afterwards the
	hospital's)."""
	first = not frappe.db.exists("Patient Workspace Profile", DEFAULT_PROFILE)
	for name, setting, care_setting, panels in (
		(DEFAULT_PROFILE, "inpatient_workspace_profile", "Inpatient", PANELS),
		(THEATRE_PROFILE, "theatre_workspace_profile", "Theatre", THEATRE_PANELS),
	):
		if not frappe.db.exists("Patient Workspace Profile", name):
			frappe.get_doc(
				{
					"doctype": "Patient Workspace Profile",
					"profile_name": name,
					"care_setting": care_setting,
					"tabs": [{"panel": p, "label": p} for p in panels],
				}
			).insert(ignore_permissions=True)
		if not frappe.db.get_single_value(SETTINGS, setting):
			frappe.db.set_single_value(SETTINGS, setting, name)
	if first and not frappe.get_all("Nursing Shift", filters={"parenttype": SETTINGS}, limit=1):
		settings = frappe.get_single(SETTINGS)
		settings.append(
			"nursing_shifts", {"shift_name": "Day", "start_time": "07:00:00", "end_time": "19:00:00"}
		)
		settings.append(
			"nursing_shifts", {"shift_name": "Night", "start_time": "19:00:00", "end_time": "07:00:00"}
		)
		settings.flags.ignore_permissions = True
		settings.save()


# The discharge summary's record of the stay


def admission_record(ip_name):
	"""Everything that happened during the admission, for the discharge
	summary: reason and diagnoses, vital signs, nursing notes and charts,
	medicines given, results, procedures and the bill."""
	if not ip_name or not frappe.db.exists(IR, ip_name):
		return frappe._dict()
	ip = frappe.get_doc(IR, ip_name)
	since = ip.admitted_datetime or ip.creation
	until = ip.discharge_datetime or now_datetime()
	window = ["between", [since, until]]
	vitals = frappe.get_all(
		"Vital Signs",
		filters={"patient": ip.patient, "docstatus": ["<", 2], "creation": window},
		fields=[
			"signs_date",
			"signs_time",
			"temperature",
			"pulse",
			"respiratory_rate",
			"bp",
			"ke_spo2",
			"ke_vitals_flags",
		],
		order_by="signs_date, signs_time",
	)
	notes = _notes(ip)["notes"]
	charts = {}
	for e in frappe.get_all(
		"Nursing Chart Entry",
		filters={"inpatient_record": ip.name},
		fields=["template", "recorded_at"],
		order_by="recorded_at",
	):
		c = charts.setdefault(e.template, frappe._dict(template=e.template, entries=0, last=None))
		c.entries += 1
		c.last = e.recorded_at
	medicines = {}
	for g in frappe.get_all(
		"Medication Administration", filters={"inpatient_record": ip.name}, fields=["drug_name", "status"]
	):
		counts = medicines.setdefault(g.drug_name, {})
		counts[g.status] = counts.get(g.status, 0) + 1
	results = _results(ip)
	procedures = frappe.get_all(
		"Clinical Procedure",
		filters={"patient": ip.patient, "docstatus": 1, "creation": window},
		fields=["procedure_template", "start_date", "practitioner"],
	)
	return frappe._dict(
		reason=ip.get("ke_admission_reason"),
		urgency=ip.get("ke_urgency"),
		diagnoses=_diagnosis(ip)["diagnoses"],
		vitals=vitals[-12:],
		vitals_count=len(vitals),
		abnormal_vitals=sum(1 for v in vitals if v.ke_vitals_flags),
		notes=list(reversed(notes))[-15:],
		doctor_notes=list(reversed(_clinical_notes(ip, only=[DOCTOR_NOTE])))[-10:],
		outcome=ip.get("ke_discharge_outcome"),
		referred_to=ip.get("ke_referred_to"),
		notes_count=len(notes),
		charts=list(charts.values()),
		medicines=[{"drug": k, "counts": v} for k, v in medicines.items()],
		labs=[t for t in results["labs"] if t["validated"]],
		imaging=[o for o in results["imaging"] if o.ke_exam_status in ("Reported", "Verified")],
		procedures=procedures,
		money=money(ip),
	)


# "A form and a table for every entry" on the patient screen (Bethesda, 20 Nov
# 2026): vitals, diagnosis and requests are entered on the tab itself.

VITAL_FIELDS = {
	"temperature": "temperature",
	"pulse": "pulse",
	"respiratory_rate": "respiratory_rate",
	"bp_systolic": "bp_systolic",
	"bp_diastolic": "bp_diastolic",
	"ke_spo2": "ke_spo2",
	"weight": "weight",
	"ke_height_cm": "ke_height_cm",
	"vital_signs_note": "vital_signs_note",
}


@frappe.whitelist()
def record_vitals(inpatient_record: str, values: str | dict, taken_at: str | None = None) -> str:
	"""Vital signs from the Vitals tab's form (in place of the Nursing Dialog)."""
	_check(WARD_ROLES)
	frappe.has_permission("Vital Signs", "create", throw=True)
	ip = frappe.get_doc(IR, inpatient_record)
	ip.check_permission("read")
	values = frappe.parse_json(values) if isinstance(values, str) else values or {}
	given = {f: values.get(f) for f in VITAL_FIELDS if values.get(f) not in (None, "")}
	if not set(given) - {"vital_signs_note"}:
		frappe.throw(_("Enter at least one reading."))
	when = get_datetime(taken_at) if taken_at else now_datetime()
	doc = frappe.get_doc(
		{
			"doctype": "Vital Signs",
			"patient": ip.patient,
			"inpatient_record": ip.name,
			"company": ip.company,
			"signs_date": when.date(),
			"signs_time": when.strftime("%H:%M:%S"),
			**{VITAL_FIELDS[f]: v for f, v in given.items()},
		}
	)
	if not frappe.get_meta("Vital Signs").has_field("ke_spo2"):
		doc.pop("ke_spo2", None)
	doc.insert()
	doc.submit()
	return doc.name


# Give Dose (v0.58): the Administration Log's form, as well as Marley's
# Medication Round dialog (Bethesda, 21 Nov 2026: "a form and its table").
DOSE_STATUSES = ("Given", "Held", "Refused", "Not Available")


@frappe.whitelist()
def due_doses(inpatient_record: str) -> list:
	"""The doses on this admission's round (due, held, refused, recently missed)."""
	from royce_health_ke.marley import get_due_medications

	_check(WARD_ROLES)
	ip = frappe.get_doc(IR, inpatient_record)
	ip.check_permission("read")
	if not (
		frappe.has_permission("Medication Administration", "write")
		and frappe.has_permission("Medication Administration", "create")
	):
		return []
	return [
		{
			"name": d.name,
			"drug_name": d.drug_name or d.drug_code,
			"dosage": d.dosage,
			"dosage_form": d.dosage_form,
			"route": d.route,
			"scheduled_time": d.scheduled_time,
			"status": d.status,
		}
		for d in get_due_medications(ip.patient)
		if frappe.db.get_value("Medication Administration", d.name, "inpatient_record") in (ip.name, None)
	]


@frappe.whitelist()
def give_dose(
	inpatient_record: str,
	administration: str,
	status: str,
	route: str | None = None,
	reason: str | None = None,
	second_check_by: str | None = None,
) -> str:
	"""Record one dose: given, or held / refused / not available with why.
	Marley's own record_administration, so the ward stock and the charge
	follow as from the Medication Round."""
	from royce_health_ke.marley import record_administration

	_check(WARD_ROLES)
	ip = frappe.get_doc(IR, inpatient_record)
	ip.check_permission("read")
	if status not in DOSE_STATUSES:
		frappe.throw(_("Choose what happened to the dose."))
	dose = frappe.db.get_value(
		"Medication Administration", administration, ["patient", "inpatient_record"], as_dict=True
	)
	if not dose or dose.patient != ip.patient or (dose.inpatient_record or ip.name) != ip.name:
		frappe.throw(_("This dose is not for this patient."))
	if status != "Given" and not (reason or "").strip():
		frappe.throw(_("Say why the dose was not given."))
	return record_administration(
		administration, status, reason=reason or None, route=route or None, second_check_by=second_check_by
	)


def _ward_round(ip):
	from royce_health_ke.prescribing import ward_encounter

	return frappe.get_doc("Patient Encounter", ward_encounter(ip.name))


@frappe.whitelist()
def add_diagnosis(inpatient_record: str, diagnosis: str | None = None, code_value: str | None = None) -> str:
	"""A diagnosis on today's ward round, from the Diagnosis tab."""
	_check(("Physician", "Healthcare Administrator", "System Manager"))
	ip = frappe.get_doc(IR, inpatient_record)
	ip.check_permission("read")
	from royce_health_ke import diagnosis as dx

	if (
		diagnosis
		and code_value
		and frappe.db.exists("Diagnosis", diagnosis)
		and not dx.icd11_of(diagnosis)[0]
	):
		# the hospital's diagnosis without a code keeps its name and takes this code (sync_rows)
		resolved = {"diagnosis": diagnosis, "code_value": code_value}
	else:
		resolved = dx.resolve(diagnosis=diagnosis, code_value=code_value) or {}
	name = resolved.get("diagnosis") or diagnosis
	if not name:
		frappe.throw(_("Choose the diagnosis or its ICD-11 code."))
	code = resolved.get("code_value") or code_value
	# every ward diagnosis is coded (MOH reporting, claims; Bethesda 21 Nov 2026):
	# a hospital diagnosis without a code gets the one chosen here (diagnosis.sync_rows)
	if not code:
		frappe.throw(
			_(
				"{0} has no ICD-11 code yet. Choose its ICD-11 Code too: it is saved on the diagnosis "
				"for next time."
			).format(frappe.bold(name)),
			title=_("ICD-11 code needed"),
		)
	doc = _ward_round(ip)
	doc.append("diagnosis", {"diagnosis": name, "ke_icd11_code": code})
	doc.save()
	return doc.name


REQUEST_TABLES = {
	"Lab Test": ("lab_test_prescription", "lab_test_code", "lab_test_comment"),
	"Imaging": ("lab_test_prescription", "observation_template", "lab_test_comment"),
	"Procedure": ("procedure_prescription", "procedure", "comments"),
	"Therapy": ("therapies", "therapy_type", None),
}
URGENCY_CODES = ("Routine", "Urgent", "ASAP", "STAT")


@frappe.whitelist()
def add_request(
	inpatient_record: str,
	category: str,
	template: str,
	urgency: str | None = None,
	note: str | None = None,
) -> str:
	"""A lab, imaging, procedure or therapy request from the Requests tab: put on
	today's ward round and sent at once (to its service point)."""
	_check(("Physician", "Healthcare Administrator", "System Manager"))
	ip = frappe.get_doc(IR, inpatient_record)
	ip.check_permission("read")
	kind = frappe.db.get_value("Request Category", category, "request_kind")
	if kind not in REQUEST_TABLES:
		frappe.throw(_("Choose the request type."))
	table, field, comment = REQUEST_TABLES[kind]
	row = {field: template}
	if comment and note:
		row[comment] = note
	# Marley's request priorities are Code Values named "Urgent-Priority"
	code = urgency in URGENCY_CODES and frappe.db.exists("Code Value", f"{urgency}-Priority")
	if code:
		row["priority"] = code
	doc = _ward_round(ip)
	doc.ke_request_type = category
	doc.append(table, row)
	doc.submit_orders_on_save = 1
	doc.save()
	return doc.name
