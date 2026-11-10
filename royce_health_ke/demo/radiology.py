# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Demo radiology: three imaging exams, a radiologist, and Joseph's chest
X-ray from order to released report."""

import frappe
from frappe.utils import add_to_date, getdate, today

from royce_health_ke.demo import journey, masters

EXAMS = (
	# name, item code, modality, MOH 717 row, price (KES)
	("Chest X-ray (PA)", "IMG-CXR", "X-ray", "Plain XRay without contrast enhancement", 1500),
	("Abdominal ultrasound", "IMG-ABUS", "Ultrasound", "General ultrasound", 3000),
	("Obstetric ultrasound", "IMG-OBUS", "Ultrasound", "Obstetric ultrasound", 2500),
)
PATIENT = {
	"first_name": "Joseph",
	"middle_name": "Kamau",
	"last_name": "Njoroge",
	"sex": "Male",
	"mobile": "0712 000 009",
	"occupation": "Farmer",
	"ke_id_type": "National ID",
	"ke_id_number": "0007890",
	"ke_sha_number": "DEMO-SHA-005",
	"ke_county": "Nakuru",
	"ke_nationality": "Kenya",
	"ke_residence": "Nakuru town (demo)",
	"ke_nok_name": "Lucy Wanjiku",
	"ke_nok_relationship": "Spouse",
	"ke_nok_phone": "0712 000 010",
	"patient_details": "DEMO PATIENT - fictional person and identifiers.",
}


def setup(company):
	masters.ensure("Medical Department", "Radiology", {"department": "Radiology"})
	for name, code, modality, moh_row, rate in EXAMS:
		if not frappe.db.exists("Observation Template", name):
			frappe.get_doc(
				{
					"doctype": "Observation Template",
					"observation": name,
					"observation_category": "Imaging",
					"permitted_data_type": "Text",
					"medical_department": "Radiology",
					"is_billable": 1,
					"item_code": code,
					"item_group": "Services",
					"rate": rate,
					"ke_modality": modality,
					"ke_moh717_imaging": moh_row,
				}
			).insert(ignore_permissions=True)
		masters.set_item_tax(company, frappe.db.get_value("Observation Template", name, "item") or code)
	if not frappe.db.exists("Healthcare Practitioner", {"first_name": "Samuel", "last_name": "Mwangi"}):
		frappe.get_doc(
			{
				"doctype": "Healthcare Practitioner",
				"first_name": "Samuel",
				"last_name": "Mwangi",
				"gender": "Male",
				"status": "Active",
				"department": "Radiology",
				"ke_cadre": "Specialist",
				"ke_regulator": "KMPDC",
				"ke_registration_number": "DEMO-D3456",
				"ke_licence_number": "DEMO-L-1004",
				"ke_licence_expiry": add_to_date(today(), days=250),
			}
		).insert(ignore_permissions=True)


def run(company):
	existing = frappe.db.get_value("Patient", {"first_name": "Joseph", "last_name": "Njoroge"})
	if existing:
		return {"patient": existing, "created": False}
	from healthcare.healthcare.doctype.service_request.service_request import make_observation

	from royce_health_ke import radiology

	amina = frappe.db.get_value("Healthcare Practitioner", {"first_name": "Amina"})
	samuel = frappe.db.get_value("Healthcare Practitioner", {"first_name": "Samuel"})
	patient = journey._insert({"doctype": "Patient", **PATIENT, "dob": f"{getdate().year - 58}-03-03"}).name
	customer = frappe.db.get_value("Patient", patient, "customer")
	encounter = journey._insert(
		{
			"doctype": "Patient Encounter",
			"patient": patient,
			"practitioner": amina,
			"appointment_type": "General Consultation",
			"medical_department": "General Medicine",
			"company": company,
			"encounter_date": today(),
			"encounter_time": "09:40:00",
			"symptoms": [{"complaint": "Fever"}],
			"lab_test_prescription": [{"observation_template": "Chest X-ray (PA)"}],
			"encounter_comment": "Productive cough 3 weeks, night sweats, weight loss. Smoker 20 pack-years. "
			"Plan: chest X-ray PA; sputum GeneXpert.",
		},
		submit=True,
	)
	request = frappe.db.get_value(
		"Service Request", {"order_group": encounter.name, "template_dt": "Observation Template"}
	)
	bill = journey._bill(
		company,
		patient,
		customer,
		today(),
		"Radiology: chest X-ray",
		journey._services(patient, customer, company),
	)
	journey._pay(bill, "TKF7DEMO05")
	if journey._etims_active(company):
		journey._register_items(company)
		journey._sign(bill)

	make_observation(request)
	observation = frappe.db.get_value(
		"Observation", {"service_request": request, "parent_observation": ["in", ["", None]]}
	)
	frappe.db.set_value("Observation", observation, "ke_priority", "Urgent")
	radiology.mark_performed(observation, "Radiographer Otieno (demo)", radiation_dose="0.02 mSv")
	radiology.report(
		observation,
		"<p>PA erect view, adequate inspiration. Patchy consolidation with a small cavity in the right upper "
		"zone. Left lung clear. Heart size normal. No pleural effusion. Bones intact.</p>",
		"Right upper zone cavitating consolidation - pulmonary tuberculosis likely. Recommend sputum GeneXpert.",
		samuel,
	)
	radiology.verify(observation, samuel)
	obs = frappe.get_doc("Observation", observation)
	return {
		"patient": patient,
		"created": True,
		"invoice": bill.name,
		"observation": observation,
		"accession": obs.ke_accession_number,
		"exam_status": obs.ke_exam_status,
		"status": obs.status,
		"service_request": frappe.db.get_value("Service Request", request, "status"),
	}
