# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Outpatient payment flow (v0.35): the consultation fee paid before triage,
the cashier billing only the ticked charges, and unpaid requests kept off the
service points' worklists until paid."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_to_date, today

from royce_health_ke import lab, visit_bill, visits
from royce_health_ke.demo.journey import _pay


class TestOutpatientPayment(IntegrationTestCase):
	def setUp(self):
		self.company = frappe.db.get_single_value(
			"Global Defaults", "default_company"
		) or frappe.db.get_value("Company", {}, "name")
		self.template = frappe.db.get_value(
			"Lab Test Template",
			{"is_billable": 1, "disabled": 0, "item": ["is", "set"], "lab_test_template_type": "Single"},
			"name",
		)
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
		if not (self.template and self.practitioner and self.appointment_type):
			self.skipTest(
				"needs a billable lab test, a charging practitioner and an appointment type (load the demo)"
			)
		frappe.flags.ke_test_payment_gate = True
		for field in visit_bill.SETTING.values():
			frappe.db.set_single_value("Kenya Health Settings", field, 1)
		self.patient = (
			frappe.get_doc(
				{
					"doctype": "Patient",
					"first_name": "Fee",
					"last_name": f"Test {frappe.generate_hash(length=6)}",
					"sex": "Female",
					"dob": add_to_date(today(), years=-30),
				}
			)
			.insert(ignore_permissions=True)
			.name
		)
		if not frappe.db.get_value("Patient", self.patient, "customer"):
			self.skipTest("patients need a customer (Healthcare Settings: link customer to patient)")

	def tearDown(self):
		frappe.flags.ke_test_payment_gate = False

	def check_in(self, **values):
		return frappe.get_doc(
			{
				"doctype": "Patient Visit",
				"patient": self.patient,
				"company": self.company,
				"visit_type": "Outpatient",
				"appointment_type": self.appointment_type,
				"practitioner": self.practitioner,
				**values,
			}
		).insert(ignore_permissions=True)

	def order_lab_test(self):
		encounter = frappe.get_doc(
			{
				"doctype": "Patient Encounter",
				"patient": self.patient,
				"practitioner": self.practitioner,
				"encounter_date": today(),
				"company": self.company,
				"lab_test_prescription": [{"lab_test_code": self.template}],
			}
		).insert(ignore_permissions=True)
		encounter.submit()
		request = frappe.db.get_value(
			"Service Request", {"order_group": encounter.name, "template_dt": "Lab Test Template"}, "name"
		)
		return encounter, request

	def bill(self, visit, lines=None):
		si = frappe.get_doc(visit_bill.make_bill(visit, lines))
		si.insert(ignore_permissions=True)
		si.submit()
		_pay(si, f"TEST-{frappe.generate_hash(length=6)}")
		return si

	def test_fee_paid_before_triage(self):
		visit = self.check_in()
		self.assertEqual((visit.fee_first, visit.current_station), (1, "Cashier"))
		with self.assertRaises(frappe.ValidationError):
			visits.send_to(visit.name, "Triage")
		charges = visit_bill.visit_bill(visit.name)["charges"]
		self.assertEqual([c["reference_dt"] for c in charges], ["Patient Visit"])
		_item, fee = visit_bill.consultation_fee(visit)
		self.assertEqual(charges[0]["amount"], fee)

		si = self.bill(visit.name)
		visit.reload()
		self.assertEqual((visit.fee_paid, visit.invoiced), (1, 1))
		self.assertEqual((visit.current_station, visit.queue_status), ("Triage", "Waiting"))
		self.assertEqual(visit.movements[-1].from_station, "Cashier")
		self.assertTrue(si.name)

		# The consultation is not billed a second time; its lab request is.
		encounter, _request = self.order_lab_test()
		self.assertEqual(frappe.db.get_value("Patient Encounter", encounter.name, "invoiced"), 1)
		refs = [c["reference_dt"] for c in visit_bill.visit_bill(visit.name)["charges"]]
		self.assertNotIn("Patient Encounter", refs)
		self.assertNotIn("Patient Visit", refs)
		self.assertIn("Service Request", refs)

	def test_who_goes_straight_to_triage(self):
		frappe.db.set_single_value("Kenya Health Settings", "pay_before_triage", 0)
		self.assertEqual(self.check_in().current_station, "Triage")
		frappe.db.set_single_value("Kenya Health Settings", "pay_before_triage", 1)
		lab_only = self.check_in(visit_type="Lab only", visit_date=add_to_date(today(), days=1))
		self.assertEqual((lab_only.fee_first, lab_only.current_station), (0, "Laboratory"))

	def test_manager_lets_the_patient_through(self):
		visit = self.check_in()
		visit_bill.approve_credit(visit.name, "Staff member")
		visits.send_to(visit.name, "Triage")
		self.assertEqual(frappe.db.get_value("Patient Visit", visit.name, "current_station"), "Triage")

	def test_cashier_bills_only_what_is_ticked(self):
		visit = self.check_in()
		_encounter, request = self.order_lab_test()
		key = f"visit:{visit.name}"

		# Not paid: off the lab worklist, counted as paying at the Cashier.
		data = lab.worklist("requests", today(), today(), self.company)
		self.assertNotIn(key, [r.key for r in data["rows"]])
		self.assertGreaterEqual(data["awaiting_payment"], 1)
		self.assertEqual(lab.order(key, today(), today())["tests"], [])
		self.assertTrue(visit_bill.request_awaiting_payment(visit_bill.LAB, request))

		# The patient pays the fee only: the test stays off the worklist.
		si = self.bill(visit.name, [["Patient Visit", visit.name]])
		self.assertEqual([i.reference_dt for i in si.items], ["Patient Visit"])
		self.assertIn(request, [c["reference_dn"] for c in visit_bill.visit_bill(visit.name)["charges"]])
		self.assertNotIn(
			key, [r.key for r in lab.worklist("requests", today(), today(), self.company)["rows"]]
		)

		# Then the test: it reaches the lab.
		self.bill(visit.name, [["Service Request", request]])
		self.assertFalse(visit_bill.request_awaiting_payment(visit_bill.LAB, request))
		self.assertIn(key, [r.key for r in lab.worklist("requests", today(), today(), self.company)["rows"]])

	def test_nothing_ticked_is_refused(self):
		visit = self.check_in()
		with self.assertRaises(frappe.ValidationError):
			visit_bill.make_bill(visit.name, [])
		with self.assertRaises(frappe.ValidationError):
			visit_bill.make_bill(visit.name, "[]")

	def test_browser_values(self):
		"""As the form sends them: no list (everything ticked), empty, "null", or JSON."""
		visit = self.check_in()
		expected = [c["reference_dt"] for c in visit_bill.visit_bill(visit.name)["charges"]]
		self.assertTrue(expected)
		for value in (None, "", "null", f'[["Patient Visit", "{visit.name}"]]'):
			bill = visit_bill.make_bill(visit.name, value)
			self.assertEqual([i["reference_dt"] for i in bill["items"]], expected, repr(value))


class TestSettingsKeptOnUpdate(IntegrationTestCase):
	def test_migrate_keeps_a_switch_turned_off(self):
		from royce_health_ke.setup.install import default_settings

		frappe.db.set_single_value("Kenya Health Settings", "clinical_alerts", 0)
		frappe.db.set_single_value("Kenya Health Settings", "pay_before_triage", 0)
		default_settings()
		self.assertEqual(frappe.db.get_single_value("Kenya Health Settings", "clinical_alerts"), 0)
		self.assertEqual(frappe.db.get_single_value("Kenya Health Settings", "pay_before_triage"), 0)
		# a field never saved gets its default
		frappe.db.sql(
			"delete from `tabSingles` where doctype = 'Kenya Health Settings' and field = 'pay_before_triage'"
		)
		default_settings()
		self.assertEqual(frappe.db.get_single_value("Kenya Health Settings", "pay_before_triage"), 1)
