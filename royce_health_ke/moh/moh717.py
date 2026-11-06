# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""MOH 717 monthly service workload. Indicator names follow the MOH 717 form
as implemented in KenyaEMR. Sections whose data isn't captured yet
(maternal and child health, deliveries, procedures, imaging) are listed with
no value, so the report shows exactly what still has to be filled in by hand.

- Outpatient attendances: one per patient per day, outpatient encounters.
  New = first outpatient day in the calendar year (as MOH 705). The clinic
  comes from the encounter's Medical Department (its MOH 717 Clinic field;
  blank = General Outpatient).
- Inpatient: the ward category comes from the admission's Healthcare Service
  Unit Type (its MOH 717 Ward field; blank = Other Wards). Admissions by
  admission date; discharges, deaths, abscondees and referrals out by
  discharge date and the record's Discharge Outcome."""

from collections import Counter

import frappe
from frappe.utils import getdate

from royce_health_ke.moh.moh705 import age_on, first_visit_of_year, lab_tests, period

CLINICS = (
	"General Outpatient",
	"ENT Clinic",
	"Eye Clinic",
	"TB and Leprosy Clinic",
	"CCC Clinic",
	"Psychiatry Clinic",
	"Orthopaedic Clinic",
	"Occupational Therapy Clinic",
	"Physiotherapy Clinic",
	"Medical Clinics",
	"Surgical Clinics",
	"Paediatrics",
	"Obstetrics and Gynaecology",
	"Nutrition Clinic",
	"Oncology Clinic",
	"Renal Clinic",
	"All other special Clinics",
	"Dental",
)
WARDS = (
	"Medical",
	"Surgical",
	"Obst And Gyn",
	"Paediatrics",
	"Maternity",
	"Eye",
	"Nursery And Newborn",
	"Orthopaedic",
	"Isolation",
	"Amenity",
	"Psychiatry",
	"ICU",
	"Renal",
	"Other Wards",
)
OUTCOMES = ("Discharged", "Referred Out", "Absconded", "Died")
NOT_CAPTURED = {
	"Child Welfare and Family Planning": ["New CWC Visits", "CWC RE-ATT", "FP NEW", "FP RE-ATT"],
	"Procedures": [
		"Dressings",
		"Removal of Stitches",
		"Injections",
		"Stitching",
		"Physiotherapy Treatments",
		"Occupational Therapy Treatments",
	],
	"Imaging": [
		"Plain XRay without contrast enhancement",
		"General ultrasound",
		"Contrast enhanced examinations",
		"Magnetic Resonance Imaging",
		"Computerized Tomography",
		"Mammography",
		"Obstetric ultrasound",
	],
}


def age_band(age):
	if age is None:
		return "5-59"
	return "<5" if age < 5 else ("5-59" if age < 60 else "60+")


def compute(company, year, month):
	start, end = period(year, month)
	rows = []

	def section(title):
		rows.append({"indicator": title, "value": None, "is_section": 1})

	def add(indicator, value, note=None):
		rows.append({"indicator": indicator, "value": value, "note": note})

	# Outpatient attendances
	encounters = frappe.get_all(
		"Patient Encounter",
		filters={
			"company": company,
			"docstatus": 1,
			"encounter_date": ["between", [start, end]],
			"inpatient_record": ["in", ["", None]],
		},
		fields=["patient", "encounter_date", "medical_department"],
		order_by="encounter_date asc, encounter_time asc",
	)
	clinic_of = dict(frappe.get_all("Medical Department", fields=["name", "ke_moh717_clinic"], as_list=True))
	patients = {
		p.name: p
		for p in frappe.get_all(
			"Patient",
			filters={"name": ["in", list({e.patient for e in encounters}) or [""]]},
			fields=["name", "sex", "dob"],
		)
	}
	attendance = Counter()
	seen = set()
	for e in encounters:
		day = getdate(e.encounter_date)
		if (e.patient, day) in seen:
			continue
		seen.add((e.patient, day))
		clinic = clinic_of.get(e.medical_department) or "General Outpatient"
		visit = "New" if first_visit_of_year(company, e.patient, day) else "RE-ATT"
		patient = patients.get(e.patient) or frappe._dict()
		band = age_band(age_on(patient.dob, day))
		sex = patient.sex if patient.sex in ("Male", "Female") else "Other"
		attendance[(clinic, visit, sex, band)] += 1

	section("General Outpatient")
	for visit in ("New", "RE-ATT"):
		for sex in ("Male", "Female"):
			for band in ("<5", "5-59"):
				add(
					f"General OP {visit} ({sex} {band})", attendance[("General Outpatient", visit, sex, band)]
				)
		add(
			f"General OP {visit} (60+)",
			sum(
				v
				for (c, vt, _s, b), v in attendance.items()
				if c == "General Outpatient" and vt == visit and b == "60+"
			),
		)
		other_sex = sum(
			v
			for (c, vt, s, b), v in attendance.items()
			if c == "General Outpatient" and vt == visit and s == "Other" and b != "60+"
		)
		if other_sex:
			add(f"General OP {visit} (sex not recorded)", other_sex)

	section("Special Clinics")
	for clinic in CLINICS[1:]:
		for visit, label in (("New", "New"), ("RE-ATT", "Re_Att")):
			add(
				f"{clinic} ({label})",
				sum(v for (c, vt, _s, _b), v in attendance.items() if c == clinic and vt == visit),
			)

	section("Laboratory")
	add("Number of Laboratory tests", len(lab_tests(company, start, end)))

	_maternity(company, start, end, section, add)
	_inpatient(company, start, end, section, add)

	for title, indicators in NOT_CAPTURED.items():
		section(title)
		for indicator in indicators:
			add(indicator, None, "Not captured yet")
	return rows


