# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""The visit's running bill and payment before service."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_to_date, nowdate, today

from royce_health_ke import visit_bill


class TestVisitBill(IntegrationTestCase):
	def setUp(self):
		self.company = frappe.db.get_value("Company", {}, "name")
		self.template = frappe.db.get_value(
			"Lab Test Template", {"is_billable": 1, "disabled": 0, "item": ["is", "set"]}, "name"
		)
		self.practitioner = frappe.db.get_value(
			"Healthcare Practitioner",
			{"status": "Active", "op_consulting_charge_item": ["is", "set"]},
			"name",
		)
		self.appointment_type = frappe.db.get_value("Appointment Type", {}, "name")
		if not (self.template and self.practitioner and self.appointment_type):
			self.skipTest("needs a billable lab test, a practitioner and an appointment type (load the demo)")
		frappe.flags.ke_test_payment_gate = True
		for field in visit_bill.SETTING.values():
			frappe.db.set_single_value("Kenya Health Settings", field, 1)
		self.patient = (
			frappe.get_doc(
				{
					"doctype": "Patient",
					"first_name": "Bill",
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
		self.visit = frappe.get_doc(
			{
				"doctype": "Patient Visit",
				"patient": self.patient,
				"company": self.company,
				"visit_type": "Outpatient",
				"appointment_type": self.appointment_type,
				"practitioner": self.practitioner,
			}
		).insert(ignore_permissions=True)

	def tearDown(self):
		frappe.flags.ke_test_payment_gate = False

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
		self.assertEqual(encounter.ke_patient_visit, self.visit.name)
		return frappe.db.get_value(
			"Service Request", {"order_group": encounter.name, "template_dt": "Lab Test Template"}, "name"
		)

	def start_lab_test(self, request):
		from healthcare.healthcare.doctype.service_request.service_request import make_lab_test

		return make_lab_test(request).insert(ignore_permissions=True)

	def bill_and_submit(self):
		si = frappe.get_doc(visit_bill.make_bill(self.visit.name))
		si.insert(ignore_permissions=True)
		si.submit()
		return si

	def test_lab_waits_for_payment(self):
		request = self.order_lab_test()
		bill = visit_bill.visit_bill(self.visit.name)
		self.assertEqual(bill["status"], "To Bill")
		self.assertIn(request, [c["reference_dn"] for c in bill["charges"]])
		self.assertGreater(bill["unbilled_total"], 0)
		self.assertEqual(frappe.db.get_value("Patient Visit", self.visit.name, "bill_status"), "To Bill")
		with self.assertRaises(frappe.ValidationError):
			self.start_lab_test(request)

		si = self.bill_and_submit()
		self.assertEqual(si.ke_patient_visit, self.visit.name)
		self.assertEqual(si.grand_total, bill["unbilled_total"])  # the bill shown is the bill made
		self.assertEqual(frappe.db.get_value("Patient Visit", self.visit.name, "bill_status"), "Unpaid")
		with self.assertRaises(frappe.ValidationError):
			self.start_lab_test(request)  # billed is not paid

		from royce_health_ke.demo.journey import _pay

		_pay(si, "TEST-PAY-1")
		self.assertEqual(frappe.db.get_value("Patient Visit", self.visit.name, "bill_status"), "Paid")
		bill = visit_bill.visit_bill(self.visit.name)
		self.assertEqual((bill["charges"], bill["balance"]), ([], 0))
		self.assertTrue(self.start_lab_test(request).name)

	def test_manager_approves_services_before_payment(self):
		request = self.order_lab_test()
		visit_bill.approve_credit(self.visit.name, "Staff member, pays at month end")
		self.assertEqual(frappe.db.get_value("Patient Visit", self.visit.name, "allow_credit"), 1)
		self.assertTrue(self.start_lab_test(request).name)

	def test_switched_off(self):
		frappe.db.set_single_value("Kenya Health Settings", "pay_before_lab", 0)
		self.assertTrue(self.start_lab_test(self.order_lab_test()).name)

	def test_one_draft_bill_at_a_time(self):
		self.order_lab_test()
		frappe.get_doc(visit_bill.make_bill(self.visit.name)).insert(ignore_permissions=True)
		self.assertIn("existing", visit_bill.make_bill(self.visit.name))

	def test_drugs_leave_the_store_only_when_paid(self):
		item = frappe.db.get_value("Item", {"is_stock_item": 1, "disabled": 0, "has_batch_no": 0}, "name")
		warehouse = frappe.db.get_value("Warehouse", {"company": self.company, "is_group": 0}, "name")
		if not (item and warehouse):
			self.skipTest("needs a stock item and a warehouse")
		si = frappe.get_doc(
			{
				"doctype": "Sales Invoice",
				"customer": frappe.db.get_value("Patient", self.patient, "customer"),
				"patient": self.patient,
				"company": self.company,
				"posting_date": nowdate(),
				"due_date": nowdate(),
				"update_stock": 1,
				"set_warehouse": warehouse,
				"items": [{"item_code": item, "qty": 1, "rate": 100, "warehouse": warehouse}],
			}
		).insert(ignore_permissions=True)
		self.assertEqual(si.ke_patient_visit, self.visit.name)
		with self.assertRaisesRegex(frappe.ValidationError, "only when paid"):
			si.submit()
