# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Demo theatre: Daniel comes in this morning with acute appendicitis, is
admitted and has an emergency open appendicectomy - consent, WHO checklist,
anaesthesia record, operation note - with sutures and gloves issued from the
theatre's stock."""

import frappe
from frappe.utils import add_to_date, get_datetime, getdate, now_datetime, today

from royce_health_ke.codes import ICD10, ICD11, set_coding
from royce_health_ke.demo import journey, masters

PROCEDURE = "Appendicectomy (open)"
DIAGNOSIS = "Acute appendicitis"
CONSUMABLES = (
	# code, name, price (KES), cost, qty per procedure
	("SUT-VIC20", "Vicryl 2-0 suture", 650, 300, 2),
	("GLV-STER75", "Sterile surgical gloves size 7.5 (pair)", 120, 50, 4),
)
PATIENT = {
	"first_name": "Daniel",
	"middle_name": "Mutua",
	"last_name": "Kioko",
	"sex": "Male",
	"mobile": "0712 000 007",
	"occupation": "Student",
	"ke_id_type": "National ID",
	"ke_id_number": "0003456",
	"ke_sha_number": "DEMO-SHA-004",
	"ke_county": "Nakuru",
	"ke_nok_name": "Ruth Kioko",
	"ke_nok_relationship": "Parent",
	"ke_nok_phone": "0712 000 008",
	"patient_details": "DEMO PATIENT - fictional person and identifiers.",
}


def setup(company):
	a = masters.abbr(company)
	for code, name, price, _cost, _qty in CONSUMABLES:
		masters.item(company, code, name, "Consumable", price, stock=1)
	masters.ensure(
		"Medical Department", "Surgery", {"department": "Surgery", "ke_moh717_clinic": "Surgical Clinics"}
	)
	if not frappe.db.exists("Healthcare Service Unit Type", "Operating Theatre"):
		frappe.get_doc(
			{
				"doctype": "Healthcare Service Unit Type",
				"service_unit_type": "Operating Theatre",
				"is_ot": 1,
				"allow_appointments": 1,
			}
		).insert(ignore_permissions=True)
	masters.ensure(
		"Healthcare Service Unit",
		f"Main Theatre - {a}",
		{
			"healthcare_service_unit_name": "Main Theatre",
			"parent_healthcare_service_unit": f"Kijani Valley Hospital - {a}",
			"service_unit_type": "Operating Theatre",
			"warehouse": f"Stores - {a}",
			"company": company,
		},
	)
	if not frappe.db.exists("Clinical Procedure Template", PROCEDURE):
		frappe.get_doc(
			{
				"doctype": "Clinical Procedure Template",
				"template": PROCEDURE,
				"item_code": "PROC-APPX",
				"item_group": "Services",
				"medical_department": "Surgery",
				"is_billable": 1,
				"rate": 85000,
				"description": "Open appendicectomy under general anaesthesia, theatre fee included.",
				"default_duration": 3600,
				"consume_stock": 1,
				"items": [
					{
						"item_code": code,
						"item_name": name,
						"qty": qty,
						"uom": "Nos",
						"stock_uom": "Nos",
						"conversion_factor": 1,
						"transfer_qty": qty,
					}
					for code, name, _p, _c, qty in CONSUMABLES
				],
			}
		).insert(ignore_permissions=True)
		masters.set_item_tax(company, "PROC-APPX")
	if not frappe.db.exists("Healthcare Practitioner", {"first_name": "Halima", "last_name": "Abdi"}):
		frappe.get_doc(
			{
				"doctype": "Healthcare Practitioner",
				"first_name": "Halima",
				"last_name": "Abdi",
				"gender": "Female",
				"status": "Active",
				"department": "Surgery",
				"ke_cadre": "Specialist",
				"ke_regulator": "KMPDC",
				"ke_registration_number": "DEMO-C9012",
				"ke_licence_number": "DEMO-L-1003",
				"ke_licence_expiry": add_to_date(today(), days=300),
			}
		).insert(ignore_permissions=True)
	diagnosis = masters.ensure("Diagnosis", DIAGNOSIS, {"diagnosis": DIAGNOSIS})
	if not diagnosis.get("codification_table"):
		set_coding(diagnosis, ICD11, "DB10.02")
		set_coding(diagnosis, ICD10, "K35.8", "Acute appendicitis, other and unspecified")
		diagnosis.save(ignore_permissions=True)
	_theatre_stock(company, a)


