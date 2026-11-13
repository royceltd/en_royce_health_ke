# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Demo private insurance on Marley's own model: a fictional insurer and
scheme, an insured patient's outpatient visit, the copay at the cashier, and
the claim through approval, one rejected line, and the insurer's payment.

Marley's flow: services ordered for an insured patient create a Patient
Insurance Coverage each (automatic approval, or manual = pre-authorisation);
the patient's invoice carries the covered share per line and, on submit, a
journal entry moves that share to the insurer's receivable, leaving the
patient to pay the copay; an Insurance Claim then gathers the visit's
coverages for the insurer to approve, reject and pay."""

import frappe
from frappe.utils import add_days, add_years, get_first_day, get_year_ending, getdate, today

from royce_health_ke.demo import journey, masters

INSURER = "Mlima Health Assurance (Demo)"
PLAN = "Corporate Gold (Demo)"
# Item -> (cover %, approval). Outpatient 90% automatic (10% copay);
# inpatient 100%, pre-authorised (manual).
COVER = {
	"CONS-GP": (90, "Automatic"),
	"LAB-BSMPS": (90, "Automatic"),
	"LAB-HB": (90, "Automatic"),
	"LAB-WBC": (90, "Automatic"),
	"DRG-AL20120": (90, "Automatic"),
	"DRG-PCM500": (90, "Automatic"),
	"DRG-AMX500": (90, "Automatic"),
	"CONS-IP": (100, "Manual"),
	"WARD-GEN": (100, "Manual"),
	"NURS-IP": (100, "Manual"),
}
PATIENT = {
	"first_name": "Peter",
	"middle_name": "Otieno",
	"last_name": "Kamau",
	"sex": "Male",
	"mobile": "0712 000 003",
	"occupation": "Accountant",
	"ke_id_type": "National ID",
	"ke_id_number": "0005678",
	"ke_sha_number": "DEMO-SHA-002",
	"ke_county": "Nakuru",
	"ke_nationality": "Kenya",
	"ke_residence": "Nakuru town (demo)",
	"ke_nok_name": "Mary Kamau",
	"ke_nok_relationship": "Spouse",
	"ke_nok_phone": "0712 000 004",
	"patient_details": "DEMO PATIENT - fictional person, identifiers and insurance policy.",
}


def setup(company):
	a = masters.abbr(company)
	receivable = _account(
		company,
		f"Insurance Claims Receivable - {a}",
		frappe.db.get_value(
			"Account", frappe.db.get_value("Company", company, "default_receivable_account"), "parent_account"
		),
		"Receivable",
	)
	expense = _account(company, f"Rejected Insurance Claims - {a}", _expense_group(company), "")
	if not frappe.db.exists("Insurance Payor", INSURER):
		frappe.get_doc(
			{
				"doctype": "Insurance Payor",
				"insurance_payor_name": INSURER,
				"insurance_claim_credit_days": 30,
				"claims_receivable_accounts": [{"company": company, "account": receivable}],
				"rejected_claims_expense_accounts": [{"company": company, "account": expense}],
			}
		).insert(ignore_permissions=True)
	if not frappe.db.exists(
		"Insurance Payor Contract", {"insurance_payor": INSURER, "company": company, "docstatus": 1}
	):
		frappe.get_doc(
			{
				"doctype": "Insurance Payor Contract",
				"insurance_payor": INSURER,
				"company": company,
				"posting_date": today(),
				"start_date": get_first_day(getdate().replace(month=1)),
				"end_date": get_year_ending(add_years(today(), 1)),
				"is_active": 1,
				"default_price_list": "Standard Selling",
			}
		).insert(ignore_permissions=True).submit()
	if not frappe.db.exists("Insurance Payor Eligibility Plan", PLAN):
		frappe.get_doc(
			{
				"doctype": "Insurance Payor Eligibility Plan",
				"insurance_plan_name": PLAN,
				"insurance_payor": INSURER,
				"is_active": 1,
				"price_list": "Standard Selling",
			}
		).insert(ignore_permissions=True)
	for item_code, (cover, approval) in COVER.items():
		if frappe.db.exists("Item Insurance Eligibility", {"insurance_plan": PLAN, "item_code": item_code}):
			continue
		frappe.get_doc(
			{
				"doctype": "Item Insurance Eligibility",
				"insurance_plan": PLAN,
				"eligibility_for": "Item",
				"item_code": item_code,
				"coverage": cover,
				"discount": 0,
				"mode_of_approval": approval,
				"valid_from": get_first_day(getdate().replace(month=1)),
				"is_active": 1,
			}
		).insert(ignore_permissions=True)
	# the demo scheme has a cover list, so insured patients pay first for what it leaves out
	if not frappe.db.exists(
		"Singles", {"doctype": "Kenya Health Settings", "field": "insured_pay_uncovered"}
	):
		frappe.db.set_single_value("Kenya Health Settings", "insured_pay_uncovered", 1)


def _account(company, name, parent, account_type):
	if not frappe.db.exists("Account", name):
		frappe.get_doc(
			{
				"doctype": "Account",
				"account_name": name.rsplit(" - ", 1)[0],
				"company": company,
				"parent_account": parent,
				"account_type": account_type,
			}
		).insert(ignore_permissions=True)
	return name


def _expense_group(company):
	return frappe.db.get_value(
		"Account",
		{"company": company, "root_type": "Expense", "is_group": 1, "account_name": ["like", "%Indirect%"]},
	) or frappe.db.get_value("Account", {"company": company, "root_type": "Expense", "is_group": 1})


def run(company):
	"""Peter, insured, comes to OPD with fever. Idempotent: skipped once Peter exists."""
	existing = frappe.db.get_value("Patient", {"first_name": "Peter", "last_name": "Kamau"})
	if existing:
		claim = frappe.db.get_value("Insurance Claim", {"patient": existing, "docstatus": 1})
		return {"patient": existing, "created": False, "settlement": _settle(claim) if claim else None}

	a = masters.abbr(company)
	amina = frappe.db.get_value("Healthcare Practitioner", {"first_name": "Amina"})
	patient = journey._insert({"doctype": "Patient", **PATIENT, "dob": f"{getdate().year - 41}-08-02"}).name
	customer = frappe.db.get_value("Patient", patient, "customer")
	policy = frappe.get_doc(
		{
			"doctype": "Patient Insurance Policy",
			"patient": patient,
			"insurance_payor": INSURER,
			"insurance_plan": PLAN,
			"policy_number": "DEMO-POL-0001",
			"policy_expiry_date": get_year_ending(add_years(today(), 1)),
		}
	).insert(ignore_permissions=True)
	policy.submit()

	appointment = journey._insert(
		{
			"doctype": "Patient Appointment",
			"patient": patient,
			"appointment_type": "General Consultation",
			"practitioner": amina,
			"department": "General Medicine",
			"service_unit": f"OPD Room 1 - {a}",
			"appointment_date": today(),
			"appointment_time": "11:00:00",
			"duration": 15,
			"company": company,
			"insurance_policy": policy.name,
			"notes": "Insured walk-in. Fever and headache for 2 days.",
		}
	)
	journey._insert(
		{
			"doctype": "Patient Encounter",
			"patient": patient,
			"appointment": appointment.name,
			"practitioner": amina,
			"appointment_type": "General Consultation",
			"medical_department": "General Medicine",
			"company": company,
			"encounter_date": today(),
			"encounter_time": "11:20:00",
			"insurance_policy": policy.name,
			"symptoms": [{"complaint": c} for c in ("Fever", "Headache")],
			"diagnosis": [{"diagnosis": "Malaria due to P. falciparum, uncomplicated"}],
			"lab_test_prescription": [
				{"lab_test_code": "Malaria Blood Slide (BS for MPS)"},
				{"lab_test_code": "White Cell Count (WBC)"},
			],
			"encounter_comment": "2/7 fever, headache. Plan: BS for MPS and WBC; treat if positive.",
		},
		submit=True,
	)

	lines = journey._services(patient, customer, company)
	bill = journey._bill(
		company, patient, customer, today(), "OPD (insured): consultation + laboratory", lines
	)
	bill.reload()
	copay = bill.outstanding_amount
	journey._pay(bill, "TKF7DEMO03")
	if journey._etims_active(company):
		journey._sign(bill)

	claim = _claim(company, patient, policy)
	return {
		"patient": patient,
		"created": True,
		"policy": policy.name,
		"invoice": bill.name,
		"invoice_total": bill.grand_total,
		"insurer_share": bill.total_insurance_coverage_amount,
		"copay_paid": copay,
		"claim": claim,
	}


def _claim(company, patient, policy):
	"""The insurer approves the consultation and malaria slide, rejects the
	WBC ('not indicated'), and pays what it approved."""
	insurer_customer = frappe.db.get_value("Insurance Payor", INSURER, "customer")
	claim = frappe.get_doc(
		{
			"doctype": "Insurance Claim",
			"insurance_payor": INSURER,
			"company": company,
			"customer": insurer_customer,
			"patient": patient,
			"insurance_policy": policy.name,
			"insurance_plan": PLAN,
			"policy_number": policy.policy_number,
			"from_date": add_days(today(), -1),
			"to_date": today(),
			"posting_date": today(),
			"posting_date_based_on": "Sales Invoice",
			"mode_of_payment": "Wire Transfer",
			"due_date": add_days(today(), 30),
		}
	)
	claim.get_coverages()
	claim.insert(ignore_permissions=True)
	claim.submit()

	claim.reload()
	for row in claim.coverages:
		if row.item_code == "LAB-WBC":
			row.status = "Rejected"
			row.payment_error_reason = "Not clinically indicated for this diagnosis (demo)"
		else:
			row.status = "Approved"
	claim.save(ignore_permissions=True)

	from healthcare.healthcare.doctype.insurance_claim.insurance_claim import create_payment_entry

	payment = create_payment_entry(claim.as_json())
	if isinstance(payment, dict):
		payment = frappe.get_doc(payment)
	payment.reference_no = "DEMO-EFT-0001"
	payment.reference_date = today()
	payment.insert(ignore_permissions=True)
	payment.submit()
	claim.reload()
	return {
		"settlement": _settle(claim.name),
		"name": claim.name,
		"status": claim.status,
		"claimed": claim.insurance_claim_amount,
		"approved": claim.approved_amount,
		"rejected": claim.rejected_amount,
		"paid": claim.paid_amount,
		"payment": payment.name,
	}


def _settle(claim_name):
	"""Bill the rejected WBC to Peter, who pays it at the cashier by M-Pesa."""
	from royce_health_ke.claims import BILL_PATIENT, settle_rejected, unsettled_rejections

	claim = frappe.get_doc("Insurance Claim", claim_name)
	if not unsettled_rejections(claim):
		return "already settled"
	entries = settle_rejected(claim_name, BILL_PATIENT)
	customer = frappe.db.get_value("Patient", claim.patient, "customer")
	mode = (
		"M-Pesa"
		if frappe.db.exists("Mode of Payment Account", {"parent": "M-Pesa", "company": claim.company})
		else "Cash"
	)
	from erpnext.accounts.doctype.journal_entry.journal_entry import get_default_bank_cash_account

	paid_to = frappe.db.get_value(
		"Mode of Payment Account", {"parent": mode, "company": claim.company}, "default_account"
	) or get_default_bank_cash_account(claim.company, "Cash").get("account")
	for entry in entries:
		row = frappe.db.get_value(
			"Journal Entry Account",
			{"parent": entry, "party": customer, "debit_in_account_currency": [">", 0]},
			["account", "debit_in_account_currency"],
			as_dict=True,
		)
		payment = frappe.get_doc(
			{
				"doctype": "Payment Entry",
				"payment_type": "Receive",
				"company": claim.company,
				"posting_date": today(),
				"mode_of_payment": mode,
				"party_type": "Customer",
				"party": customer,
				"paid_from": row.account,
				"paid_to": paid_to,
				"paid_amount": row.debit_in_account_currency,
				"received_amount": row.debit_in_account_currency,
				"reference_no": "TKF7DEMO04",
				"reference_date": today(),
				"references": [
					{
						"reference_doctype": "Journal Entry",
						"reference_name": entry,
						"allocated_amount": row.debit_in_account_currency,
					}
				],
			}
		)
		payment.insert(ignore_permissions=True)
		payment.submit()
	return {"billed_to_patient": entries}
