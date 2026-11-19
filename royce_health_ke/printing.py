# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""What the hospital print formats need that a template shouldn't work out for
itself: the hospital's identity, the facility, the patient band, the clinician's
registration, and lab results with abnormal values flagged.

Same look as kenyan_accountant's documents (its Tax Invoice and Receipt), so a
patient's bill and their lab report read as one hospital's paperwork. When
kenyan_accountant is installed its company identity, accent colour and
letterhead rule are used, so a client's Printed Documents settings apply to both;
without it we fall back to the Company record.

Ownership (as kenyan_accountant's ADR-023): the formats are standard app files, so
fixes reach every client; which format is the DEFAULT is set once (install /
patch) and then belongs to the client.
"""

import base64
import io
import re

import frappe
from frappe import _
from frappe.utils import cint, flt, format_datetime, formatdate, get_datetime, get_time, getdate

DEFAULT_PRINT_FORMATS = {
	"Lab Test": "Laboratory Report",
	"Patient Encounter": "Consultation Summary",
	"Discharge Summary": "Patient Discharge Summary",
	"Observation": "Radiology Report",
	"Clinical Procedure": "Operation Note",
	"Patient": "Patient Card",
	"Diagnostic Report": "Diagnostic Results",
	"Surgical Consent": "Consent for Operation",
	"Surgical Safety Checklist": "Theatre Checklist",
	"Anaesthesia Record": "Anaesthesia Record",
}
# Marley's own formats: not a client's choice, so ours may replace them.
MARLEY_FORMATS = {
	"Lab Test": ("Lab Test Print",),
	"Patient Encounter": ("Encounter Print",),
	"Diagnostic Report": ("Diagnostic Report",),
}
NEUTRAL_ACCENT = "#1f2937"


def _ka():
	return "kenyan_accountant" in frappe.get_installed_apps()


def health_print_context(doc) -> frappe._dict:
	"""One call at the top of each template (a Jinja method in hooks)."""
	company = doc.get("company") or frappe.defaults.get_user_default("company")
	identity, accent, own_letter_head = _identity(doc, company)
	facility = _facility(doc)
	return frappe._dict(
		company=identity,
		accent=accent,
		use_letter_head=own_letter_head,
		facility=facility,
		patient=patient_band(doc),
		badge=_badge(doc),
	)


def _identity(doc, company):
	if _ka():
		from kenyan_accountant import printing as ka

		settings = ka._print_settings(company)
		home = (frappe.db.get_value("Company", company, "country") if company else None) or "Kenya"
		return (
			ka._company_identity(doc, company, home),
			settings.get("print_accent_color") or ka.NEUTRAL_ACCENT,
			ka.uses_own_letter_head(doc),
		)
	values = (
		frappe.db.get_value(
			"Company", company, ["company_name", "tax_id", "phone_no", "email", "website"], as_dict=True
		)
		if company
		else None
	) or frappe._dict()
	return (
		frappe._dict(
			name=values.company_name or company or "",
			logo="",
			address=frappe._dict(lines=[]),
			tax_id=values.tax_id or "",
			phone=values.phone_no or "",
			email=values.email or "",
			website=values.website or "",
		),
		NEUTRAL_ACCENT,
		False,
	)


def _facility(doc) -> frappe._dict:
	"""The Health Facility the document belongs to: from its service unit, else
	the inpatient record's current ward, else the company's only facility."""
	from royce_health_ke.sms import facility_for_unit

	unit = doc.get("service_unit")
	if not unit and doc.get("inpatient_record"):
		unit = frappe.db.get_value(
			"Inpatient Occupancy",
			{"parent": doc.inpatient_record, "parenttype": "Inpatient Record"},
			"service_unit",
			order_by="idx desc",
		)
	if not unit and doc.get("appointment"):
		unit = frappe.db.get_value("Patient Appointment", doc.appointment, "service_unit")
	name = facility_for_unit(unit)
	if not name and doc.get("company"):
		names = frappe.get_all("Health Facility", {"company": doc.company, "disabled": 0}, pluck="name")
		name = names[0] if len(names) == 1 else None
	if not name:
		return frappe._dict()
	return frappe._dict(
		frappe.db.get_value(
			"Health Facility", name, ["facility_name", "kmhfl_code", "phone", "email"], as_dict=True
		)
		or {}
	)


def _badge(doc) -> str:
	if doc.docstatus == 2 or doc.get("status") == "Cancelled":
		return "Cancelled"
	if doc.docstatus == 0 and doc.meta.is_submittable:
		return "Draft"
	return ""


def age(dob, on=None) -> str:
	"""'34 years', '7 months', '12 days': how a clinician writes it."""
	if not dob:
		return ""
	dob, on = getdate(dob), getdate(on)
	years = on.year - dob.year - ((on.month, on.day) < (dob.month, dob.day))
	if years >= 2:
		return f"{years} years"
	months = (on.year - dob.year) * 12 + on.month - dob.month - (on.day < dob.day)
	if months >= 1:
		return f"{months} month{'s' if months != 1 else ''}"
	days = (on - dob).days
	return f"{days} day{'s' if days != 1 else ''}"


def patient_band(doc) -> frappe._dict:
	"""Who the document is about, for the box under the header."""
	name = doc.name if doc.doctype == "Patient" else doc.get("patient")
	if not name:
		return frappe._dict()
	fields = ["patient_name", "sex", "dob", "uid"]
	meta = frappe.get_meta("Patient")
	fields += [f for f in ("ke_id_type", "ke_id_number", "ke_sha_number") if meta.has_field(f)]
	p = frappe.db.get_value("Patient", name, fields, as_dict=True) or frappe._dict()
	on = (
		doc.get("encounter_date")
		or doc.get("result_date")
		or doc.get("posting_date")
		or doc.get("date")
		or getdate()
	)
	ward = ""
	if doc.get("inpatient_record"):
		ward = (
			frappe.db.get_value(
				"Inpatient Occupancy",
				{"parent": doc.inpatient_record, "parenttype": "Inpatient Record"},
				"service_unit",
				order_by="idx desc",
			)
			or ""
		)
	return frappe._dict(
		name=p.patient_name or doc.get("patient_name") or name,
		# The record name when it's a number (naming series); not when the site
		# names patients by their name, and not Marley's UID (our ID number copy).
		number=name if name != (p.patient_name or doc.get("patient_name")) else "",
		age=age(p.dob, on) or doc.get("patient_age") or "",
		sex=p.sex or doc.get("patient_sex") or doc.get("gender") or "",
		id_label=p.get("ke_id_type") if p.get("ke_id_type") not in (None, "", "None") else "",
		id_number=p.get("ke_id_number") or "",
		sha=p.get("ke_sha_number") or "",
		inpatient=doc.get("inpatient_record") or "",
		ward=ward.rsplit(" - ", 1)[0] if ward else "",
	)


def clinician(practitioner) -> frappe._dict:
	"""Name, cadre and professional registration, for the signature line."""
	if not practitioner:
		return frappe._dict()
	meta = frappe.get_meta("Healthcare Practitioner")
	fields = ["practitioner_name", "department"]
	fields += [f for f in ("ke_cadre", "ke_regulator", "ke_registration_number") if meta.has_field(f)]
	p = frappe.db.get_value("Healthcare Practitioner", practitioner, fields, as_dict=True) or frappe._dict()
	reg = " ".join(x for x in (p.get("ke_regulator"), p.get("ke_registration_number")) if x)
	return frappe._dict(
		name=p.practitioner_name or practitioner,
		cadre=p.get("ke_cadre") or "",
		department=p.department or "",
		registration=reg,
	)


# Lab --------------------------------------------------------------------------

_RANGE = re.compile(r"(-?\d+(?:\.\d+)?)\s*(?:-|\u2013|to)\s*(-?\d+(?:\.\d+)?)")
_LIMIT = re.compile(r"(<|>|≤|≥|<=|>=)\s*(-?\d+(?:\.\d+)?)")


_SEX_LABEL = re.compile(r"(?:^|(?<=[\s/;,|(]))(male|female|men|women|m|f)\b\s*:?", re.I)


def range_for_sex(text, sex=None) -> str:
	"""The part of a range written per sex ('F 12.0 - 15.5 / M 13.5 - 17.5')
	that applies to this patient; the whole text when it isn't split by sex or
	the sex is unknown."""
	key = (sex or "").strip()[:1].upper()
	if key not in ("M", "F"):
		return text
	labels = list(_SEX_LABEL.finditer(text))
	if len(labels) < 2:
		return text
	for i, m in enumerate(labels):
		word = m.group(1).lower()
		label = "F" if word in ("f", "female", "women") else "M"
		if label == key:
			end = labels[i + 1].start() if i + 1 < len(labels) else len(text)
			return text[m.end() : end]
	return text


def flag(value, normal_range, sex=None) -> str:
	"""'H' or 'L' when a numeric result is outside a numeric range (the
	patient's sex's range, when the range is given per sex); '' when it is
	inside, or when either isn't a plain number/range (we never guess)."""
	try:
		v = float(str(value).strip().replace(",", ""))
	except TypeError, ValueError:
		return ""
	text = range_for_sex(re.sub(r"<[^>]+>", " ", str(normal_range or "")), sex)
	m = _RANGE.search(text)
	if m:
		lo, hi = float(m.group(1)), float(m.group(2))
		return "L" if v < lo else ("H" if v > hi else "")
	m = _LIMIT.search(text)
	if m:
		op, limit = m.group(1), float(m.group(2))
		if op in ("<", "<=", "≤") and v > limit:
			return "H"
		if op in (">", ">=", "≥") and v < limit:
			return "L"
	return ""


def lab_results(doc) -> list[frappe._dict]:
	"""Normal Test Result rows ready to print: group headings (a row with no
	result and no unit is a heading in Marley's grouped templates), the plain
	range text, and the H/L flag."""
	rows = []
	for r in doc.get("normal_test_items") or []:
		name = r.lab_test_event or r.lab_test_name or ""
		heading = not r.result_value and not r.lab_test_uom and not r.normal_range and not r.lab_test_event
		rows.append(
			frappe._dict(
				heading=heading,
				name=r.lab_test_name if heading else name,
				result=r.result_value or "",
				unit=r.lab_test_uom or "",
				range=_plain(r.normal_range),
				flag=flag(r.result_value, r.normal_range, doc.get("patient_sex")),
				comment=r.lab_test_comment or "",
				indent=bool(r.lab_test_event and r.lab_test_name and not heading),
			)
		)
	return rows


def _plain(html) -> str:
	text = re.sub(r"<br\s*/?>", "\n", str(html or ""), flags=re.I)
	return re.sub(r"<[^>]+>", "", text).strip()


def lab_people(doc) -> frappe._dict:
	"""Who performed and who verified, with when."""
	performed = doc.get("employee_name") or ""
	if not performed and doc.get("owner"):
		performed = frappe.db.get_value("User", doc.owner, "full_name") or ""
	verified = ""
	if doc.get("user"):
		verified = frappe.db.get_value("User", doc.user, "full_name") or doc.user
	return frappe._dict(
		performed=performed,
		performed_designation=doc.get("employee_designation") or "",
		verified=verified,
		verified_on=format_datetime(doc.approved_date, "d MMM yyyy HH:mm")
		if doc.get("approved_date")
		else "",
		collected=_collected(doc),
		reported=formatdate(doc.result_date, "d MMM yyyy") if doc.get("result_date") else "",
	)


def _collected(doc) -> str:
	if doc.get("ke_sample_collected_at"):
		return format_datetime(doc.ke_sample_collected_at, "d MMM yyyy HH:mm")
	if doc.get("sample"):
		when = frappe.db.get_value("Sample Collection", doc.sample, "collected_time")
		if when:
			return format_datetime(when, "d MMM yyyy HH:mm")
	if doc.get("date"):
		return formatdate(doc.date, "d MMM yyyy") + (f" {str(doc.time)[:5]}" if doc.get("time") else "")
	return ""


# Encounter ----------------------------------------------------------------------


def encounter_vitals(doc) -> frappe._dict:
	"""The vital signs taken for this visit: linked to the encounter or its
	appointment, else the patient's last ones that day."""
	filters = None
	if frappe.db.exists("Vital Signs", {"encounter": doc.name, "docstatus": 1}):
		filters = {"encounter": doc.name}
	elif doc.get("appointment") and frappe.db.exists(
		"Vital Signs", {"appointment": doc.appointment, "docstatus": 1}
	):
		filters = {"appointment": doc.appointment}
	elif doc.get("encounter_date"):
		filters = {"patient": doc.patient, "signs_date": doc.encounter_date}
	if not filters:
		return frappe._dict()
	filters["docstatus"] = 1
	v = frappe.get_all(
		"Vital Signs",
		filters=filters,
		fields=[
			"temperature",
			"pulse",
			"respiratory_rate",
			"bp",
			"bp_systolic",
			"bp_diastolic",
			"weight",
			"height",
			"ke_height_cm",
			"bmi",
		],
		order_by="signs_date desc, signs_time desc",
		limit=1,
	)
	if not v:
		return frappe._dict()
	v = v[0]
	bp = v.bp or (f"{v.bp_systolic}/{v.bp_diastolic}" if v.bp_systolic and v.bp_diastolic else "")
	items = [
		("Temp", f"{v.temperature} °C" if v.temperature else ""),
		("Pulse", f"{v.pulse} /min" if v.pulse else ""),
		("Resp. rate", f"{v.respiratory_rate} /min" if v.respiratory_rate else ""),
		("BP", f"{bp} mmHg" if bp else ""),
		("Weight", f"{flt(v.weight, 1):g} kg" if flt(v.weight) else ""),
		("Height", f"{flt(v.ke_height_cm or flt(v.height) * 100, 1):g} cm" if flt(v.height) else ""),
		("BMI", f"{flt(v.bmi, 1):g}" if flt(v.bmi) else ""),
	]
	return frappe._dict(items=[(k, val) for k, val in items if val])


def prescription_lines(doc) -> list[frappe._dict]:
	"""Drug Prescription rows as a pharmacist reads them."""
	lines = []
	for d in doc.get("drug_prescription") or []:
		# Marley often stores the item code in drug_name; print the item's name.
		name = d.drug_name if d.drug_name and d.drug_name != d.drug_code else ""
		name = (
			name
			or (frappe.db.get_value("Item", d.drug_code, "item_name") if d.drug_code else "")
			or d.medication
			or d.drug_code
			or ""
		)
		strength = f"{flt(d.strength):g} {d.strength_uom or ''}".strip() if flt(d.strength) else ""
		how = d.dosage or ""
		if cint(d.dosage_by_interval) and d.interval:
			how = f"every {d.interval} {(d.interval_uom or '').lower()}{'s' if d.interval > 1 else ''}"
		# Leave out strength / form already spelt in the item name ("... 500mg Tablet").
		squashed = name.lower().replace(" ", "")
		if strength and strength.lower().replace(" ", "") in squashed:
			strength = ""
		form = d.dosage_form or ""
		if form and form.lower() in name.lower():
			form = ""
		dose = (
			f"{flt(d.get('ke_dose')):g} {d.get('ke_dose_uom') or ''}".strip() if flt(d.get("ke_dose")) else ""
		)
		start = ""
		if d.get("ke_start_date"):
			start = formatdate(d.ke_start_date, "d MMM")
			if d.get("ke_start_time"):
				start = f"{start} {str(d.ke_start_time)[:5]}"
		quantity = d.get("ke_quantity") or (
			d.get("medication_request")
			and frappe.db.get_value("Medication Request", d.medication_request, "quantity")
		)
		lines.append(
			frappe._dict(
				name=name,
				strength=strength,
				form=form,
				dosage=how,
				dose=dose,
				route=d.get("ke_route") or "",
				start=start,
				quantity=f"{flt(quantity):g} {d.get('ke_dispensing_unit') or ''}".strip()
				if flt(quantity)
				else "",
				period=d.period or "",
				comment=d.comment or "",
				repeats=cint(d.number_of_repeats_allowed),
			)
		)
	return lines


def encounter_time(doc) -> str:
	if not doc.get("encounter_date"):
		return ""
	if doc.get("encounter_time"):
		return format_datetime(get_datetime(f"{doc.encounter_date} {doc.encounter_time}"), "d MMM yyyy HH:mm")
	return formatdate(doc.encounter_date, "d MMM yyyy")


# Discharge ------------------------------------------------------------------------


def discharge_details(doc) -> frappe._dict:
	ip = frappe._dict()
	if doc.get("inpatient_record"):
		ip = (
			frappe.db.get_value(
				"Inpatient Record",
				doc.inpatient_record,
				["admitted_datetime", "discharge_datetime", "discharge_instructions", "followup_date"],
				as_dict=True,
			)
			or frappe._dict()
		)
		ip.medicines = prescription_lines(frappe.get_doc("Inpatient Record", doc.inpatient_record))
	admitted = doc.get("admitted_datetime") or ip.get("admitted_datetime")
	discharged = ip.get("discharge_datetime")
	stay = ""
	if admitted:
		end = get_datetime(discharged) if discharged else get_datetime(doc.posting_date)
		days = max((end.date() - get_datetime(admitted).date()).days, 0)
		stay = f"{days} day{'s' if days != 1 else ''}" if days else "Same day"
	return frappe._dict(
		admitted=format_datetime(admitted, "d MMM yyyy HH:mm") if admitted else "",
		discharged=format_datetime(discharged, "d MMM yyyy HH:mm")
		if discharged
		else (formatdate(doc.posting_date, "d MMM yyyy") if doc.get("posting_date") else ""),
		stay=stay,
		followup=formatdate(doc.get("followup_date") or ip.get("followup_date"), "d MMM yyyy")
		if (doc.get("followup_date") or ip.get("followup_date"))
		else "",
		medicines=ip.get("medicines") or [],
		instructions=ip.get("discharge_instructions") or "",
	)


def has_text(html) -> bool:
	"""A Text Editor field counts as empty when it's only tags and spaces."""
	return bool(_plain(html).replace("\xa0", "").strip())


# Radiology ------------------------------------------------------------------------


def imaging_details(doc) -> frappe._dict:
	"""An imaging Observation as the radiology report prints it."""
	from royce_health_ke.radiology import is_imaging

	sr = frappe._dict()
	if doc.get("service_request"):
		sr = (
			frappe.db.get_value(
				"Service Request",
				doc.service_request,
				["practitioner", "order_description", "comment", "priority"],
				as_dict=True,
			)
			or frappe._dict()
		)
	clinical = " ".join(x for x in (sr.get("comment"), sr.get("order_description")) if x and x.strip())
	requested_by = doc.get("healthcare_practitioner") or sr.get("practitioner")

	def when(value):
		return format_datetime(value, "d MMM yyyy HH:mm") if value else ""

	return frappe._dict(
		imaging=bool(is_imaging(doc)),
		exam=doc.get("preferred_display_name") or doc.get("observation_template") or "",
		modality=doc.get("ke_modality") or "",
		accession=doc.get("ke_accession_number") or "",
		priority=doc.get("ke_priority") or "",
		requested_by=clinician(requested_by),
		clinical=clinical if clinical != (doc.get("observation_template") or "") else "",
		performed=when(doc.get("ke_performed_at")),
		radiographer=doc.get("ke_radiographer") or "",
		contrast=(doc.get("ke_contrast_agent") or "Yes") if cint(doc.get("ke_contrast")) else "",
		dose=doc.get("ke_radiation_dose") or "",
		reported_by=clinician(doc.get("ke_reported_by")),
		reported=when(doc.get("ke_reported_at")),
		verified_by=clinician(doc.get("ke_verified_by")),
		verified=when(doc.get("time_of_approval")),
		result_date=when(doc.get("time_of_result"))
		or (formatdate(doc.posting_date, "d MMM yyyy") if doc.get("posting_date") else ""),
	)


# Theatre --------------------------------------------------------------------------


def operation_details(doc) -> frappe._dict:
	"""A Clinical Procedure with its theatre booking and anaesthesia record."""
	booking = frappe._dict()
	if doc.get("ke_theatre_booking"):
		booking = (
			frappe.db.get_value(
				"Theatre Booking",
				doc.ke_theatre_booking,
				[
					"name",
					"priority",
					"theatre",
					"surgeon",
					"assistant",
					"anaesthetist",
					"scrub_nurse",
					"anaesthesia_record",
				],
				as_dict=True,
			)
			or frappe._dict()
		)
	anaesthesia = frappe._dict()
	record = booking.get("anaesthesia_record") or (
		frappe.db.get_value("Anaesthesia Record", {"theatre_booking": booking.name, "docstatus": ["<", 2]})
		if booking.get("name")
		else None
	)
	if record:
		anaesthesia = (
			frappe.db.get_value(
				"Anaesthesia Record",
				record,
				[
					"anaesthesia_type",
					"asa_class",
					"asa_emergency",
					"airway",
					"complications",
					"induction_agents",
					"maintenance",
				],
				as_dict=True,
			)
			or frappe._dict()
		)

	def name(practitioner):
		return clinician(practitioner).name if practitioner else ""

	start = doc.get("actual_start_datetime") or (
		get_datetime(f"{doc.start_date} {doc.start_time}")
		if doc.get("start_date") and doc.get("start_time")
		else None
	)
	end = doc.get("actual_end_datetime")
	minutes = int((get_datetime(end) - get_datetime(start)).total_seconds() // 60) if start and end else 0
	asa = anaesthesia.get("asa_class") or ""
	if asa and cint(anaesthesia.get("asa_emergency")):
		asa += "E"
	surgeon = booking.get("surgeon") or doc.get("practitioner")
	return frappe._dict(
		theatre=bool(booking),
		priority=booking.get("priority") or "",
		room=(booking.get("theatre") or doc.get("service_unit") or "").rsplit(" - ", 1)[0],
		surgeon=clinician(surgeon),
		assistant=name(booking.get("assistant")),
		anaesthetist=name(booking.get("anaesthetist")),
		scrub_nurse=booking.get("scrub_nurse") or "",
		anaesthesia=anaesthesia.get("anaesthesia_type") or "",
		agent=", ".join(
			x for x in (anaesthesia.get("induction_agents"), anaesthesia.get("maintenance")) if x
		),
		asa=asa,
		airway=anaesthesia.get("airway") if anaesthesia.get("airway") not in (None, "", "None") else "",
		anaesthesia_complications=anaesthesia.get("complications") or "",
		started=format_datetime(start, "d MMM yyyy HH:mm") if start else "",
		ended=format_datetime(end, "HH:mm") if end else "",
		duration=f"{minutes} min" if minutes > 0 else "",
		blood_loss=f"{cint(doc.get('ke_estimated_blood_loss_ml'))} ml"
		if cint(doc.get("ke_estimated_blood_loss_ml")) > 0
		else "",
	)


# Theatre forms ----------------------------------------------------------------------


def _booking_team(booking_name) -> frappe._dict:
	b = (
		frappe.db.get_value(
			"Theatre Booking",
			booking_name,
			[
				"name",
				"company",
				"inpatient_record",
				"theatre",
				"priority",
				"scheduled_start",
				"surgeon",
				"assistant",
				"anaesthetist",
				"scrub_nurse",
				"procedure_template",
			],
			as_dict=True,
		)
		if booking_name
		else None
	) or frappe._dict()

	def name(practitioner):
		return clinician(practitioner).name if practitioner else ""

	procedure = ""
	if b.procedure_template:
		procedure = (
			frappe.db.get_value("Clinical Procedure Template", b.procedure_template, "template")
			or b.procedure_template
		)
	return frappe._dict(
		booking=b,
		procedure=procedure,
		surgeon=name(b.surgeon),
		assistant=name(b.assistant),
		anaesthetist=name(b.anaesthetist),
		scrub_nurse=b.scrub_nurse or "",
		theatre=(b.theatre or "").rsplit(" - ", 1)[0],
		date=format_datetime(b.scheduled_start, "d MMM yyyy") if b.scheduled_start else "",
	)


def _hm(value) -> str:
	return get_time(value).strftime("%H:%M") if value else ""


def _time(value) -> str:
	return format_datetime(value, "d MMM HH:mm") if value else ""


def theatre_details(doc) -> frappe._dict:
	"""What the consent, theatre checklist and anaesthesia prints share: the
	booking's team and procedure, and the record's company / inpatient stay
	(so the hospital header and the ward show)."""
	team = _booking_team(doc.get("theatre_booking"))
	if not doc.get("company"):
		doc.company = team.booking.get("company")
	if not doc.get("inpatient_record"):
		doc.inpatient_record = team.booking.get("inpatient_record")
	return team


def consent_details(doc) -> frappe._dict:
	"""Surgical Consent in the hospital's wording: who consents, of what
	address, for which operation, on whom."""
	team = theatre_details(doc)
	address = frappe.db.sql(
		"""select a.address_line1, a.address_line2, a.city, a.pincode from `tabAddress` a
		join `tabDynamic Link` l on l.parent = a.name and l.parenttype = 'Address'
		where l.link_doctype = 'Patient' and l.link_name = %s
		order by a.is_primary_address desc, a.creation desc limit 1""",
		doc.patient,
		as_dict=True,
	)
	a = address[0] if address else frappe._dict()
	on_whom = {
		"Patient": _("myself"),
		"Parent": _("my child"),
		"Guardian": _("the patient in my care"),
		"Next of kin": _("my relative"),
	}.get(doc.consent_by, "")
	return frappe._dict(
		team=team,
		consenter=doc.consenter_name or "",
		address=", ".join(x for x in (a.get("address_line1"), a.get("address_line2"), a.get("city")) if x),
		doctor=clinician(doc.explained_by).name if doc.explained_by else team.surgeon,
		operation=team.procedure or doc.procedure_template or "",
		on_whom=on_whom,
		relationship=doc.relationship or "",
		date=format_datetime(doc.consent_datetime, "d MMM yyyy HH:mm") if doc.consent_datetime else "",
		by_patient=doc.consent_by == "Patient",
	)


def checklist_details(doc) -> frappe._dict:
	team = theatre_details(doc)
	return frappe._dict(
		team=team,
		handed_over=_time(doc.get("wp_handed_over_time")),
		received=_time(doc.get("wp_received_time")),
		back_in_ward=_time(doc.get("po_received_time")),
		sign_in=_time(doc.get("sign_in_time")),
		time_out=_time(doc.get("time_out_time")),
		sign_out=_time(doc.get("sign_out_time")),
		premed_time=_time(doc.get("wp_premed_time")),
		last_feed=_time(doc.get("wp_last_feed")),
	)


def anaesthesia_details(doc) -> frappe._dict:
	"""The KSA pre-op assessment (systems grouped, a system Abnormal when any
	condition is Yes) and the monitoring chart (vitals in time order, drugs)."""
	team = theatre_details(doc)
	systems = []
	for row in doc.get("systems_review") or []:
		if not systems or systems[-1].name != row.system:
			systems.append(frappe._dict(name=row.system, rows=[], abnormal=False))
		systems[-1].rows.append(row)
		if row.present == "Yes":
			systems[-1].abnormal = True
	asa = (doc.asa_class or "").replace("ASA ", "")
	return frappe._dict(
		team=team,
		systems=systems,
		asa=asa,
		gcs=f"E{doc.gcs_e} M{doc.gcs_m} V{doc.gcs_v} = {doc.gcs_total}" if doc.get("gcs_total") else "",
		vitals=[
			frappe._dict(r.as_dict(), at=_hm(r.time))
			for r in sorted(doc.get("vitals") or [], key=lambda r: _hm(r.time))
		],
		drugs=[
			frappe._dict(r.as_dict(), at=_hm(r.time))
			for r in sorted(doc.get("drugs") or [], key=lambda r: _hm(r.time))
		],
		induction=_time(doc.get("induction_time")),
		end=_time(doc.get("end_time")),
		surgery_start=_time(doc.get("surgery_start")),
		surgery_end=_time(doc.get("surgery_end")),
		premed_time=_time(doc.get("premed_time")),
		assessed_on=_time(doc.get("assessed_on")),
		recovery_out=_time(doc.get("recovery_discharge_time")),
		anaesthetist=clinician(doc.anaesthetist) if doc.get("anaesthetist") else frappe._dict(),
	)


# Patient card -----------------------------------------------------------------------


def patient_card(doc) -> frappe._dict:
	"""Registration details and the wallet card. The QR holds only the patient
	number (the record's name): scanned at reception it finds the record, and it
	gives nothing away if the card is lost."""
	address = ", ".join(x for x in (doc.get("ke_sub_county"), doc.get("ke_county")) if x)
	nok = " ".join(
		x
		for x in (
			doc.get("ke_nok_name"),
			f"({doc.ke_nok_relationship})" if doc.get("ke_nok_relationship") else "",
		)
		if x
	)
	band = patient_band(doc)
	return frappe._dict(
		# The number on the card: the record name when it's a number, else the ID.
		number=band.number or band.id_number or "",
		registered=formatdate(doc.creation, "d MMM yyyy") if doc.get("creation") else "",
		dob=formatdate(doc.dob, "d MMM yyyy") if doc.get("dob") else "",
		address=address,
		nok=nok,
		nok_phone=doc.get("ke_nok_phone") or "",
		qr=qr_data_uri(doc.name) if doc.get("name") else "",
	)


def qr_data_uri(text: str) -> str:
	try:
		import pyqrcode

		buffer = io.BytesIO()
		pyqrcode.create(text).png(buffer, scale=3, quiet_zone=1)
		return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()
	except Exception:
		return ""


# Diagnostic Report ------------------------------------------------------------------


def diagnostic_rows(doc) -> list[frappe._dict]:
	"""The report's observations, as Marley collects them (get_observation_details),
	flattened for printing: a panel's name as a heading row, its components
	indented under it. Text results (imaging findings, microscopy) print as text."""
	from royce_health_ke.marley import get_observation_details

	try:
		data, _count = get_observation_details(doc.name)
	except Exception:
		frappe.log_error(title=f"Diagnostic Report {doc.name}: observations not readable for print")
		return []
	rows = []

	def add(obs, indent=False):
		name = obs.get("preferred_display_name") or obs.get("observation_template") or ""
		result = obs.get("result") or ""
		text = "<" in result or len(result) > 40
		rows.append(
			frappe._dict(
				heading=False,
				name=name,
				result=result,
				text=text,
				unit=obs.get("permitted_unit") or "",
				range=_plain(obs.get("reference")),
				flag=""
				if text
				else ((obs.get("result_flag") or "")[:1].upper() or flag(result, obs.get("reference"))),
				comment=_plain(obs.get("note")),
				indent=indent,
				pending=not result,
			)
		)

	def walk(entry, depth=0):
		if entry.get("has_component"):
			rows.append(frappe._dict(heading=True, name=entry.get("display_name") or "", indent=depth > 0))
			for child in entry.get(entry.get("observation")) or []:
				walk(child, depth + 1)
		else:
			add(entry.get("observation") or {}, indent=depth > 0)

	for entry in data:
		walk(entry)
	return rows


# Defaults -----------------------------------------------------------------------


def set_default_print_formats() -> list:
	"""Makes our formats the default for their doctypes unless the client chose
	another one. Replaces only an empty default or Marley's own. Runs at install
	and once by patch on existing sites, never on every migrate."""
	done = []
	for doctype, print_format in DEFAULT_PRINT_FORMATS.items():
		if not frappe.db.exists("Print Format", print_format):
			continue
		current = frappe.db.get_value(
			"Property Setter",
			{"doc_type": doctype, "doctype_or_field": "DocType", "property": "default_print_format"},
			"value",
		)
		if current and current not in MARLEY_FORMATS.get(doctype, ()):
			continue
		frappe.make_property_setter(
			{
				"doctype": doctype,
				"doctype_or_field": "DocType",
				"property": "default_print_format",
				"value": print_format,
				"property_type": "Data",
			},
			is_system_generated=False,
		)
		done.append(doctype)
	return done


# Jinja methods (hooks). Frappe registers them by their own __name__, so these
# are real functions, prefixed so they can't clash with another app's names.
def health_lab_results(doc):
	return lab_results(doc)


def health_lab_people(doc):
	return lab_people(doc)


def health_clinician(practitioner):
	return clinician(practitioner)


def health_has_text(html):
	return has_text(html)


def health_encounter_vitals(doc):
	return encounter_vitals(doc)


def health_prescription_lines(doc):
	return prescription_lines(doc)


def health_encounter_time(doc):
	return encounter_time(doc)


def health_discharge_details(doc):
	return discharge_details(doc)


def health_imaging_details(doc):
	return imaging_details(doc)


def health_operation_details(doc):
	return operation_details(doc)


def health_patient_card(doc):
	return patient_card(doc)


def health_diagnostic_rows(doc):
	return diagnostic_rows(doc)


def health_consent_details(doc):
	return consent_details(doc)


def health_checklist_details(doc):
	return checklist_details(doc)


def health_anaesthesia_details(doc):
	return anaesthesia_details(doc)


def continuation_details(booking) -> frappe._dict:
	"""Theatre Booking: the operation header of the continuation sheet (from
	the operation note and anaesthesia record) and its progress notes."""
	procedure = (
		frappe.get_doc("Clinical Procedure", booking.clinical_procedure)
		if booking.get("clinical_procedure")
		else None
	)
	if procedure:
		op = operation_details(procedure)
	else:
		op = frappe._dict(
			surgeon=clinician(booking.surgeon) if booking.get("surgeon") else frappe._dict(name=""),
			assistant=clinician(booking.assistant).name if booking.get("assistant") else "",
			anaesthetist=clinician(booking.anaesthetist).name if booking.get("anaesthetist") else "",
			agent="",
			started="",
		)
	return frappe._dict(
		op=op,
		diagnosis=(procedure.get("ke_indication") if procedure else "") or "",
		incision=(procedure.get("ke_incision") if procedure else "") or "",
		findings=(procedure.get("ke_findings") if procedure else "") or "",
		procedure_html=(procedure.get("ke_procedure_details") if procedure else "") or "",
		notes=[
			frappe._dict(
				time=format_datetime(n.noted_at, "d MMM HH:mm") if n.noted_at else "",
				stage=n.stage,
				note=n.note,
				by=n.recorded_by_name or n.recorded_by or "",
			)
			for n in booking.get("progress_notes") or []
		],
	)


def treatment_sheet_details(doc) -> frappe._dict:
	from royce_health_ke import postop

	details = postop.sheet_details(doc)
	weight = f"{flt(doc.weight_kg):g} kg" if flt(doc.get("weight_kg")) else ""

	def when(value):
		return format_datetime(value, "d MMM HH:mm") if value else ""

	def given(row):
		"""The once-only dose's scheduled entry, when the ward has given it."""
		at = get_datetime(row.give_at).replace(second=0, microsecond=0) if row.get("give_at") else None
		return [
			e
			for e in details.given.get(row.drug, [])
			if (e.status == "Completed" or e.is_completed) and at and get_datetime(f"{e.date} {e.time}") == at
		]

	return frappe._dict(
		weight=weight,
		prescriber=clinician(doc.practitioner) if doc.get("practitioner") else frappe._dict(name=""),
		written=when(doc.get("written_at")),
		drugs=[
			frappe._dict(
				name=(d.row.drug_name or d.row.drug or "").upper(),
				dose=d.row.dose,
				route=d.row.route,
				frequency=d.frequency,
				days=d.row.duration_days if not d.row.prn else "",
				first=when(d.row.first_dose_at),
				instructions=d.row.instructions or "",
				doses=d.doses,
			)
			for d in details.drugs
		],
		once=[
			frappe._dict(
				name=(r.drug_name or r.drug or "").upper(),
				dose=r.dose,
				route=r.route,
				time=when(r.give_at),
				instructions=r.instructions or "",
				given=_("Given") if given(r) else "",
			)
			for r in doc.once_only
		],
	)


def health_continuation_details(doc):
	return continuation_details(doc)


def health_treatment_sheet(doc):
	return treatment_sheet_details(doc)


def health_patient_receipt(doc) -> frappe._dict:
	"""Jinja (Patient Receipt, 80 mm): who paid, for what, how (with the
	M-Pesa or card code) and the change, like the hospital's EPOS slips.
	Payments are those taken on the invoice and any Payment Entry against it."""
	ctx = health_print_context(doc)
	patient = frappe._dict()
	if doc.get("patient"):
		patient = (
			frappe.db.get_value(
				"Patient",
				doc.patient,
				["name", "patient_name", "dob", "sex", "mobile", "phone"],
				as_dict=True,
			)
			or frappe._dict()
		)
	payments = [
		frappe._dict(mode=p.mode_of_payment, amount=flt(p.amount), reference=p.get("reference_no") or "")
		for p in doc.get("payments") or []
		if flt(p.amount)
	]
	if doc.docstatus == 1:
		for pe in frappe.db.sql(
			"""select pe.name, pe.mode_of_payment, pe.reference_no, ref.allocated_amount, pe.ke_change
			from `tabPayment Entry Reference` ref join `tabPayment Entry` pe on pe.name = ref.parent
			where ref.reference_doctype = 'Sales Invoice' and ref.reference_name = %s
				and pe.docstatus = 1 and pe.payment_type = 'Receive'
			order by pe.posting_date, pe.creation""",
			doc.name,
			as_dict=True,
		):
			payments.append(
				frappe._dict(
					mode=pe.mode_of_payment,
					amount=flt(pe.allocated_amount),
					reference=pe.reference_no or "",
					entry=pe.name,
					change=flt(pe.ke_change),
				)
			)
	paid = sum(p.amount for p in payments)
	change = flt(doc.get("change_amount")) + sum(flt(p.get("change")) for p in payments)
	return frappe._dict(
		company=ctx.company,
		badge=ctx.badge,
		patient=patient,
		# the record number when patients are numbered (not when named by name)
		patient_no=ctx.patient.get("number") or "",
		phone=patient.get("mobile") or patient.get("phone") or "",
		payments=payments,
		modes=", ".join(dict.fromkeys(p.mode for p in payments if p.mode)),
		references=", ".join(dict.fromkeys(p.reference for p in payments if p.reference)),
		tendered=paid + change,
		change=change,
		paid=paid,
		balance=flt(doc.get("outstanding_amount")) if doc.docstatus == 1 else None,
		served_by=frappe.utils.get_fullname(doc.owner),
		paid_by=doc.get("patient_name") or doc.get("customer_name") or "",
		etims=_etims_receipt(doc),
		company_pin=frappe.db.get_value("Company", doc.company, "tax_id") if doc.get("company") else "",
	)


def _etims_receipt(doc):
	"""KRA eTIMS details for the receipt, once KRA has signed the invoice
	(royce_etims, optional): the CU invoice and receipt numbers, the signature,
	the control unit's date and time, and the QR code (IT demo, 18 Nov 2026)."""
	if not doc.get("royce_etims_receipt_signature"):
		return None
	current, total = (
		doc.get("royce_etims_current_receipt_number"),
		doc.get("royce_etims_total_receipt_number"),
	)
	return frappe._dict(
		invoice_number=doc.get("royce_etims_invoice_number") or "",
		receipt_number=f"{current}/{total}" if current or total else "",
		signature=doc.get("royce_etims_receipt_signature"),
		internal_data=doc.get("royce_etims_internal_data") or "",
		cu_datetime=doc.get("royce_etims_control_unit_datetime") or "",
		qr=doc.get("royce_etims_qr_code") or doc.get("royce_etims_qr_image") or "",
		verify_url=doc.get("royce_etims_qr_verification_url") or "",
	)


# The patient file (IT demo, 18 Nov 2026): the patient's whole record on one
# page, newest visit first, for clinicians only. Reception and the Cashier see
# no diagnosis or result (role_access.py), so it is refused for them; opening
# and printing it are logged (access.py) like any patient record.

FILE_ROLES = ("Physician", "Nursing User", "Healthcare Administrator", "System Manager")
FILE_VISITS = 50
VITALS_FIELDS = (
	"name",
	"signs_date",
	"signs_time",
	"temperature",
	"pulse",
	"respiratory_rate",
	"bp",
	"ke_spo2",
	"weight",
	"ke_height_cm",
	"bmi",
	"ke_vitals_flags",
)


VISIT_FIELDS = (
	"name",
	"visit_date",
	"visit_type",
	"payment_method",
	"insurance_payor",
	"status",
	"practitioner_name",
)
REQUEST_STATUS = {
	"active-Request Status": _("Requested"),
	"completed-Request Status": _("Done"),
	"revoked-Request Status": _("Cancelled"),
	"on-hold-Request Status": _("On hold"),
}


def diagnosis_lines(encounter):
	"""The consultation's diagnoses with their ICD-11 code."""
	from royce_health_ke.diagnosis import icd11_of

	out = []
	for row in encounter.get("diagnosis") or []:
		if not row.get("diagnosis"):
			continue
		code = row.get("ke_icd11_code") and frappe.db.get_value("Code Value", row.ke_icd11_code, "code_value")
		out.append(frappe._dict(name=row.diagnosis, code=code or icd11_of(row.diagnosis)[1] or ""))
	return out


def visit_record(v):
	"""One visit as the Patient File and the Visit Summary print it: vitals,
	consultations, requests, lab results, imaging reports."""
	encounters = [
		frappe.get_doc("Patient Encounter", name)
		for name in frappe.get_all(
			"Patient Encounter",
			filters={"ke_patient_visit": v.name, "docstatus": ["<", 2]},
			pluck="name",
			order_by="creation asc",
		)
	]
	request_rows = (
		frappe.get_all(
			"Service Request",
			filters={"order_group": ["in", [e.name for e in encounters]], "docstatus": 1},
			fields=[
				"name",
				"template_dn",
				"status",
				"ke_service_point",
				"ke_request_category",
				"ke_cancel_reason",
			],
			order_by="creation",
		)
		if encounters
		else []
	)
	requests = [r.name for r in request_rows]
	return frappe._dict(
		visit=v,
		vitals=frappe.get_all(
			"Vital Signs",
			filters={"ke_patient_visit": v.name, "docstatus": ["<", 2]},
			fields=list(VITALS_FIELDS),
			order_by="signs_date, signs_time",
		),
		encounters=[
			frappe._dict(
				doc=e,
				doctor=clinician(e.practitioner),
				medicines=prescription_lines(e),
				diagnoses=diagnosis_lines(e),
			)
			for e in encounters
		],
		requests=[
			frappe._dict(
				test=r.template_dn,
				where=r.ke_service_point or "",
				status=REQUEST_STATUS.get(r.status, r.status.split("-")[0].title() if r.status else ""),
				note=r.ke_cancel_reason or "",
			)
			for r in request_rows
		],
		labs=[
			frappe._dict(doc=t, rows=lab_results(t))
			for t in (
				frappe.get_doc("Lab Test", name)
				for name in frappe.get_all(
					"Lab Test",
					filters={"ke_patient_visit": v.name, "docstatus": 1},
					pluck="name",
					order_by="creation",
				)
			)
		],
		imaging=[
			frappe.get_doc("Observation", name)
			for name in (
				frappe.get_all(
					"Observation",
					filters={
						"service_request": ["in", requests],
						"parent_observation": ["is", "not set"],
						"ke_exam_status": ["in", ("Reported", "Verified")],
					},
					pluck="name",
				)
				if requests
				else []
			)
		],
	)


def visit_summary(doc) -> frappe._dict:
	"""Patient Visit: everything done on the visit, for the patient's file
	(clinicians only, like the Patient File)."""
	if not may_open_file():
		return frappe._dict(allowed=False)
	v = frappe._dict({field: doc.get(field) for field in VISIT_FIELDS})
	return frappe._dict(allowed=True, record=visit_record(v))


def health_visit_summary(doc):
	return visit_summary(doc)


def may_open_file(user=None):
	# a patient's own copy, exported by the Data Protection Officer (dataprotection.export_record)
	if frappe.flags.ke_record_export:
		return True
	return bool(set(FILE_ROLES) & set(frappe.get_roles(user)))


def patient_file(doc) -> frappe._dict:
	if not may_open_file():
		return frappe._dict(allowed=False)
	history = [
		(label, doc.get(field))
		for field, label in (
			("allergies", _("Allergies")),
			("medication", _("Current medication")),
			("medical_history", _("Past medical")),
			("surgical_history", _("Past surgical")),
			("ke_family_history", _("Family")),
			("ke_social_history", _("Social")),
		)
		if doc.get(field)
	]
	visits = [
		visit_record(v)
		for v in frappe.get_all(
			"Patient Visit",
			filters={"patient": doc.name, "status": ["!=", "Cancelled"]},
			fields=VISIT_FIELDS,
			order_by="visit_date desc, creation desc",
			limit=FILE_VISITS,
		)
	]
	admissions = frappe.get_all(
		"Inpatient Record",
		filters={"patient": doc.name},
		fields=["name", "admitted_datetime", "discharge_datetime", "status", "primary_practitioner"],
		order_by="admitted_datetime desc",
	)
	return only_sections(frappe._dict(allowed=True, history=history, visits=visits, admissions=admissions))


# The patient report: the sections chosen when printing (?sections=...,
# Bethesda: "choose what to include in the report"). All when none chosen.
FILE_SECTIONS = ("history", "admissions", "vitals", "consultations", "requests", "labs", "imaging")


def only_sections(f):
	chosen = {x.strip() for x in (frappe.form_dict.get("sections") or "").split(",") if x.strip()}
	if not chosen:
		return f
	if "history" not in chosen:
		f.history = []
	if "admissions" not in chosen:
		f.admissions = []
	keys = {
		"vitals": "vitals",
		"consultations": "encounters",
		"requests": "requests",
		"labs": "labs",
		"imaging": "imaging",
	}
	for v in f.visits:
		for section, key in keys.items():
			if section not in chosen:
				v[key] = []
	f.visits = [v for v in f.visits if any(v.get(k) for k in keys.values())]
	return f


def health_patient_file(doc):
	return patient_file(doc)


def health_admission_record(doc):
	"""Jinja (Discharge Summary): the record of the stay (inpatient.admission_record)."""
	from royce_health_ke.inpatient import admission_record

	return admission_record(doc.get("inpatient_record"))