def _theatre_stock(company, a):
	remark = "Demo theatre consumables"
	if frappe.db.exists("Stock Entry", {"remarks": remark, "company": company, "docstatus": 1}):
		return
	etims = journey._etims_active(company)
	if etims:
		from royce_etims.etims_sync.item import sync_item
		from royce_etims.utils.id_mapping import get_etims_id

		for code, *_rest in CONSUMABLES:
			if not get_etims_id(frappe.get_doc("Item", code), company):
				sync_item(code, company)
				frappe.db.commit()
	journey._insert(
		{
			"doctype": "Stock Entry",
			"stock_entry_type": "Material Receipt",
			"company": company,
			"remarks": remark,
			"items": [
				{"item_code": code, "qty": 200, "basic_rate": cost, "t_warehouse": f"Stores - {a}"}
				for code, _n, _p, cost, _q in CONSUMABLES
			],
		},
		submit=True,
	)
	if etims:
		journey._push_stock(company)


def run(company):
	existing = frappe.db.get_value("Patient", {"first_name": "Daniel", "last_name": "Kioko"})
	if existing:
		return {"patient": existing, "created": False}
	from royce_health_ke import theatre

	a = masters.abbr(company)
	brian = frappe.db.get_value("Healthcare Practitioner", {"first_name": "Brian"})
	halima = frappe.db.get_value("Healthcare Practitioner", {"first_name": "Halima"})
	patient = journey._insert({"doctype": "Patient", **PATIENT, "dob": f"{getdate().year - 23}-06-21"}).name
	now = now_datetime()

	encounter = journey._insert(
		{
			"doctype": "Patient Encounter",
			"patient": patient,
			"practitioner": brian,
			"appointment_type": "General Consultation",
			"medical_department": "Surgery",
			"company": company,
			"encounter_date": today(),
			"encounter_time": "07:30:00",
			"source": "Direct",
			"symptoms": [{"complaint": "Vomiting"}, {"complaint": "Fever"}],
			"diagnosis": [{"diagnosis": DIAGNOSIS}],
			"encounter_comment": "18h periumbilical pain migrating to RIF, vomiting x3, T 38.2. Rebound tenderness "
			"McBurney's point. Alvarado 8. Plan: admit, NPO, IV fluids, emergency appendicectomy.",
		},
		submit=True,
	)
	from healthcare.healthcare.doctype.inpatient_record.inpatient_record import schedule_inpatient

	schedule_inpatient(
		frappe.as_json(
			{
				"patient": patient,
				"admission_encounter": encounter.name,
				"admission_practitioner": brian,
				"primary_practitioner": brian,
				"medical_department": "Surgery",
				"admission_ordered_for": today(),
				"admission_service_unit_type": "General Ward Bed",
				"expected_length_of_stay": 2,
				"admission_instruction": "NPO. IV fluids. Prepare for theatre.",
			}
		)
	)
	inpatient = frappe.get_doc(
		"Inpatient Record", frappe.db.get_value("Patient", patient, "inpatient_record")
	)
	inpatient.admit(f"GW Bed 02 - {a}", get_datetime(f"{today()} 08:00:00"), add_to_date(now, days=2))

	start = get_datetime(f"{today()} 09:00:00")
	booking = journey._insert(
		{
			"doctype": "Theatre Booking",
			"patient": patient,
			"procedure_template": PROCEDURE,
			"priority": "Emergency",
			"company": company,
			"inpatient_record": inpatient.name,
			"theatre": f"Main Theatre - {a}",
			"scheduled_start": start,
			"surgeon": brian,
			"anaesthetist": halima,
			"scrub_nurse": "Nurse Mercy (demo)",
		}
	)
	journey._insert(
		{
			"doctype": "Surgical Consent",
			"theatre_booking": booking.name,
			"consent_datetime": add_to_date(start, minutes=-30),
			"explained_by": brian,
			"procedure_explained": "Removal of the inflamed appendix through a small incision in the right lower abdomen.",
			"risks_explained": "Wound infection, bleeding, abscess, injury to bowel, anaesthetic risks, conversion to a larger incision.",
			"alternatives_explained": "Antibiotics alone (higher recurrence, not advised with these findings).",
			"anaesthesia_consent": 1,
			"blood_transfusion_consent": 1,
			"consent_by": "Patient",
			"consenter_name": "Daniel Mutua Kioko",
			"witness_name": "Nurse Mercy (demo)",
		},
		submit=True,
	)
	checklist = journey._insert(
		{
			"doctype": "Surgical Safety Checklist",
			"theatre_booking": booking.name,
			"si_identity_confirmed": 1,
			"si_site_marked": "Yes",
			"si_anaesthesia_check": 1,
			"si_pulse_oximeter": 1,
			"si_known_allergy": "No",
			"si_difficult_airway": "No",
			"si_blood_loss_risk": "No",
			"sign_in_by": "Dr Halima Abdi",
		}
	)
	theatre.start(booking.name)
	journey._insert(
		{
			"doctype": "Anaesthesia Record",
			"theatre_booking": booking.name,
			"asa_class": "ASA I",
			"asa_emergency": 1,
			"fasting_confirmed": 1,
			"weight": 64,
			"airway_assessment": "Mallampati I",
			"anaesthesia_type": "General",
			"airway": "Endotracheal tube",
			"induction_time": add_to_date(start, minutes=10),
			"end_time": add_to_date(start, minutes=65),
			"drugs": [
				{"time": "09:10:00", "drug": "Propofol", "dose": "150 mg", "route": "IV"},
				{"time": "09:10:00", "drug": "Suxamethonium", "dose": "100 mg", "route": "IV"},
				{"time": "09:12:00", "drug": "Ceftriaxone", "dose": "1 g", "route": "IV"},
				{"time": "09:15:00", "drug": "Isoflurane", "dose": "1-1.5%", "route": "Inhalation"},
			],
			"vitals": [
				{"time": "09:05:00", "pulse": 104, "bp_systolic": 124, "bp_diastolic": 78, "spo2": 99},
				{
					"time": "09:30:00",
					"pulse": 92,
					"bp_systolic": 116,
					"bp_diastolic": 72,
					"spo2": 99,
					"etco2": 36,
				},
				{
					"time": "10:00:00",
					"pulse": 88,
					"bp_systolic": 118,
					"bp_diastolic": 74,
					"spo2": 98,
					"etco2": 35,
				},
			],
			"fluids_ml": 1500,
			"blood_loss_ml": 50,
			"urine_output_ml": 200,
			"aldrete_score": 9,
			"recovery_discharge_time": add_to_date(start, minutes=110),
		},
		submit=True,
	)
	checklist.reload()
	checklist.update(
		{
			"to_team_introduced": 1,
			"to_confirmed": 1,
			"to_antibiotic": "Yes",
			"to_imaging": "Not applicable",
			"to_surgeon_events": 1,
			"to_anaesthetist_concerns": 1,
			"to_nursing_sterility": 1,
			"time_out_by": "Dr Brian Kiprotich",
		}
	)
	checklist.save(ignore_permissions=True)
	booking.reload()
	procedure = frappe.get_doc("Clinical Procedure", booking.clinical_procedure)
	procedure.update(
		{
			"ke_indication": "Acute appendicitis, Alvarado 8.",
			"ke_findings": "Inflamed, non-perforated retrocaecal appendix. No pus, no free fluid.",
			"ke_procedure_details": "<p>Lanz incision RIF. Muscle split. Appendix delivered, mesoappendix ligated, base "
			"ligated and appendix excised. Stump inverted. Peritoneum and muscle closed with Vicryl 2-0, skin "
			"subcuticular.</p>",
			"ke_estimated_blood_loss_ml": 50,
			"ke_specimens": "Appendix to histology",
			"ke_post_op_instructions": "Sips at 6h, light diet tomorrow. IV ceftriaxone/metronidazole 24h. "
			"Analgesia. Mobilise. Review wound day 2.",
		}
	)
	procedure.save(ignore_permissions=True)
	checklist.reload()
	checklist.update(
		{
			"so_procedure_recorded": 1,
			"so_counts_correct": 1,
			"so_specimen_labelled": "Yes",
			"so_recovery_reviewed": 1,
			"sign_out_by": "Nurse Mercy (demo)",
		}
	)
	checklist.save(ignore_permissions=True)
	result = theatre.complete(booking.name)
	if journey._etims_active(company):
		journey._push_stock(company)
	booking.reload()
	checklist.reload()
	return {
		"patient": patient,
		"created": True,
		"booking": booking.name,
		"status": booking.status,
		"checklist": [checklist.sign_in_status, checklist.time_out_status, checklist.sign_out_status],
		**result,
	}