def _inpatient(company, start, end, section, add):
	ward_of = dict(
		frappe.get_all("Healthcare Service Unit Type", fields=["name", "ke_moh717_ward"], as_list=True)
	)

	def ward(record):
		unit_type = record.admission_service_unit_type or frappe.db.get_value(
			"Inpatient Occupancy",
			{"parent": record.name, "parenttype": "Inpatient Record"},
			"service_unit",
			order_by="idx asc",
		)
		if unit_type and not frappe.db.exists("Healthcare Service Unit Type", unit_type):
			unit_type = frappe.db.get_value("Healthcare Service Unit", unit_type, "service_unit_type")
		return ward_of.get(unit_type) or "Other Wards"

	admitted = frappe.get_all(
		"Inpatient Record",
		filters={
			"company": company,
			"admitted_datetime": ["between", [f"{start} 00:00:00", f"{end} 23:59:59"]],
		},
		fields=["name", "dob", "admitted_datetime", "admission_service_unit_type"],
	)
	admissions = Counter()
	for r in admitted:
		age = age_on(r.dob, getdate(r.admitted_datetime))
		band = "Under 5" if age is not None and age < 5 else "5+"
		admissions[(ward(r), band)] += 1

	left = frappe.get_all(
		"Inpatient Record",
		filters={
			"company": company,
			"status": "Discharged",
			"discharge_datetime": ["between", [f"{start} 00:00:00", f"{end} 23:59:59"]],
		},
		fields=["name", "admission_service_unit_type", "ke_discharge_outcome"],
	)
	outcomes = Counter((ward(r), r.ke_discharge_outcome or "Discharged") for r in left)

	section("Inpatient")
	for w in WARDS:
		for band in ("Under 5", "5+"):
			add(f"Admissions ({w} {band})", admissions[(w, band)])
	for outcome, label in (
		("Discharged", "Discharges"),
		("Died", "Deaths"),
		("Absconded", "Abscondees"),
		("Referred Out", "Referrals Out of the Facility"),
	):
		for w in WARDS:
			add(f"{label} ({w})", outcomes[(w, outcome)])


MODES = {
	"Spontaneous vaginal delivery": "Normal Deliveries",
	"Caesarean section": "Caesarean sections",
	"Breech delivery": "Breech Deliveries",
	"Assisted vaginal delivery": "Assisted Vaginal Delivery",
}
LOW_BIRTH_WEIGHT_G = 2500


def _maternity(company, start, end, section, add):
	section("Maternal and Child Health")
	for doctype, label, field in (
		("ANC Visit", "ANC", "contact_number"),
		("PNC Visit", "PNC", "visit_number"),
	):
		visits = frappe.get_all(
			doctype,
			filters={"company": company, "docstatus": 1, "visit_date": ["between", [start, end]]},
			pluck=field,
		)
		add(f"New {label} Visits", sum(1 for n in visits if n == 1))
		add(f"{label} RE-ATT", sum(1 for n in visits if n and n > 1))

	deliveries = frappe.get_all(
		"Delivery Record",
		filters={
			"company": company,
			"docstatus": 1,
			"delivery_datetime": ["between", [f"{start} 00:00:00", f"{end} 23:59:59"]],
		},
		fields=[
			"name",
			"mode_of_delivery",
			"place_of_delivery",
			"maternal_condition",
			"maternal_death_audited",
		],
	)
	babies = frappe.get_all(
		"Delivery Newborn",
		filters={"parenttype": "Delivery Record", "parent": ["in", [d.name for d in deliveries] or [""]]},
		fields=["outcome", "birth_weight_g", "condition_at_discharge"],
	)
	section("Maternity")
	modes = Counter(d.mode_of_delivery for d in deliveries if d.place_of_delivery != "Born before arrival")
	for mode, label in MODES.items():
		add(label, modes[mode])
	add("Born before arrival", sum(1 for d in deliveries if d.place_of_delivery == "Born before arrival"))
	add("Maternal deaths", sum(1 for d in deliveries if d.maternal_condition == "Died"))
	add(
		"Maternal deaths Audited",
		sum(1 for d in deliveries if d.maternal_condition == "Died" and d.maternal_death_audited),
	)
	live = [b for b in babies if b.outcome == "Live birth"]
	add("Live births", len(live))
	add("Still births", sum(1 for b in babies if b.outcome != "Live birth"))
	add("Neonatal deaths", sum(1 for b in live if b.condition_at_discharge == "Died"))
	add(
		"Low Birth weight babies",
		sum(1 for b in live if b.birth_weight_g and b.birth_weight_g < LOW_BIRTH_WEIGHT_G),
	)
	add("Total Discharges (new born)", sum(1 for b in live if b.condition_at_discharge == "Alive"))
