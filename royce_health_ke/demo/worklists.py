# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Today's patients for a demo of the lab and pharmacy worklists and the
doctors' Results Inbox: one patient at each stage, all fictional.

    bench --site <site> execute royce_health_ke.demo.worklists.run

Each run gives the demo patients a new visit dated today (once a day), so the
worklists always have something current to show; set the worklists' dates to
today to show only these. Runs only on a site with royce_health_demo set.

Lab Worklist: Mercy (3 tests requested, not paid), Samuel (paid, samples
taken), Esther (results entered, waiting validation; low Hb, high WBC), David
(validated: malaria positive, Hb low for a man), Faith (urgent walk-in from an
outside clinic, not paid). Results Inbox: Dr Amina has David's and Esther's
results unread once validated.

Pharmacy Worklist: Hassan (prescription not billed), David (paid, ready to
dispense), Agnes (paid, 10 of 15 capsules given, the rest waiting), Kevin
(one drug sent back to the doctor, one bought outside), two walk-in counter
sales (one paid and waiting, one dispensed).

Petty cash (`petty_cash()`, also run by `run()`): three requests by staff,
one waiting for the accounts office, one approved, one paid.

Billing approvals (`billing_approvals()`): Mercy's 10% discount and Hassan's
pay-later waiting for the manager; Faith's walk-in bill waived.

