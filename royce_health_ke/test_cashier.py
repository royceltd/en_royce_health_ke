# Copyright (c) 2026, Royce Technologies LTD and Contributors
# See license.txt

"""Only cashiers take payments; cashier shifts."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_to_date, nowdate, today

from royce_health_ke import cashier


def user(email, roles):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0}
		).insert(ignore_permissions=True)
	doc = frappe.get_doc("User", email)
	doc.add_roles(*roles)
	return email


class IntegrationTestCashier(IntegrationTestCase):
	def setUp(self):
		self.company = frappe.db.get_value("Company", {}, "name")
		self.item = frappe.db.get_value(
			"Item", {"is_stock_item": 0, "disabled": 0, "is_sales_item": 1}, "name"
		)
		self.cash = frappe.db.get_value("Mode of Payment", {"type": "Cash", "enabled": 1}, "name")
		if not (self.company and self.item and self.cash):
			self.skipTest("needs a company, a service item and a cash mode of payment")
		frappe.flags.ke_test_cashier = True
		self.addCleanup(setattr, frappe.flags, "ke_test_cashier", False)
		self.addCleanup(frappe.set_user, "Administrator")
		for field in ("only_cashiers_take_payment", "require_cashier_shift"):
			frappe.db.set_single_value("Kenya Health Settings", field, 0)
		self.cashier = user("ke.cashier@example.com", ["Cashier"])
		self.lab = user("ke.lab@example.com", ["Accounts User", "Laboratory User"])
		# shifts left open by an earlier test of this class
		frappe.db.delete("Cashier Shift", {"cashier": ["in", [self.cashier, self.lab]]})
		frappe.flags.in_test = True
		self.patient = (
			frappe.get_doc(
				{
					"doctype": "Patient",
					"first_name": "Till",
					"last_name": f"Test {frappe.generate_hash(length=6)}",
					"sex": "Male",
					"dob": add_to_date(today(), years=-35),
				}
			)
			.insert(ignore_permissions=True)
			.name
		)
		self.customer = frappe.db.get_value("Patient", self.patient, "customer")
		if not self.customer:
			self.skipTest("patients need a customer")

	def invoice(self, rate=1000):
		si = frappe.get_doc(
			{
				"doctype": "Sales Invoice",
				"customer": self.customer,
				"patient": self.patient,
				"company": self.company,
				"posting_date": nowdate(),
				"due_date": nowdate(),
				"items": [{"item_code": self.item, "qty": 1, "rate": rate}],
			}
		)
		si.set_missing_values()
		si.insert(ignore_permissions=True)
		si.submit()
		return si

	def pay(self, si, as_user, amount=None):
		from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

		frappe.set_user("Administrator")
		pe = get_payment_entry("Sales Invoice", si.name)
		pe.mode_of_payment = self.cash
		pe.reference_no, pe.reference_date = "TEST", nowdate()
		if amount:
			pe.paid_amount = pe.received_amount = amount
			pe.references[0].allocated_amount = amount
		frappe.set_user(as_user)
		try:
			pe.insert()
			pe.submit()
		finally:
			frappe.set_user("Administrator")
		return pe

	def test_only_cashiers_take_payments(self):
		frappe.db.set_single_value("Kenya Health Settings", "only_cashiers_take_payment", 1)
		si = self.invoice()
		with self.assertRaises(frappe.PermissionError):
			self.pay(si, self.lab)
		# the Cashier role alone is enough to take it
		pe = self.pay(si, self.cashier)
		self.assertEqual(pe.docstatus, 1)

	def test_shift_records_payments_and_the_count(self):
		frappe.db.set_single_value("Kenya Health Settings", "require_cashier_shift", 1)
		si = self.invoice(1000)
		with self.assertRaises(frappe.ValidationError):
			self.pay(si, self.cashier)  # no shift open

		frappe.set_user(self.cashier)
		shift = frappe.get_doc(
			{"doctype": "Cashier Shift", "company": self.company, "opening_float": 500}
		).insert()
		frappe.set_user("Administrator")
		self.assertEqual(shift.cashier, self.cashier)
		with self.assertRaises(frappe.ValidationError):  # one open shift per cashier
			frappe.get_doc(
				{"doctype": "Cashier Shift", "company": self.company, "cashier": self.cashier}
			).insert()

		first = self.pay(si, self.cashier, amount=600)
		self.pay(si, self.cashier, amount=400)
		self.assertEqual(first.ke_cashier_shift, shift.name)

		frappe.set_user(self.cashier)
		shift.reload()
		shift.save()  # Refresh Takings
		row = next(r for r in shift.totals if r.mode_of_payment == self.cash)
		self.assertEqual((row.receipts, row.expected), (2, 1500))  # float 500 + 1,000
		row.counted = 1450
		shift.save()
		self.assertEqual(shift.total_difference, -50)
		with self.assertRaises(frappe.ValidationError):
			shift.submit()  # a shortfall needs a note
		shift.reload()
		shift.notes = "KES 50 change given from own pocket"
		shift.submit()
		frappe.set_user("Administrator")
		self.assertEqual(shift.status, "Closed")
		self.assertTrue(shift.closed_at)

	def test_shift_cash_goes_to_the_cashiers_account(self):
		account = frappe.db.get_value(
			"Account", {"company": self.company, "account_type": "Cash", "is_group": 0}, "name"
		)
		if not account:
			self.skipTest("no cash account")
		frappe.db.set_single_value("Kenya Health Settings", "require_cashier_shift", 1)
		frappe.get_doc(
			{
				"doctype": "Cashier Shift",
				"company": self.company,
				"cashier": self.cashier,
				"cash_account": account,
			}
		).insert()
		pe = self.pay(self.invoice(), self.cashier)
		self.assertEqual(pe.paid_to, account)

	def test_non_patient_and_system_payments_are_not_affected(self):
		frappe.db.set_single_value("Kenya Health Settings", "only_cashiers_take_payment", 1)
		frappe.db.set_single_value("Kenya Health Settings", "require_cashier_shift", 1)
		self.assertFalse(
			cashier.is_patient_customer(
				frappe.db.get_value(
					"Customer",
					{
						"name": [
							"not in",
							frappe.get_all("Patient", pluck="customer", filters={"customer": ["is", "set"]}),
						]
					},
				)
			)
		)
		pe = self.pay(self.invoice(), "Administrator")  # e.g. an M-Pesa callback
		self.assertFalse(pe.ke_cashier_shift)

	def test_payment_on_the_invoice_needs_a_cashier(self):
		frappe.db.set_single_value("Kenya Health Settings", "only_cashiers_take_payment", 1)
		si = frappe.get_doc(
			{
				"doctype": "Sales Invoice",
				"customer": self.customer,
				"company": self.company,
				"is_pos": 1,
				"items": [{"item_code": self.item, "qty": 1, "rate": 100}],
				"payments": [{"mode_of_payment": self.cash, "amount": 100}],
			}
		)
		frappe.set_user(self.lab)
		with self.assertRaises(frappe.PermissionError):
			cashier.invoice_before_validate(si)
		frappe.set_user(self.cashier)
		cashier.invoice_before_validate(si)  # allowed
		si.payments[0].amount = 0
		frappe.set_user(self.lab)
		cashier.invoice_before_validate(si)  # billing without payment is fine
