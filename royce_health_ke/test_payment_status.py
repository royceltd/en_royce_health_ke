# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""The stored payment status of an order (payment_status.py): every change
that moves it, lists reading it, actions checking live, and the hourly
safety net."""

import frappe
from frappe.tests import IntegrationTestCase

from royce_health_ke import lab, payment_status, visit_bill
from royce_health_ke import test_opd_payment as opd
from royce_health_ke.demo.journey import _pay
from royce_health_ke.payment_status import BILLED, EXEMPT, NOT_BILLED, PAID, SR


class TestPaymentStatus(IntegrationTestCase):
	setUp = opd.TestOutpatientPayment.setUp
	tearDown = opd.TestOutpatientPayment.tearDown
	check_in = opd.TestOutpatientPayment.check_in
	order_lab_test = opd.TestOutpatientPayment.order_lab_test

	def status(self, request):
		return tuple(frappe.db.get_value(SR, request, ["ke_payment_status", "ke_payment_exemption"]))

	def lab_request(self):
		visit = self.check_in()
		_encounter, request = self.order_lab_test()
		return visit, request

	def test_ordered_billed_paid_and_back(self):
		visit, request = self.lab_request()
		self.assertEqual(self.status(request), (NOT_BILLED, None))

		si = frappe.get_doc(visit_bill.make_bill(visit.name, [[SR, request]]))
		si.insert(ignore_permissions=True)
		self.assertEqual(self.status(request)[0], BILLED)  # on a draft bill

		si.submit()
		self.assertEqual(self.status(request)[0], BILLED)  # submitted, not paid
		_pay(si, f"TEST-{frappe.generate_hash(length=6)}")
		self.assertEqual(self.status(request), (PAID, None))

		payment = frappe.get_value("Payment Entry Reference", {"reference_name": si.name}, "parent")
		frappe.get_doc("Payment Entry", payment).cancel()
		self.assertEqual(self.status(request)[0], BILLED)
		si.reload()
		si.cancel()
		self.assertEqual(self.status(request)[0], NOT_BILLED)

	def test_draft_bill_deleted(self):
		visit, request = self.lab_request()
		si = frappe.get_doc(visit_bill.make_bill(visit.name, [[SR, request]]))
		si.insert(ignore_permissions=True)
		self.assertEqual(self.status(request)[0], BILLED)
		si.delete()
		self.assertEqual(self.status(request)[0], NOT_BILLED)

	def test_manager_approval_exempts_the_visit_orders(self):
		visit, request = self.lab_request()
		visit_bill.approve_credit(visit.name, "Staff member")
		self.assertEqual(self.status(request), (EXEMPT, "approved"))

	def test_lists_read_the_stored_status_actions_check_live(self):
		visit, request = self.lab_request()
		key = f"visit:{visit.name}"
		today = frappe.utils.today()
		self.assertNotIn(key, [r.key for r in lab.worklist("requests", today, today, self.company)["rows"]])

		# A stored status that is wrong (an update missed): the list follows it ...
		frappe.db.set_value(SR, request, "ke_payment_status", PAID)
		self.assertIn(key, [r.key for r in lab.worklist("requests", today, today, self.company)["rows"]])

		# ... but the lab can't start the test: the action checks live and corrects it.
		from healthcare.healthcare.doctype.service_request.service_request import make_lab_test

		with self.assertRaises(frappe.ValidationError):
			make_lab_test(request).insert(ignore_permissions=True)
		self.assertEqual(payment_status.compute(SR, request)[0], NOT_BILLED)

	def test_safety_net_corrects_and_reports_drift(self):
		_visit, request = self.lab_request()
		frappe.db.set_value(SR, request, "ke_payment_status", PAID)
		drifted = payment_status.reconcile(days=1, log_drift=False)
		self.assertIn(f"{SR} {request}: {PAID} -> {NOT_BILLED}", drifted)
		self.assertEqual(self.status(request)[0], NOT_BILLED)
		self.assertNotIn(request, " ".join(payment_status.reconcile(days=1, log_drift=False)))

	def test_drugs(self):
		visit = self.check_in()
		drug = frappe.db.get_value("Medication", {"disabled": 0}, "name")
		item = drug and frappe.db.get_value("Medication Linked Item", {"parent": drug}, "item_code")
		if not item:
			self.skipTest("needs a medication with an item (load the demo)")
		encounter = frappe.get_doc(
			{
				"doctype": "Patient Encounter",
				"patient": self.patient,
				"practitioner": self.practitioner,
				"encounter_date": frappe.utils.today(),
				"company": self.company,
				"drug_prescription": [
					{
						"medication": drug,
						"drug_code": item,
						"dosage": frappe.db.get_value("Prescription Dosage", {}, "name"),
						"period": frappe.db.get_value("Prescription Duration", {}, "name"),
						"dosage_form": frappe.db.get_value("Dosage Form", {}, "name"),
					}
				],
			}
		).insert(ignore_permissions=True)
		encounter.submit()
		mr = frappe.db.get_value("Medication Request", {"order_group": encounter.name}, "name")
		if not mr:
			self.skipTest("the prescription made no Medication Request")
		self.assertEqual(payment_status.stored("Medication Request", mr)[0], NOT_BILLED)
		self.assertTrue(visit_bill.drug_awaiting_payment(mr))
		visit_bill.approve_credit(visit.name, "Staff member")
		self.assertEqual(payment_status.stored("Medication Request", mr), (EXEMPT, "approved"))
		self.assertFalse(visit_bill.drug_awaiting_payment(mr))
