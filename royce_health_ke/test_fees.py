# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""The consultation fee rule (v0.36.1): which item, then its price from the
patient's price list, with a fixed amount on the doctor kept as an override."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_to_date, today

from royce_health_ke import fees, visit_bill
from royce_health_ke import hooks as app_hooks

PRACTITIONER = "Healthcare Practitioner"


class TestConsultationFee(IntegrationTestCase):
	def setUp(self):
		self.company = frappe.db.get_single_value(
			"Global Defaults", "default_company"
		) or frappe.db.get_value("Company", {}, "name")
		self.cash = frappe.db.get_single_value("Selling Settings", "selling_price_list")
		self.practitioner = frappe.db.get_value(PRACTITIONER, {"status": "Active"}, "name")
		self.appointment_type = frappe.db.get_value("Appointment Type", {}, "name")
		if not (self.cash and self.practitioner and self.appointment_type):
			self.skipTest("needs a cash price list, a practitioner and a service type (load the demo)")
		self.keep(PRACTITIONER, self.practitioner, ["op_consulting_charge_item", "op_consulting_charge"])
		self.keep_single("Kenya Health Settings", "default_consultation_item")
		self.keep_single("Kenya Health Settings", "pay_before_triage")
		self.general = self.item("General Consultation", 200)
		self.specialist = self.item("Specialist Consultation", 1000)
		self.review = self.item("Review Consultation", 0)

	def keep(self, doctype, name, fields):
		before = frappe.db.get_value(doctype, name, fields, as_dict=True)
		self.addCleanup(lambda: frappe.db.set_value(doctype, name, before, update_modified=False))

	def keep_single(self, doctype, field):
		before = frappe.db.get_single_value(doctype, field)
		self.addCleanup(lambda: frappe.db.set_single_value(doctype, field, before))

	def item(self, name, rate):
		code = f"TEST-{name.upper().replace(' ', '-')}-{frappe.generate_hash(length=4)}"
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": code,
				"item_name": f"{name} (test)",
				"item_group": frappe.db.get_value("Item Group", {"is_group": 0}, "name"),
				"is_stock_item": 0,
				"stock_uom": "Nos",
			}
		).insert(ignore_permissions=True)
		frappe.get_doc(
			{"doctype": "Item Price", "item_code": code, "price_list": self.cash, "price_list_rate": rate}
		).insert(ignore_permissions=True)
		return code

	def doctor(self, item=None, amount=0):
		frappe.db.set_value(
			PRACTITIONER,
			self.practitioner,
			{"op_consulting_charge_item": item, "op_consulting_charge": amount},
			update_modified=False,
		)

	def visit_like(self, **values):
		return frappe._dict(
			practitioner=self.practitioner, company=self.company, payment_method="Cash", **values
		)

	def test_hospital_default_priced_from_the_cash_price_list(self):
		self.doctor()
		frappe.db.set_single_value("Kenya Health Settings", "default_consultation_item", self.general)
		self.assertEqual(fees.consultation_fee(self.visit_like()), (self.general, 200))
		# a new price is one Item Price edit
		frappe.db.set_value("Item Price", {"item_code": self.general}, "price_list_rate", 250)
		self.assertEqual(fees.consultation_fee(self.visit_like()), (self.general, 250))

	def test_doctor_item_wins_and_a_typed_amount_overrides_the_price(self):
		frappe.db.set_single_value("Kenya Health Settings", "default_consultation_item", self.general)
		self.doctor(self.specialist)
		self.assertEqual(fees.consultation_fee(self.visit_like()), (self.specialist, 1000))
		self.doctor(self.specialist, 1500)
		self.assertEqual(fees.consultation_fee(self.visit_like()), (self.specialist, 1500))
		self.assertEqual(fees.fee_item(self.visit_like())[2], "practitioner")

	def test_zero_price_means_no_fee_and_no_warning(self):
		self.doctor(self.review)
		self.assertEqual(fees.consultation_fee(self.visit_like()), (self.review, 0))
		self.assertIsNone(fees.explain(self.visit_like()))

	def test_explain_names_what_is_missing(self):
		self.doctor()
		frappe.db.set_single_value("Kenya Health Settings", "default_consultation_item", None)
		marley_default = frappe.db.get_single_value("Healthcare Settings", "op_consulting_charge_item")
		if not marley_default:
			self.assertIn("No consultation fee is set", fees.explain(self.visit_like()))
		unpriced = self.item("Unpriced Consultation", 0)
		frappe.db.delete("Item Price", {"item_code": unpriced})
		self.doctor(unpriced)
		self.assertIn("has no price", fees.explain(self.visit_like()))

	def test_marley_billing_no_longer_needs_a_typed_amount(self):
		self.doctor(self.general)  # an item, no amount: Marley's own rule stops here
		with self.assertRaises(frappe.ValidationError):
			from healthcare.healthcare.utils import get_appointment_billing_item_and_rate

			get_appointment_billing_item_and_rate(
				frappe._dict(doctype="Patient Appointment", practitioner=self.practitioner)
			)
		frappe.clear_last_message()
		billing = fees.billing_item_and_rate(
			{"doctype": "Patient Encounter", "practitioner": self.practitioner}
		)
		self.assertEqual(billing, {"service_item": self.general, "practitioner_charge": None})
		# the swap lasts only for the block
		from healthcare.healthcare import utils

		original = utils.get_appointment_billing_item_and_rate
		with fees.marley_rule():
			self.assertIs(utils.get_appointment_billing_item_and_rate, fees.billing_item_and_rate)
		self.assertIs(utils.get_appointment_billing_item_and_rate, original)

	def test_invoice_lines_and_fee_before_triage_use_the_rule(self):
		self.doctor()
		frappe.db.set_single_value("Kenya Health Settings", "default_consultation_item", self.general)
		frappe.db.set_single_value("Kenya Health Settings", "pay_before_triage", 1)
		frappe.flags.ke_test_payment_gate = True
		self.addCleanup(lambda: setattr(frappe.flags, "ke_test_payment_gate", False))
		patient = frappe.get_doc(
			{
				"doctype": "Patient",
				"first_name": "Fee",
				"last_name": f"Rule {frappe.generate_hash(length=6)}",
				"sex": "Male",
				"dob": add_to_date(today(), years=-40),
			}
		).insert(ignore_permissions=True)
		if not frappe.db.get_value("Patient", patient.name, "customer"):
			self.skipTest("patients need a customer")
		visit = frappe.get_doc(
			{
				"doctype": "Patient Visit",
				"patient": patient.name,
				"company": self.company,
				"visit_type": "Outpatient",
				"appointment_type": self.appointment_type,
				"practitioner": self.practitioner,
				"payment_method": "Cash",
			}
		).insert(ignore_permissions=True)
		self.assertEqual((visit.fee_first, visit.current_station), (1, "Cashier"))
		charges = visit_bill.visit_bill(visit.name)["charges"]
		self.assertEqual([(c["reference_dt"], c["amount"]) for c in charges], [("Patient Visit", 200)])

		# A later consultation on another visit (not fee first) is priced by the same rule.
		frappe.db.set_single_value("Kenya Health Settings", "pay_before_triage", 0)
		encounter = frappe.get_doc(
			{
				"doctype": "Patient Encounter",
				"patient": patient.name,
				"practitioner": self.practitioner,
				"encounter_date": add_to_date(today(), days=1),
				"company": self.company,
			}
		).insert(ignore_permissions=True)
		encounter.submit()
		lines = fees.get_healthcare_services_to_invoice(
			patient.name, frappe.db.get_value("Patient", patient.name, "customer"), self.company
		)
		line = next(x for x in lines if x.get("reference_name") == encounter.name)
		self.assertEqual((line["service"], line.get("rate")), (self.general, None))

	def test_marley_methods_are_routed_to_the_rule(self):
		overrides = app_hooks.override_whitelisted_methods
		self.assertEqual(
			overrides["healthcare.healthcare.utils.get_healthcare_services_to_invoice"],
			"royce_health_ke.fees.get_healthcare_services_to_invoice",
		)
		self.assertEqual(
			overrides["healthcare.healthcare.utils.get_appointment_billing_item_and_rate"],
			"royce_health_ke.fees.get_appointment_billing_item_and_rate",
		)
