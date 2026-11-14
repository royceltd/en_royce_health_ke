# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Billing approvals (discount, waiver, pay later) and the Patient Bills board."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_to_date, flt, today

from royce_health_ke import approvals, bills, visit_bill

CASHIER = "bar.cashier@example.com"
MANAGER = "bar.manager@example.com"
MANAGER2 = "bar.manager2@example.com"


def _user(email, roles):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": email.split("@")[0],
				"send_welcome_email": 0,
				"user_type": "System User",
			}
		).insert(ignore_permissions=True)
	frappe.get_doc("User", email).add_roles(*roles)


class TestApprovals(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.company = frappe.db.get_single_value(
			"Global Defaults", "default_company"
		) or frappe.db.get_value("Company", {}, "name")
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
		_user(CASHIER, ["Cashier"])
		_user(MANAGER, ["Healthcare Administrator"])
		_user(MANAGER2, ["Accounts Manager"])
		self.patient = (
			frappe.get_doc(
				{
					"doctype": "Patient",
					"first_name": "Approval",
					"last_name": f"Test {frappe.generate_hash(length=6)}",
					"sex": "Female",
					"dob": add_to_date(today(), years=-30),
				}
			)
			.insert(ignore_permissions=True)
			.name
		)
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
		frappe.get_doc(
			{
				"doctype": "Patient Encounter",
				"patient": self.patient,
				"practitioner": self.practitioner,
				"encounter_date": today(),
				"company": self.company,
				"lab_test_prescription": [{"lab_test_code": self.template}],
			}
		).insert(ignore_permissions=True).submit()
		self.bill = frappe.get_doc(visit_bill.make_bill(self.visit.name)).insert(ignore_permissions=True)

	def tearDown(self):
		frappe.set_user("Administrator")

	def ask(self, request_type, user=CASHIER, **kwargs):
		frappe.set_user(user)
		name = approvals.request(self.visit.name, request_type, "Staff member, hardship", **kwargs)
		frappe.set_user("Administrator")
		return name

	def test_discount_is_applied_to_the_draft_bill(self):
		total = flt(self.bill.grand_total)
		name = self.ask("Discount", sales_invoice=self.bill.name, discount_percentage=10)
		frappe.set_user(CASHIER)
		with self.assertRaises(frappe.PermissionError):
			approvals.approve(name)  # the cashier can't decide
		frappe.set_user(MANAGER)
		approvals.approve(name, "OK")
		self.bill.reload()
		self.assertEqual(frappe.db.get_value("Bill Approval Request", name, "status"), "Approved")
		self.assertAlmostEqual(flt(self.bill.grand_total), round(total * 0.9, 2), places=0)
		# The visit's bill: the drafted lines aren't "not billed yet" any more,
		# and what is left to pay is the discounted draft.
		bill = visit_bill.visit_bill(self.visit.name)
		self.assertTrue(all(c["on_draft"] for c in bill["charges"]))
		self.assertEqual(flt(bill["unbilled_total"]), 0)
		self.assertAlmostEqual(flt(bill["to_pay"]), flt(self.bill.grand_total), places=2)
		self.assertEqual(bill["approvals"][0]["status"], "Approved")

	def test_discount_refused_on_a_submitted_bill(self):
		self.bill.submit()
		with self.assertRaisesRegex(frappe.ValidationError, "waiver"):
			self.ask("Discount", sales_invoice=self.bill.name, amount=100)

	def test_waiver_writes_off_the_balance(self):
		self.bill.submit()
		balance = flt(self.bill.outstanding_amount)
		self.assertGreater(balance, 0)
		with self.assertRaises(frappe.ValidationError):
			self.ask("Waiver", sales_invoice=self.bill.name, amount=balance + 1)
		name = self.ask("Waiver", sales_invoice=self.bill.name)  # the whole balance
		self.assertEqual(flt(frappe.db.get_value("Bill Approval Request", name, "amount")), balance)
		frappe.set_user(MANAGER)
		approvals.approve(name)
		self.assertEqual(flt(frappe.db.get_value("Sales Invoice", self.bill.name, "outstanding_amount")), 0)
		je = frappe.db.get_value("Bill Approval Request", name, "journal_entry")
		self.assertTrue(je)

		row = next(r for r in bills.board("Cash", today(), today())["rows"] if r["name"] == self.visit.name)
		self.assertEqual((row["balance"], row["discount"], row["paid"]), (0, balance, 0))

		frappe.set_user("Administrator")
		frappe.get_doc("Journal Entry", je).cancel()
		self.assertEqual(frappe.db.get_value("Bill Approval Request", name, "status"), "Rejected")
		self.assertEqual(
			flt(frappe.db.get_value("Sales Invoice", self.bill.name, "outstanding_amount")), balance
		)

	def test_pay_later(self):
		name = self.ask("Pay Later")
		frappe.set_user(MANAGER2)
		approvals.approve(name)
		visit = frappe.get_doc("Patient Visit", self.visit.name)
		self.assertEqual((visit.allow_credit, visit.credit_approved_by), (1, MANAGER2))
		with self.assertRaises(frappe.ValidationError):
			self.ask("Pay Later")  # already on

	def test_nobody_decides_their_own(self):
		name = self.ask("Pay Later", user=MANAGER)
		frappe.set_user(MANAGER)
		with self.assertRaisesRegex(frappe.ValidationError, "own request"):
			approvals.approve(name)
		frappe.set_user(MANAGER2)
		with self.assertRaises(frappe.ValidationError):
			approvals.reject(name, "")  # a reason is needed
		approvals.reject(name, "Not eligible")
		self.assertEqual(frappe.db.get_value("Bill Approval Request", name, "status"), "Rejected")

	def test_board_shows_the_visit_and_waiting_approvals(self):
		self.ask("Pay Later")
		frappe.set_user(CASHIER)
		m = bills.board("Cash", today(), today())
		row = next(r for r in m["rows"] if r["name"] == self.visit.name)
		self.assertEqual((row["draft"] > 0, row["pending_approvals"]), (True, 1))
		self.assertGreaterEqual(m["approvals_waiting"], 1)
		self.assertNotIn(
			self.visit.name, [r["name"] for r in bills.board("Insurance", today(), today())["rows"]]
		)
		self.assertIn(
			self.visit.name, [r["name"] for r in bills.board("Cash", today(), today(), "Has balance")["rows"]]
		)
		self.assertNotIn(
			self.visit.name, [r["name"] for r in bills.board("Cash", today(), today(), "Cleared")["rows"]]
		)
