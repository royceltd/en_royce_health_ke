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

import re

import frappe
from frappe.utils import cint, flt, format_datetime, formatdate, get_datetime, getdate

DEFAULT_PRINT_FORMATS = {
	"Lab Test": "Laboratory Report",
	"Patient Encounter": "Consultation Summary",
	"Discharge Summary": "Patient Discharge Summary",
}
# Marley's own formats: not a client's choice, so ours may replace them.
MARLEY_FORMATS = {
	"Lab Test": ("Lab Test Print",),
	"Patient Encounter": ("Encounter Print",),
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
	name = doc.get("patient")
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


def flag(value, normal_range) -> str:
	"""'H' or 'L' when a numeric result is outside a numeric range; '' when it
	is inside, or when either isn't a plain number/range (we never guess)."""
	try:
		v = float(str(value).strip().replace(",", ""))
	except (TypeError, ValueError):
		return ""
	text = re.sub(r"<[^>]+>", " ", str(normal_range or ""))
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
				flag=flag(r.result_value, r.normal_range),
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
		("Height", f"{flt(v.height, 2):g} m" if flt(v.height) else ""),
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
		lines.append(
			frappe._dict(
				name=name,
				strength=strength,
				form=form,
				dosage=how,
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