`users(password)` makes the demo logins (one per role) with that password."""

import frappe
from frappe.utils import add_to_date, today

from royce_health_ke import lab, pharmacy, visit_bill
from royce_health_ke.demo import DEMO_COMPANY
from royce_health_ke.demo.journey import _pay

BS, HB, WBC = "Malaria Blood Slide (BS for MPS)", "Haemoglobin (Hb)", "White Cell Count (WBC)"
PATIENTS = {
	"mercy": ("Mercy", "Atieno", "Ouma", "Female", 29),
	"samuel": ("Samuel", "Kiptoo", "Langat", "Male", 45),
	"esther": ("Esther", "Nyambura", "Kariuki", "Female", 52),
	"david": ("David", "Ochieng", "Odhiambo", "Male", 38),
	"faith": ("Faith", "Chebet", "Rotich", "Female", 24),
	"hassan": ("Hassan", "Abdi", "Mohamed", "Male", 61),
	"agnes": ("Agnes", "Wambui", "Gitau", "Female", 33),
	"kevin": ("Kevin", "Mutua", "Musyoka", "Male", 27),
}
DRUGS = {
	"DRG-AL20120": ("1-0-1 (twice daily)", "3 Day", "Tablet", 24, "4 tablets per dose, with fatty food"),
	"DRG-PCM500": ("1-1-1 (three times daily)", "3 Day", "Tablet", 18, "2 tablets per dose"),
	"DRG-AMX500": ("1-1-1 (three times daily)", "5 Day", "Capsule", 15, ""),
}
USERS = (
	# email, first, last, roles, practitioner (first name)
	("reception@kijanivalley.example", "Reception", "Desk", ("Receptionist",), None),
	("nurse.wanjiru@kijanivalley.example", "Wanjiru", "Nurse", ("Nursing User",), None),
	("amina.achieng@kijanivalley.example", "Amina", "Achieng", ("Physician",), "Amina"),
	("brian.kiprotich@kijanivalley.example", "Brian", "Kiprotich", ("Physician",), "Brian"),
	("lab@kijanivalley.example", "Lab", "Technologist", ("Laboratory User",), None),
	("pharmacy@kijanivalley.example", "Pharmacy", "Technologist", ("Pharmacist", "Stock User"), None),
	("cashier@kijanivalley.example", "Main", "Cashier", ("Cashier",), None),
	("accounts@kijanivalley.example", "Accounts", "Office", ("Accounts User",), None),
	("manager@kijanivalley.example", "Hospital", "Manager", ("Healthcare Administrator",), None),
)
# Petty cash (kenyan_accountant): requester, purpose, on behalf of, [(what, qty, price, account name)], how far
PETTY_CASH = (
	(
		"reception@kijanivalley.example",
		"Printer toner for reception",
		None,
		[("Toner cartridge", 1, 4500, "Print and Stationery")],
		"pending",
	),
	(
		"nurse.wanjiru@kijanivalley.example",
		"Tea and sugar for the night shift",
		"Ward 3 night nurses",
		[
			("Tea leaves 500 g", 2, 350, "Miscellaneous Expenses"),
			("Sugar 2 kg", 2, 400, "Miscellaneous Expenses"),
		],
		"approved",
	),
	(
		"pharmacy@kijanivalley.example",
		"Courier: urgent drugs from the Nakuru supplier",
		None,
		[("Boda boda courier", 1, 1500, "Postal Expenses")],
		"paid",
	),
)


def _guard():
	if not frappe.conf.get("royce_health_demo"):
		frappe.throw("Demo data is off for this site (royce_health_demo).")
	frappe.set_user("Administrator")
	frappe.local.lang = frappe.local.lang or "en"


def run(company: str = DEMO_COMPANY):
	_guard()
	ctx = frappe._dict(company=company, amina=_practitioner("Amina"), done=[])
	if not ctx.amina:
		frappe.throw("Load the demo first (no Dr Amina).")
	p = {key: _patient(i, *data) for i, (key, data) in enumerate(PATIENTS.items(), 1)}
	if frappe.db.exists("Patient Visit", {"patient": p["mercy"], "visit_date": today()}):
		return {"skipped": "today's demo patients are already in"}
	frappe.db.set_single_value("Kenya Health Settings", "walk_in_lab_practitioner", ctx.amina)

	# Laboratory
	_consult(ctx, p["mercy"], labs=(BS, HB, WBC), station="Cashier")
	samuel = _consult(ctx, p["samuel"], labs=(BS, HB, WBC), station="Laboratory")
	_bill_and_pay(samuel.visit)
	lab.collect(requests=samuel.requests)
	esther = _consult(ctx, p["esther"], labs=(BS, HB, WBC), station="Laboratory")
	_bill_and_pay(esther.visit)
	_results(esther, {BS: "No malaria parasites seen", HB: "9.1", WBC: "13.4"}, validate=False)
	david = _consult(ctx, p["david"], labs=(BS, HB), drugs=("DRG-AL20120", "DRG-PCM500"), station="Pharmacy")
	_bill_and_pay(david.visit)
	_results(david, {BS: "P. falciparum seen (+), trophozoites", HB: "12.9"}, validate=True)
	_ensure_visit(ctx, p["faith"], visit_type="Lab only")
	lab.walk_in(
		p["faith"],
		[HB, WBC],
		practitioner=ctx.amina,
		referred_by="Dr Njoroge, Mlima Clinic (demo)",
		priority="Urgent",
		company=ctx.company,
	)

	# Pharmacy
	_consult(ctx, p["hassan"], drugs=("DRG-AMX500", "DRG-PCM500"), station="Pharmacy")
	agnes = _consult(ctx, p["agnes"], drugs=("DRG-AMX500",), station="Pharmacy")
	pharmacy.bill_drugs(agnes.visit)
	_pay_draft(agnes.visit)
	store = pharmacy.default_warehouse()
	pharmacy.dispense(
		[
			{
				"kind": "mr",
				"ref": agnes.drugs["DRG-AMX500"],
				"qty": 10,
				"instructions": "1 capsule three times daily for 5 days",
			}
		],
		store,
	)
	kevin = _consult(ctx, p["kevin"], drugs=("DRG-AL20120", "DRG-PCM500"), station="Pharmacy")
	pharmacy.buy_outside([kevin.drugs["DRG-PCM500"]], "Patient has paracetamol at home")
	pharmacy.send_back(
		[kevin.drugs["DRG-AL20120"]], "Patient vomited AL last time. Please prescribe an alternative."
	)
	waiting = pharmacy.counter_sale(
		[{"item_code": "DRG-PCM500", "qty": 20, "instructions": "2 tablets up to 4 times a day when needed"}],
		walk_in_name="Mama Achieng (walk-in, demo)",
		company=ctx.company,
	)
	_pay_invoice(waiting["invoice"])
	sold = pharmacy.counter_sale(
		[{"item_code": "DRG-AMX500", "qty": 15, "instructions": "1 capsule three times daily for 5 days"}],
		walk_in_name="Mr Otieno (walk-in, demo)",
		company=ctx.company,
	)
	_pay_invoice(sold["invoice"])
	item = frappe.db.get_value("Sales Invoice Item", {"parent": sold["invoice"]}, "name")
	pharmacy.dispense([{"kind": "sale", "ref": item, "qty": 15}], store)
	frappe.db.commit()
	return {
		"patients": list(p.values()),
		"store": store,
		"petty_cash": petty_cash(ctx.company),
		"approvals": billing_approvals(p),
	}


def billing_approvals(p):
	"""For the Patient Bills board: a 10% discount on Mercy's draft bill and
	pay-later for Hassan, both waiting for a manager; Faith's walk-in bill
	waived by the manager."""
	from royce_health_ke import approvals

	cashier = "cashier@kijanivalley.example"
	manager = "manager@kijanivalley.example"
	if not (frappe.db.exists("User", cashier) and frappe.db.exists("User", manager)):
		return "make the demo logins first (users)"
	visits = {
		key: frappe.db.get_value("Patient Visit", {"patient": p[key], "visit_date": today()}, "name")
		for key in ("mercy", "hassan", "faith")
	}
	bills = {}
	for key in ("mercy", "faith"):
		bill = visit_bill.make_bill(visits[key])
		bills[key] = (
			bill["existing"]
			if bill.get("existing")
			else frappe.get_doc(bill).insert(ignore_permissions=True).name
		)
	frappe.get_doc("Sales Invoice", bills["faith"]).submit()
	frappe.set_user(cashier)
	approvals.request(visits["mercy"], "Discount", "Staff relative: hospital policy 10%", bills["mercy"], 10)
	approvals.request(visits["hassan"], "Pay Later", "Known patient, pays at month end (demo)")
	waiver = approvals.request(
		visits["faith"], "Waiver", "Student, can't pay: waived by the manager (demo)", bills["faith"]
	)
	frappe.set_user(manager)
	approvals.approve(waiver, "Approved for the demo")
	frappe.set_user("Administrator")
	frappe.db.commit()
	return list(visits.values())


def petty_cash(company: str = DEMO_COMPANY):
	"""Today's petty cash requests: one waiting for the accounts office, one
	approved, one paid; the float topped up from M-Pesa first. Needs
	kenyan_accountant with petty cash (v16.8)."""
	_guard()
	if not frappe.db.exists("DocType", "Petty Cash Request"):
		return "kenyan_accountant has no petty cash yet"
	if frappe.db.exists(
		"Petty Cash Request", {"company": company, "posting_date": today(), "purpose": PETTY_CASH[0][1]}
	):
		return "today's petty cash requests are already in"
	from kenyan_accountant import petty_cash as pc

	approver = (
		"accounts@kijanivalley.example"
		if frappe.db.exists("User", "accounts@kijanivalley.example")
		else "Administrator"
	)
	account = pc.petty_cash_account(company)
	if pc.balance(account, company) < 20000:
		source = frappe.db.get_value(
			"Account", {"company": company, "account_name": "M-Pesa", "is_group": 0}
		) or frappe.db.get_value("Account", {"company": company, "account_type": "Bank", "is_group": 0})
		pc.top_up(company, source, 20000 - pc.balance(account, company), "DEMO-TOPUP")
	made = []
	for user, purpose, behalf, lines, stage in PETTY_CASH:
		frappe.set_user(user if frappe.db.exists("User", user) else "Administrator")
		doc = frappe.get_doc(
			{
				"doctype": "Petty Cash Request",
				"company": company,
				"purpose": purpose,
				"on_behalf": 1 if behalf else 0,
				"requested_for": behalf,
				"items": [
					{
						"description": what,
						"qty": qty,
						"rate": rate,
						"expense_account": frappe.db.get_value(
							"Account", {"company": company, "account_name": name, "is_group": 0}
						),
					}
					for what, qty, rate, name in lines
				],
			}
		)
		doc.insert()
		doc.submit()
		frappe.set_user(approver)
		if stage in ("approved", "paid"):
			pc.approve(doc.name, "OK (demo)")
		if stage == "paid":
			pc.pay(doc.name, frappe.db.get_value("User", user, "full_name") or user)
		made.append(doc.name)
	frappe.set_user("Administrator")
	frappe.db.commit()
	return made


# Building blocks


def _practitioner(first):
	return frappe.db.get_value("Healthcare Practitioner", {"first_name": first, "status": "Active"}, "name")


def _patient(i, first, middle, last, sex, age):
	name = frappe.db.get_value("Patient", {"first_name": first, "middle_name": middle, "last_name": last})
	if name:
		return name
	return (
		frappe.get_doc(
			{
				"doctype": "Patient",
				"first_name": first,
				"middle_name": middle,
				"last_name": last,
				"sex": sex,
				"dob": add_to_date(today(), years=-age, days=-41),
				"mobile": f"+25471200{i:04d}",
				"ke_id_type": "National ID",
				"ke_id_number": f"00090{i:02d}",
				"ke_nationality": "Kenya",
				"ke_county": "Nakuru",
				"ke_residence": _residence(i),
				"patient_details": "DEMO PATIENT - fictional person and identifiers.",
			}
		)
		.insert(ignore_permissions=True)
		.name
	)


def _residence(i):
	from royce_health_ke.demo.masters import RESIDENCES, ensure

	place, kind, sub_county = RESIDENCES[i % len(RESIDENCES)]
	ensure(
		"Residence",
		place,
		{"residence_name": place, "residence_type": kind, "county": "Nakuru", "sub_county": sub_county},
	)
	return place


def _ensure_visit(ctx, patient, visit_type="Outpatient"):
	from royce_health_ke.visits import open_visit_for

	return open_visit_for(patient) or (
		frappe.get_doc(
			{
				"doctype": "Patient Visit",
				"patient": patient,
				"company": ctx.company,
				"visit_type": visit_type,
				"appointment_type": "General Consultation" if visit_type == "Outpatient" else None,
				"practitioner": ctx.amina if visit_type == "Outpatient" else None,
				"payment_method": "Cash",
			}
		)
		.insert(ignore_permissions=True)
		.name
	)


def _consult(ctx, patient, labs=(), drugs=(), station=None):
	"""Checked in, seen by Dr Amina (tests and drugs ordered), sent on."""
	from royce_health_ke.visits import _move

	visit = _ensure_visit(ctx, patient)
	encounter = frappe.get_doc(
		{
			"doctype": "Patient Encounter",
			"patient": patient,
			"practitioner": ctx.amina,
			"encounter_date": today(),
			"company": ctx.company,
			"ke_chief_complaint": "Fever and headache for 3 days (demo)",
			"lab_test_prescription": [{"lab_test_code": t} for t in labs],
			"drug_prescription": [
				{
					"medication": frappe.db.get_value("Medication Linked Item", {"item": code}, "parent"),
					"drug_code": code,
					"dosage": DRUGS[code][0],
					"period": DRUGS[code][1],
					"dosage_form": DRUGS[code][2],
					"comment": DRUGS[code][4],
				}
				for code in drugs
			],
		}
	)
	encounter.insert(ignore_permissions=True)
	encounter.submit()
	drug_requests = {}
	for mr in frappe.get_all(
		"Medication Request", filters={"order_group": encounter.name}, fields=["name", "medication_item"]
	):
		# Marley gives 1 unless the dosage carries strengths: set the real quantity
		qty = DRUGS[mr.medication_item][3]
		frappe.db.set_value(
			"Medication Request", mr.name, {"quantity": qty, "total_dispensable_quantity": qty}
		)
		drug_requests[mr.medication_item] = mr.name
	if station:
		v = frappe.get_doc("Patient Visit", visit)
		_move(v, v.current_station, station)
		v.flags.ignore_permissions = True
		v.save()
	return frappe._dict(
		visit=visit,
		encounter=encounter.name,
		requests=frappe.get_all(
			"Service Request",
			filters={"order_group": encounter.name, "template_dt": "Lab Test Template"},
			pluck="name",
		),
		drugs=drug_requests,
	)


def _pay_invoice(name):
	si = frappe.get_doc("Sales Invoice", name)
	if si.docstatus == 0:
		si.submit()
	if si.outstanding_amount > 0:
		_pay(si, f"DEMO-{frappe.generate_hash(length=6).upper()}")


def _pay_draft(visit):
	for name in frappe.get_all(
		"Sales Invoice", filters={"ke_patient_visit": visit, "docstatus": 0}, pluck="name"
	):
		_pay_invoice(name)


def _bill_and_pay(visit):
	"""The cashier bills the visit and takes M-Pesa."""
	bill = visit_bill.make_bill(visit)
	if bill.get("existing"):
		_pay_invoice(bill["existing"])
		return
	si = frappe.get_doc(bill)
	si.insert(ignore_permissions=True)
	_pay_invoice(si.name)


def _results(order, values, validate):
	done = lab.collect(requests=order.requests)["done"]
	entries = []
	for sheet in lab.results_sheet(done):
		test = frappe.db.get_value("Lab Test", sheet["lab_test"], "template")
		entries.append(
			{
				"lab_test": sheet["lab_test"],
				"normal": {r["name"]: values.get(test, "") for r in sheet["normal"] if not r["heading"]},
				"comment": "Demo result",
			}
		)
	lab.save_results(entries, validate=1 if validate else 0)


# Logins


def users(password: str):
	"""One demo login per role (fictional addresses; the demo site's email is
	muted). Doctors are linked to their practitioner records."""
	_guard()
	if not password or len(password) < 10:
		frappe.throw("Give a password of at least 10 characters.")
	from frappe.utils.password import update_password

	made = []
	for email, first, last, roles, practitioner in USERS:
		if not frappe.db.exists("User", email):
			frappe.get_doc(
				{
					"doctype": "User",
					"email": email,
					"first_name": first,
					"last_name": last,
					"send_welcome_email": 0,
					"user_type": "System User",
				}
			).insert(ignore_permissions=True)
		user = frappe.get_doc("User", email)
		user.add_roles(*[r for r in roles if frappe.db.exists("Role", r)])
		update_password(email, password)
		if practitioner:
			name = _practitioner(practitioner)
			if name:
				frappe.db.set_value("Healthcare Practitioner", name, "user_id", email)
		made.append(email)
	frappe.db.commit()
	return made
