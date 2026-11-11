# Copyright (c) 2026, Royce Technologies LTD and Contributors
# See license.txt

"""Pricebooks per payment category (Bethesda's example: consultation cash at
the doctor's charge, SHA-PHC 500, SHA-Mwalimu and UASALAMA 1,000 from one
shared list) through the visit, the consultation and the visit bill."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, add_to_date, today

from royce_health_ke import visit_bill

DEMO_INSURER = "Mlima Health Assurance (Demo)"


class IntegrationTestSchemes(IntegrationTestCase):
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
		self.appointment_type = frappe.db.get_value("Appointment Type", {}, "name")
		if not (
			frappe.db.exists("Insurance Payor", DEMO_INSURER) and self.practitioner and self.appointment_type
		):
			self.skipTest("needs the demo insurer, a practitioner with a fee and an appointment type")
		self.consult_item, self.doctor_fee = frappe.db.get_value(
			"Healthcare Practitioner",
			self.practitioner,
			["op_consulting_charge_item", "op_consulting_charge"],
		)
		self.sha_phc = self.plan("_Test SHA-PHC", self.price_list("_Test SHA-PHC", 500))
		shared = self.price_list("_Test Schemes 1000", 1000)
		self.mwalimu = self.plan("_Test SHA-Mwalimu", shared)
		self.uasalama = self.plan("_Test UASALAMA", shared)
		self.unpriced = self.plan("_Test No Price", self.price_list("_Test Empty", None))

	def price_list(self, name, consult_rate):
		if not frappe.db.exists("Price List", name):
			frappe.get_doc(
				{"doctype": "Price List", "price_list_name": name, "selling": 1, "currency": "KES"}
			).insert()
		if consult_rate and not frappe.db.exists(
			"Item Price", {"price_list": name, "item_code": self.consult_item}
		):
			frappe.get_doc(
				{
					"doctype": "Item Price",
					"price_list": name,
					"item_code": self.consult_item,
					"price_list_rate": consult_rate,
				}
			).insert()
		return name

	def plan(self, name, price_list):
		if not frappe.db.exists("Insurance Payor Eligibility Plan", name):
			frappe.get_doc(
				{
					"doctype": "Insurance Payor Eligibility Plan",
					"insurance_plan_name": name,
					"insurance_payor": DEMO_INSURER,
					"price_list": price_list,
					"is_active": 1,
				}
			).insert()
			frappe.get_doc(
				{
					"doctype": "Item Insurance Eligibility",
					"insurance_plan": name,
					"eligibility_for": "Item",
					"item_code": self.consult_item,
					"coverage": 100,
					"discount": 0,
					"mode_of_approval": "Automatic",
					"valid_from": add_days(today(), -30),
					"is_active": 1,
				}
			).insert(ignore_permissions=True)
		return name

	def consultation_charge(self, plan=None):
		"""Check a patient in (insured under the plan, or cash), consult and
		submit; the consultation line of the visit bill."""
		frappe.flags.in_test = True
		patient = (
			frappe.get_doc(
				{
					"doctype": "Patient",
					"first_name": "Scheme",
					"last_name": f"Test {frappe.generate_hash(length=6)}",
					"sex": "Female",
					"dob": add_to_date(today(), years=-40),
				}
			)
			.insert(ignore_permissions=True)
			.name
		)
		insurance = (
			{
				"payment_method": "Insurance",
				"insurance_payor": DEMO_INSURER,
				"insurance_plan": plan,
				"member_number": f"M-{frappe.generate_hash(length=6)}",
				"policy_expiry": add_days(today(), 100),
			}
			if plan
			else {}
		)
		visit = frappe.get_doc(
			{
				"doctype": "Patient Visit",
				"patient": patient,
				"company": self.company,
				"visit_type": "Outpatient",
				"appointment_type": self.appointment_type,
				"practitioner": self.practitioner,
				**insurance,
			}
		).insert(ignore_permissions=True)
		encounter = frappe.get_doc(
			{
				"doctype": "Patient Encounter",
				"patient": patient,
				"practitioner": self.practitioner,
				"encounter_date": today(),
				"company": self.company,
			}
		).insert(ignore_permissions=True)
		encounter.submit()
		self.assertEqual(encounter.insurance_policy, visit.insurance_policy)
		bill = visit_bill.visit_bill(visit.name)
		self.assertFalse(bill.get("error"))
		return next(c for c in bill["charges"] if c["reference_dt"] == "Patient Encounter")

	def test_each_scheme_bills_its_consultation_price(self):
		for plan, rate in ((self.sha_phc, 500), (self.mwalimu, 1000), (self.uasalama, 1000)):
			line = self.consultation_charge(plan)
			self.assertEqual(line["rate"], rate, plan)
			self.assertEqual(line["insurance"], rate, plan)  # 100% covered: on the claim

	def test_cash_and_unpriced_schemes_pay_the_doctors_fee(self):
		self.assertEqual(self.consultation_charge()["rate"], self.doctor_fee)
		line = self.consultation_charge(self.unpriced)
		self.assertEqual((line["rate"], line["insurance"]), (self.doctor_fee, self.doctor_fee))
