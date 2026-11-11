# Copyright (c) 2026, Royce Technologies LTD and Contributors
# See license.txt

"""Insured visits are billed automatically: a draft invoice kept current as
charges are ordered, submitted when the visit closes."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, add_to_date, today

from royce_health_ke import visits

DEMO_INSURER = "Mlima Health Assurance (Demo)"
DEMO_PLAN = "Corporate Gold (Demo)"


class IntegrationTestInsuredBilling(IntegrationTestCase):
	def setUp(self):
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
		self.templates = frappe.get_all(
			"Lab Test Template",
			filters={"is_billable": 1, "disabled": 0, "item": ["is", "set"]},
			pluck="name",
			limit=2,
		)
		self.appointment_type = frappe.db.get_value("Appointment Type", {}, "name")
		if not (
			frappe.db.exists("Insurance Payor Eligibility Plan", DEMO_PLAN)
			and self.practitioner
			and len(self.templates) == 2
			and self.appointment_type
		):
			self.skipTest("needs the demo insurer and plan, a practitioner and two lab tests")
		frappe.db.set_single_value("Kenya Health Settings", "auto_bill_insured", 1)
		frappe.flags.in_test = True
		self.patient = (
			frappe.get_doc(
				{
					"doctype": "Patient",
					"first_name": "Auto",
					"last_name": f"Bill {frappe.generate_hash(length=6)}",
					"sex": "Female",
					"dob": add_to_date(today(), years=-28),
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

	def visit(self, insured=True):
		insurance = (
			{
				"payment_method": "Insurance",
				"insurance_payor": DEMO_INSURER,
				"insurance_plan": DEMO_PLAN,
				"member_number": f"AB-{frappe.generate_hash(length=6)}",
				"policy_expiry": add_days(today(), 100),
			}
			if insured
			else {}
		)
		return frappe.get_doc(
			{
				"doctype": "Patient Visit",
				"patient": self.patient,
				"company": self.company,
				"visit_type": "Outpatient",
				"appointment_type": self.appointment_type,
				"practitioner": self.practitioner,
				**insurance,
			}
		).insert(ignore_permissions=True)

	def consult(self, template):
		e = frappe.get_doc(
			{
				"doctype": "Patient Encounter",
				"patient": self.patient,
				"practitioner": self.practitioner,
				"encounter_date": today(),
				"company": self.company,
				"lab_test_prescription": [{"lab_test_code": template}],
			}
		).insert(ignore_permissions=True)
		e.submit()
		return e

	def draft(self, visit):
		name = frappe.db.get_value("Sales Invoice", {"ke_patient_visit": visit.name, "docstatus": 0})
		return name and frappe.get_doc("Sales Invoice", name)

	def test_insured_charges_go_on_the_bill_and_it_is_submitted_at_close(self):
		v = self.visit()
		self.consult(self.templates[0])
		si = self.draft(v)
		self.assertTrue(si, "the first charges start a draft bill")
		self.assertEqual(len(si.items), 2)  # consultation and the first test
		self.assertGreater(si.total_insurance_coverage_amount, 0)

		self.consult(self.templates[1])  # a review with another test joins the same draft
		si = self.draft(v)
		self.assertEqual(len(si.items), 4)  # its consultation fee too (unless free follow-ups are on)
		self.assertEqual(frappe.db.count("Sales Invoice", {"ke_patient_visit": v.name}), 1)

		visits.complete(v.name)
		si.reload()
		self.assertEqual(si.docstatus, 1)
		self.assertGreater(si.total_insurance_coverage_amount, 0)
		self.assertEqual(frappe.db.get_value("Patient Visit", v.name, "status"), "Completed")

	def test_cash_visits_are_billed_by_the_cashier(self):
		v = self.visit(insured=False)
		self.consult(self.templates[0])
		self.assertFalse(self.draft(v))

	def test_switched_off(self):
		frappe.db.set_single_value("Kenya Health Settings", "auto_bill_insured", 0)
		v = self.visit()
		self.consult(self.templates[0])
		self.assertFalse(self.draft(v))
		visits.complete(v.name)
		self.assertFalse(frappe.db.exists("Sales Invoice", {"ke_patient_visit": v.name}))
