# Copyright (c) 2026, Royce Technologies LTD and Contributors
# See license.txt

"""An insured patient is served first only for what the scheme covers: the
rest is billed to the patient on a bill of its own and paid first."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, add_to_date, today

from royce_health_ke import coverage, visit_bill, visits

DEMO_INSURER = "Mlima Health Assurance (Demo)"
DEMO_PLAN = "Corporate Gold (Demo)"
COVERED_TEST, UNCOVERED_TEST = "White Cell Count (WBC)", "Haemoglobin (Hb)"
COVERED_DRUG, UNCOVERED_DRUG = "DRG-PCM500", "DRG-AMX500"


class IntegrationTestUncoveredItems(IntegrationTestCase):
	def setUp(self):
		from royce_health_ke.demo import masters

		self.company = frappe.db.get_value("Company", {}, "name")
		self.practitioner = frappe.db.get_value(
			"Healthcare Practitioner",
			{
				"status": "Active",
				"op_consulting_charge_item": ["is", "set"],
				"op_consulting_charge": [">", 0],
			},
			"name",
		)
		self.appointment_type = frappe.db.get_value("Appointment Type", {}, "name")
		self.drugs = {code: masters.medication(code) for code in (COVERED_DRUG, UNCOVERED_DRUG)}
		if not (
			frappe.db.exists("Insurance Payor Eligibility Plan", DEMO_PLAN)
			and frappe.db.exists("Lab Test Template", COVERED_TEST)
			and frappe.db.exists("Lab Test Template", UNCOVERED_TEST)
			and all(self.drugs.values())
			and self.practitioner
			and self.appointment_type
		):
			self.skipTest("needs the demo insurer, plan, lab tests and drugs (load the demo)")
		# the scheme leaves out Hb and amoxicillin (rolled back with the test class)
		for item in ("LAB-HB", UNCOVERED_DRUG):
			for name in frappe.get_all(
				"Item Insurance Eligibility", {"insurance_plan": DEMO_PLAN, "item_code": item}, pluck="name"
			):
				frappe.db.set_value("Item Insurance Eligibility", name, "is_active", 0)
		for field in (*visit_bill.SETTING.values(), "auto_bill_insured", "insured_pay_uncovered"):
			frappe.db.set_single_value("Kenya Health Settings", field, 1)
		frappe.flags.ke_test_payment_gate = True
		self.patient = (
			frappe.get_doc(
				{
					"doctype": "Patient",
					"first_name": "Uncovered",
					"last_name": f"Test {frappe.generate_hash(length=6)}",
					"sex": "Male",
					"dob": add_to_date(today(), years=-35),
				}
			)
			.insert(ignore_permissions=True)
			.name
		)
		if not frappe.db.get_value("Patient", self.patient, "customer"):
			self.skipTest("patients need a customer (Healthcare Settings: link customer to patient)")
		self.visit = frappe.get_doc(
			{
				"doctype": "Patient Visit",
				"patient": self.patient,
				"company": self.company,
				"visit_type": "Outpatient",
				"appointment_type": self.appointment_type,
				"practitioner": self.practitioner,
				"payment_method": "Insurance",
				"insurance_payor": DEMO_INSURER,
				"insurance_plan": DEMO_PLAN,
				"member_number": f"UC-{frappe.generate_hash(length=6)}",
				"policy_expiry": add_days(today(), 100),
			}
		).insert(ignore_permissions=True)

	def tearDown(self):
		frappe.flags.ke_test_payment_gate = False

	def consult(self, tests=(), drugs=()):
		e = frappe.get_doc(
			{
				"doctype": "Patient Encounter",
				"patient": self.patient,
				"practitioner": self.practitioner,
				"encounter_date": today(),
				"company": self.company,
				"lab_test_prescription": [{"lab_test_code": t} for t in tests],
				"drug_prescription": [
					{
						"medication": self.drugs[code],
						"drug_code": code,
						"dosage": "1-0-1 (twice daily)",
						"period": "3 Day",
						"dosage_form": "Tablet",
					}
					for code in drugs
				],
			}
		).insert(ignore_permissions=True)
		e.submit()
		return e

	def request(self, encounter, template):
		return frappe.db.get_value(
			"Service Request", {"order_group": encounter.name, "template_dn": template}, "name"
		)

	def start_lab_test(self, request):
		from healthcare.healthcare.doctype.service_request.service_request import make_lab_test

		return make_lab_test(request).insert(ignore_permissions=True)

	def drafts(self):
		return {
			d.ke_bill_for: frappe.get_doc("Sales Invoice", d.name)
			for d in frappe.get_all(
				"Sales Invoice",
				filters={"ke_patient_visit": self.visit.name, "docstatus": 0},
				fields=["name", "ke_bill_for"],
			)
		}

	def test_uncovered_test_is_paid_first(self):
		e = self.consult(tests=(COVERED_TEST, UNCOVERED_TEST))
		covered, uncovered = self.request(e, COVERED_TEST), self.request(e, UNCOVERED_TEST)
		self.assertTrue(
			coverage.is_covered(frappe.db.get_value("Service Request", covered, "insurance_coverage"))
		)
		self.assertFalse(frappe.db.get_value("Service Request", uncovered, "insurance_coverage"))

		# the insurer's bill takes the covered charges only
		insurer = self.drafts()["Insurer"]
		on_bill = {row.reference_dn for row in insurer.items}
		self.assertIn(covered, on_bill)
		self.assertNotIn(uncovered, on_bill)

		bill = visit_bill.visit_bill(self.visit.name)
		self.assertTrue(bill["split"])
		self.assertGreater(bill["patient_now"], 0)
		self.assertEqual([c["reference_dn"] for c in bill["charges"] if not c["covered"]], [uncovered])

		self.assertTrue(self.start_lab_test(covered).name)  # covered: served first
		with self.assertRaisesRegex(frappe.ValidationError, "not covered"):
			self.start_lab_test(uncovered)

		# the cashier's bill is the patient's share: the uncovered test only
		si = frappe.get_doc(visit_bill.make_bill(self.visit.name))
		self.assertEqual(si.ke_bill_for, "Patient")
		self.assertEqual([row.reference_dn for row in si.items], [uncovered])
		self.assertFalse(si.items[0].get("insurance_coverage"))
		si.insert(ignore_permissions=True)
		self.assertEqual(visit_bill.make_bill(self.visit.name), {"existing": si.name})
		si.submit()
		with self.assertRaises(frappe.ValidationError):
			self.start_lab_test(uncovered)  # billed is not paid

		from royce_health_ke.demo.journey import _pay

		_pay(si, "TEST-UNCOVERED-1")
		self.assertTrue(self.start_lab_test(uncovered).name)
		with self.assertRaisesRegex(frappe.ValidationError, "covered by insurance"):
			visit_bill.make_bill(self.visit.name)  # what is left is the insurer's

		visits.complete(self.visit.name)
		insurer.reload()
		self.assertEqual(insurer.docstatus, 1)
		self.assertNotIn(uncovered, {row.reference_dn for row in insurer.items})

	def test_drugs_get_the_schemes_cover(self):
		e = self.consult(drugs=(COVERED_DRUG, UNCOVERED_DRUG))
		requests = {
			m.medication_item: m.ke_insurance_coverage
			for m in frappe.get_all(
				"Medication Request",
				filters={"order_group": e.name},
				fields=["medication_item", "ke_insurance_coverage"],
			)
		}
		self.assertTrue(coverage.is_covered(requests[COVERED_DRUG]))
		self.assertFalse(requests[UNCOVERED_DRUG])

		lines = {line["item"]: line for line in visit_bill.unbilled_lines(self.visit)}
		self.assertEqual(lines[COVERED_DRUG]["insurance_coverage"], requests[COVERED_DRUG])
		self.assertFalse(lines[UNCOVERED_DRUG].get("insurance_coverage"))

		insurer = self.drafts()["Insurer"]
		drugs = {row.item_code: row for row in insurer.items if row.reference_dt == "Medication Request"}
		self.assertEqual(set(drugs), {COVERED_DRUG})
		self.assertGreater(drugs[COVERED_DRUG].insurance_coverage_amount, 0)

	def test_doctor_is_told_what_the_patient_pays_for(self):
		frappe.local.message_log = []
		self.consult(tests=(UNCOVERED_TEST,))
		messages = " ".join(str(m) for m in frappe.local.message_log)
		self.assertIn("Not covered by", messages)
		self.assertIn(UNCOVERED_TEST, messages)

	def test_switched_off_the_insured_visit_is_served_first(self):
		frappe.db.set_single_value("Kenya Health Settings", "insured_pay_uncovered", 0)
		e = self.consult(tests=(UNCOVERED_TEST,))
		self.assertTrue(self.start_lab_test(self.request(e, UNCOVERED_TEST)).name)
		frappe.db.set_single_value("Kenya Health Settings", "insured_pay_uncovered", 1)

	def test_a_drug_matches_only_its_own_eligibility(self):
		own = coverage.eligibility(COVERED_DRUG, insurance_plan=DEMO_PLAN)
		self.assertEqual(own.item_code, COVERED_DRUG)
		# Marley's lookup would hand back another item's (template-less) eligibility here
		self.assertIsNone(coverage.eligibility(UNCOVERED_DRUG, insurance_plan=DEMO_PLAN))

	def test_uncovered_drugs_leave_the_store_only_when_paid(self):
		warehouse = frappe.db.get_value("Warehouse", {"company": self.company, "is_group": 0}, "name")
		if frappe.db.get_value("Item", UNCOVERED_DRUG, "has_batch_no") or not warehouse:
			self.skipTest("needs an unbatched demo drug and a warehouse")
		si = frappe.get_doc(
			{
				"doctype": "Sales Invoice",
				"customer": frappe.db.get_value("Patient", self.patient, "customer"),
				"patient": self.patient,
				"company": self.company,
				"posting_date": today(),
				"due_date": today(),
				"update_stock": 1,
				"set_warehouse": warehouse,
				"items": [{"item_code": UNCOVERED_DRUG, "qty": 1, "rate": 100, "warehouse": warehouse}],
			}
		).insert(ignore_permissions=True)
		self.assertEqual(si.ke_patient_visit, self.visit.name)
		with self.assertRaisesRegex(frappe.ValidationError, "only when paid"):
			si.submit()  # insured visit, but the scheme doesn't cover it
