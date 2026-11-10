# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""One patient, walk-in to discharge, through the real Marley and ERPNext
paths the UI uses: registration -> appointment -> triage -> consultation with
lab and drug orders -> cashier (M-Pesa, eTIMS) -> lab results -> review ->
admission -> ward round -> final bill with pharmacy dispensing (M-Pesa,
eTIMS) -> discharge and discharge summary.

The visit starts yesterday morning and the discharge happens now, so the bed
day and the timeline read like a real overnight stay."""

import json

import frappe
from frappe.utils import add_days, get_datetime, getdate, now_datetime, today

from royce_health_ke.demo import masters
from royce_health_ke.utils import installed

PATIENT = {"first_name": "Grace", "middle_name": "Wanjiku", "last_name": "Mwangi"}
DEMO_ITEMS = (
	"CONS-GP",
	"CONS-IP",
	"NURS-IP",
	"KIT-ADM",
	"WARD-GEN",
	"MAT-PKG-NVD",
	"MAT-PKG-CS",
	"MEAL-DAY",
	"LIN-SHEET",
	"LIN-PILLOW",
	"LIN-BLANKET",
	"LIN-GOWN",
	"LAB-BSMPS",
	"LAB-HB",
	"LAB-WBC",
	"DRG-AL20120",
	"DRG-PCM500",
	"DRG-AMX500",
	"IMG-CXR",
	"IMG-ABUS",
	"IMG-OBUS",
	"PROC-APPX",
)
IDENTIFIERS = {
	"ke_id_type": "National ID",
	"ke_id_number": "0001234",
	"ke_sha_number": "DEMO-SHA-001",
	"ke_county": "Nakuru",
	"ke_nationality": "Kenya",
	"ke_residence": "Nakuru town (demo)",
	"ke_sub_county": "Nakuru East",
	"ke_nok_name": "John Mwangi",
	"ke_nok_relationship": "Spouse",
	"ke_nok_phone": "0712 000 002",
}
LAB_RESULTS = {
	"Malaria Blood Slide (BS for MPS)": "P. falciparum seen (++), trophozoites",
	"Haemoglobin (Hb)": "10.8",
	"White Cell Count (WBC)": "6.2",
}
# Tablets dispensed: AL 4 tabs x 6 doses; paracetamol 2 tabs x 9 doses. Marley
# derives a quantity of 1 unless the Prescription Dosage carries strengths.
DISPENSED = {"DRG-AL20120": 24, "DRG-PCM500": 18}


def run(company):
	existing = frappe.db.get_value(
		"Patient", {"first_name": PATIENT["first_name"], "last_name": PATIENT["last_name"]}
	)
	if existing:
		if not frappe.db.get_value("Patient", existing, "ke_id_type"):
			patient = frappe.get_doc("Patient", existing)
			patient.update(IDENTIFIERS)
			patient.save(ignore_permissions=True)
		return {"patient": existing, "created": False}

	a = masters.abbr(company)
	day1 = add_days(today(), -1)
	amina = frappe.db.get_value("Healthcare Practitioner", {"first_name": "Amina"})
	brian = frappe.db.get_value("Healthcare Practitioner", {"first_name": "Brian"})
	etims = _etims_active(company)
	if etims:
		_register_items(company)

	_opening_stock(company, a, etims)

	patient = _register()
	customer = frappe.db.get_value("Patient", patient, "customer")
	appointment = _insert(
		{
			"doctype": "Patient Appointment",
			"patient": patient,
			"appointment_type": "General Consultation",
			"practitioner": amina,
			"department": "General Medicine",
			"service_unit": f"OPD Room 1 - {a}",
			"appointment_date": day1,
			"appointment_time": "10:00:00",
			"duration": 15,
			"company": company,
			"notes": "Walk-in. Fever for 3 days.",
		}
	)
	_insert(
		{
			"doctype": "Vital Signs",
			"patient": patient,
			"appointment": appointment.name,
			"company": company,
			"signs_date": day1,
			"signs_time": "10:05:00",
			"temperature": "38.9",
			"pulse": "104",
			"respiratory_rate": "20",
			"bp_systolic": "118",
			"bp_diastolic": "76",
			"height": 1.65,
			"weight": 62,
			"bmi": 22.8,
			"nutrition_note": "Normal BMI",
			"vital_signs_note": "Triage: Urgent. Febrile, tachycardic, looks pale.",
		},
		submit=True,
	)

	opd = _insert(
		{
			"doctype": "Patient Encounter",
			"patient": patient,
			"appointment": appointment.name,
			"practitioner": amina,
			"appointment_type": "General Consultation",
			"medical_department": "General Medicine",
			"company": company,
			"encounter_date": day1,
			"encounter_time": "10:20:00",
			"symptoms": [{"complaint": c} for c in ("Fever", "Headache", "Chills", "Joint pains")],
			"diagnosis": [{"diagnosis": "Malaria due to P. falciparum, uncomplicated"}],
			"lab_test_prescription": [{"lab_test_code": name} for name in LAB_RESULTS],
			"drug_prescription": [
				{
					"medication": masters.medication("DRG-AL20120"),
					"drug_code": "DRG-AL20120",
					"dosage": "1-0-1 (twice daily)",
					"period": "3 Day",
					"dosage_form": "Tablet",
					"comment": "4 tablets per dose, with fatty food",
				},
				{
					"medication": masters.medication("DRG-PCM500"),
					"drug_code": "DRG-PCM500",
					"dosage": "1-1-1 (three times daily)",
					"period": "3 Day",
					"dosage_form": "Tablet",
					"comment": "2 tablets per dose",
				},
			],
			"encounter_comment": "3/7 fever, chills, headache. Travelled to Kisumu 2 weeks ago. Pale conjunctivae. "
			"Plan: BS for MPS, Hb, WBC. Start AL if positive. Review with results.",
		},
		submit=True,
	)
	for request in frappe.get_all(
		"Medication Request", filters={"order_group": opd.name}, fields=["name", "medication_item"]
	):
		if request.medication_item in DISPENSED:
			qty = DISPENSED[request.medication_item]
			frappe.db.set_value(
				"Medication Request", request.name, {"quantity": qty, "total_dispensable_quantity": qty}
			)

	# Cashier before the lab draws blood: consultation + lab orders.
	opd_bill = _bill(
		company,
		patient,
		customer,
		day1,
		"OPD: consultation + laboratory",
		_services(patient, customer, company),
	)
	_pay(opd_bill, "TKF7DEMO01")
	if etims:
		_sign(opd_bill)

	_run_lab(patient)

	review = _insert(
		{
			"doctype": "Patient Encounter",
			"patient": patient,
			"appointment": appointment.name,  # same visit: not billed twice
			"practitioner": amina,
			"appointment_type": "General Consultation",
			"medical_department": "General Medicine",
			"company": company,
			"encounter_date": day1,
			"encounter_time": "12:30:00",
			"symptoms": [{"complaint": "Vomiting"}, {"complaint": "Fever"}],
			"diagnosis": [
				{"diagnosis": "Malaria due to P. falciparum, uncomplicated"},
				{"diagnosis": "Anaemia, unspecified"},
			],
			"encounter_comment": "Results: BS for MPS P. falciparum ++, Hb 10.8 g/dL, WBC 6.2. Vomited x2 in the "
			"waiting bay, unable to keep oral meds. Admit for observation, antiemetic and supervised first AL doses.",
		},
		submit=True,
	)
	from healthcare.healthcare.doctype.inpatient_record.inpatient_record import (
		schedule_discharge,
		schedule_inpatient,
	)

	schedule_inpatient(
		json.dumps(
			{
				"patient": patient,
				"admission_encounter": review.name,
				"admission_practitioner": amina,
				"primary_practitioner": brian,
				"medical_department": "General Medicine",
				"admission_ordered_for": day1,
				"admission_service_unit_type": "General Ward Bed",
				"expected_length_of_stay": 1,
				"admission_instruction": "Admit General Ward. Vitals 4-hourly. Oral AL supervised. Encourage fluids.",
			}
		)
	)
	inpatient = frappe.get_doc(
		"Inpatient Record", frappe.db.get_value("Patient", patient, "inpatient_record")
	)
	inpatient.admit(f"GW Bed 01 - {a}", get_datetime(f"{day1} 13:00:00"), now_datetime())
	inpatient.reload()

	_insert(
		{
			"doctype": "Patient Encounter",
			"patient": patient,
			"practitioner": brian,
			"inpatient_record": inpatient.name,
			"appointment_type": "General Consultation",
			"medical_department": "General Medicine",
			"company": company,
			"encounter_date": day1,
			"encounter_time": "18:00:00",
			"diagnosis": [{"diagnosis": "Malaria due to P. falciparum, uncomplicated"}],
			"encounter_comment": "Ward round: no further vomiting, tolerating AL. T 37.4. Plan discharge in the "
			"morning with remaining AL doses; OPD review in 7 days with repeat Hb.",
		},
		submit=True,
	)
	_insert(
		{
			"doctype": "Vital Signs",
			"patient": patient,
			"inpatient_record": inpatient.name,
			"company": company,
			"signs_date": day1,
			"signs_time": "18:00:00",
			"temperature": "37.4",
			"pulse": "88",
			"respiratory_rate": "18",
			"bp_systolic": "112",
			"bp_diastolic": "72",
			"vital_signs_note": "Ward vitals. Comfortable.",
		},
		submit=True,
	)

	# Final bill: ward round, bed day, OPD drugs dispensed from Stores, nursing, admission kit (16% VAT).
	from healthcare.healthcare.utils import get_drugs_to_invoice

	lines = _services(patient, customer, company)
	lines += [
		{
			"dn": d["reference_name"],
			"dt": d["reference_type"],
			"item": d["drug_code"],
			"rate": False,
			"income_account": False,
			"qty": d.get("quantity") or False,
			"description": d.get("description") or False,
		}
		for d in get_drugs_to_invoice(opd.name, customer) or []
	]
	final_bill = _bill(
		company,
		patient,
		customer,
		today(),
		f"Inpatient final bill {inpatient.name}",
		lines,
		extra=[("NURS-IP", 1), ("KIT-ADM", 1)],
		warehouse=f"Stores - {a}",
	)
	_pay(final_bill, "TKF7DEMO02")
	if etims:
		_push_stock(company)
		_sign(final_bill)
		_push_stock(company)

	schedule_discharge(
		json.dumps(
			{
				"patient": patient,
				"discharge_practitioner": brian,
				"discharge_ordered_date": today(),
				"followup_date": add_days(today(), 7),
				"discharge_instructions": "Complete AL course (4 tabs twice daily, with food). Paracetamol 1g TDS "
				"if needed. Return at once if vomiting, confusion or yellow eyes. OPD review in 7 days with repeat Hb.",
				"discharge_note": "Uncomplicated P. falciparum malaria with mild anaemia. Improved on oral AL.",
			}
		)
	)
	inpatient.reload()
	inpatient.ke_discharge_outcome = "Discharged"
	inpatient.discharge()
	from healthcare.healthcare.doctype.inpatient_record.inpatient_record import make_discharge_summary

	make_discharge_summary(inpatient.name, ignore_permissions=True).insert(ignore_permissions=True)

	return {
		"patient": patient,
		"created": True,
		"invoices": [opd_bill.name, final_bill.name],
		"etims": {
			si.name: frappe.db.get_value("Sales Invoice", si.name, "royce_etims_status")
			for si in (opd_bill, final_bill)
		}
		if etims
		else "not active",
		"inpatient": inpatient.name,
	}


def _insert(data, submit=False):
	doc = frappe.get_doc(data)
	doc.insert(ignore_permissions=True)
	if submit:
		doc.submit()
	return doc


def _register():
	return _insert(
		{
			"doctype": "Patient",
			**PATIENT,
			"sex": "Female",
			"dob": f"{getdate().year - 34}-04-14",
			"mobile": "+254712000001",
			"blood_group": "O Positive",
			"occupation": "Teacher",
			"marital_status": "Married",
			"allergies": "No known drug allergies",
			"patient_details": "DEMO PATIENT - fictional person and identifiers.",
			**IDENTIFIERS,
		}
	).name


def _services(patient, customer, company):
	"""What Marley's 'Get Items from Healthcare Services' offers the cashier,
	with every key it returns (insurance coverage included) passed through."""
	from healthcare.healthcare.utils import get_healthcare_services_to_invoice

	return [
		{
			**s,
			"dn": s["reference_name"],
			"dt": s["reference_type"],
			"item": s["service"],
			"rate": s.get("rate") or False,
			"income_account": s.get("income_account") or False,
			"qty": s.get("qty") or False,
			"description": s.get("description") or False,
		}
		for s in get_healthcare_services_to_invoice(patient, customer, company)
	]


def _bill(company, patient, customer, posting_date, remarks, lines, extra=(), warehouse=None):
	si = frappe.new_doc("Sales Invoice")
	si.update(
		{
			"customer": customer,
			"patient": patient,
			"company": company,
			"posting_date": posting_date,
			"set_posting_time": 1,
			"due_date": posting_date,
			"remarks": remarks,
			"update_stock": 1 if warehouse else 0,
			"set_warehouse": warehouse,
		}
	)
	si.set_healthcare_services(lines)
	for code, qty in extra:
		si.append("items", {"item_code": code, "qty": qty})
	for row in si.items:
		if row.item_code in DISPENSED:
			row.qty = DISPENSED[row.item_code]
		if warehouse:
			row.warehouse = warehouse
	si.set_missing_values()
	vat = f"KE - Standard VAT 16% - Sales - {masters.abbr(company)}"
	if not si.taxes_and_charges and frappe.db.exists("Sales Taxes and Charges Template", vat):
		si.taxes_and_charges = vat
		si.set_taxes()
	si.calculate_taxes_and_totals()
	si.insert(ignore_permissions=True)
	si.submit()
	return si


def _pay(si, reference):
	from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

	mpesa = frappe.db.exists("Mode of Payment Account", {"parent": "M-Pesa", "company": si.company})
	pe = get_payment_entry("Sales Invoice", si.name)
	pe.mode_of_payment = "M-Pesa" if mpesa else "Cash"
	# get_payment_entry fills the company's default bank; the money is in the
	# mode of payment's own account (M-Pesa, Cash), so day-end balances agree.
	account = frappe.db.get_value(
		"Mode of Payment Account",
		{"parent": pe.mode_of_payment, "company": si.company},
		"default_account",
	)
	if account:
		pe.paid_to = account
		pe.paid_to_account_currency = frappe.db.get_value("Account", account, "account_currency")
	pe.reference_no = reference
	pe.reference_date = si.posting_date
	pe.posting_date = si.posting_date
	pe.insert(ignore_permissions=True)
	pe.submit()


def _run_lab(patient):
	from healthcare.healthcare.doctype.service_request.service_request import make_lab_test

	for request in frappe.get_all(
		"Service Request", filters={"patient": patient, "template_dt": "Lab Test Template"}, fields=["name"]
	):
		lab_test = make_lab_test(request.name)
		lab_test.insert(ignore_permissions=True)
		for row in lab_test.normal_test_items:
			row.result_value = LAB_RESULTS.get(lab_test.template, "")
		lab_test.lab_test_comment = "Reported by the duty lab technologist (demo)."
		lab_test.save(ignore_permissions=True)
		lab_test.submit()


def _opening_stock(company, a, etims):
	remark = "Demo opening pharmacy stock"
	if frappe.db.exists("Stock Entry", {"remarks": remark, "company": company, "docstatus": 1}):
		return
	costs = {code: cost for *_, code, _rate, cost in masters.MEDICINES}
	_insert(
		{
			"doctype": "Stock Entry",
			"stock_entry_type": "Material Receipt",
			"company": company,
			"remarks": remark,
			"items": [
				{
					"item_code": "DRG-AL20120",
					"qty": 480,
					"basic_rate": costs["DRG-AL20120"],
					"t_warehouse": f"Stores - {a}",
				},
				{
					"item_code": "DRG-PCM500",
					"qty": 1000,
					"basic_rate": costs["DRG-PCM500"],
					"t_warehouse": f"Stores - {a}",
				},
				{
					"item_code": "DRG-AMX500",
					"qty": 500,
					"basic_rate": costs["DRG-AMX500"],
					"t_warehouse": f"Stores - {a}",
				},
				{"item_code": "KIT-ADM", "qty": 50, "basic_rate": 400, "t_warehouse": f"Stores - {a}"},
			],
		},
		submit=True,
	)
	if etims:
		_push_stock(company)


# eTIMS: run inline so the demo is complete without a background worker. Each
# call is safe to repeat - signing and stock movements lock and skip what KRA
# already has.


def _etims_active(company):
	return installed("royce_etims") and frappe.db.get_value("eTIMS Settings", company, "status") == "Active"


def _register_items(company):
	from royce_etims.etims_sync.item import sync_item
	from royce_etims.utils.id_mapping import get_etims_id

	for code in DEMO_ITEMS:
		if frappe.db.exists("Item", code) and not get_etims_id(frappe.get_doc("Item", code), company):
			sync_item(code, company)
			frappe.db.commit()


def _push_stock(company):
	from royce_etims.etims_sync.stock import process_branch_queue

	frappe.db.commit()
	process_branch_queue(frappe.db.get_value("eTIMS Settings", company, "default_branch"))
	frappe.db.commit()


def _sign(si):
	from royce_etims.etims_sync.receipt import sync_receipt

	# Two tries: royce_etims corrects a band's reported rate from KRA's own
	# rejection and then expects a retry (normally queued for the worker).
	for _attempt in range(2):
		frappe.db.commit()
		if frappe.db.get_value("Sales Invoice", si.name, "royce_etims_status") == "Sent":
			break
		sync_receipt("Sales Invoice", si.name)
	frappe.db.commit()
