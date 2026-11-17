# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""The patient flow (flow.py): every move says why, the hospital's switches
turn its rules on and off, and no other code moves a patient."""

import re
from pathlib import Path

import frappe
from frappe.tests import IntegrationTestCase

from royce_health_ke import flow, visit_bill, visits
from royce_health_ke import test_opd_payment as opd

APP = Path(__file__).parent


class TestFlowRules(IntegrationTestCase):
	setUp = opd.TestOutpatientPayment.setUp
	tearDown = opd.TestOutpatientPayment.tearDown
	check_in = opd.TestOutpatientPayment.check_in
	order_lab_test = opd.TestOutpatientPayment.order_lab_test
	bill = opd.TestOutpatientPayment.bill

	def reasons(self, visit):
		return [m.reason for m in frappe.get_doc("Patient Visit", visit).movements]

	def test_every_move_says_why(self):
		visit = self.check_in()
		self.assertEqual(self.reasons(visit.name), [flow.FEE_FIRST])
		self.bill(visit.name, [["Patient Visit", visit.name]])
		_encounter, request = self.order_lab_test()
		visits.send_to(visit.name, "Laboratory")
		self.bill(visit.name, [["Service Request", request]])
		self.assertEqual(self.reasons(visit.name), [flow.FEE_FIRST, flow.FEE_PAID, flow.PAY_FIRST, flow.PAID])
		self.assertEqual(frappe.db.get_value("Patient Visit", visit.name, "current_station"), "Laboratory")

	def test_cashier_first_is_the_hospitals_choice(self):
		frappe.db.set_single_value(flow.SETTINGS, "cashier_before_service", 0)
		self.addCleanup(frappe.db.set_single_value, flow.SETTINGS, "cashier_before_service", 1)
		visit = self.check_in()
		self.bill(visit.name, [["Patient Visit", visit.name]])
		self.order_lab_test()
		r = visits.send_to(visit.name, "Laboratory")
		self.assertEqual((r["station"], r["redirected_from"]), ("Laboratory", None))
		# the lab still doesn't see the unpaid test: that is Laboratory's own switch
		self.assertEqual(visit_bill.awaiting_stations(visit.name), ["Laboratory"])

	def test_check_in_without_a_fee_goes_to_the_first_station(self):
		frappe.db.set_single_value(flow.SETTINGS, "pay_before_triage", 0)
		self.addCleanup(frappe.db.set_single_value, flow.SETTINGS, "pay_before_triage", 1)
		visit = self.check_in()
		self.assertEqual((visit.current_station, self.reasons(visit.name)), ("Triage", [flow.CHECKED_IN]))

	def test_rules_name_real_stations(self):
		for stations, check, purpose in flow.RULES:
			self.assertTrue(set(stations) <= set(flow.STATIONS), purpose)
			self.assertTrue(callable(check))
		self.assertTrue(set(flow.FIRST_STATION.values()) <= set(flow.STATIONS))


class TestOnlyFlowMovesPatients(IntegrationTestCase):
	"""The patient flow has one home: no other module sets the station or
	writes a movement (tests and the demo use flow.move too)."""

	PATTERNS = (
		re.compile(r"""\.append\(\s*["']movements["']"""),
		re.compile(r"""\bcurrent_station\s*=(?!=)"""),
		re.compile(r"""["']current_station["']\s*:"""),
	)
	ALLOWED = ("flow.py", "assign.py")  # assign.py: a query filter, not a move

	def test_no_moves_outside_flow(self):
		offenders = []
		for path in APP.rglob("*.py"):
			if path.name in self.ALLOWED or path.name.startswith("test_"):
				continue
			for n, line in enumerate(path.read_text().splitlines(), 1):
				code = line.split("#", 1)[0]
				if any(p.search(code) for p in self.PATTERNS):
					offenders.append(f"{path.relative_to(APP)}:{n}: {line.strip()}")
		self.assertEqual(offenders, [], "move patients with royce_health_ke.flow")


class TestSeenOnlyWhenAllowed(IntegrationTestCase):
	"""IT team, 17 Nov: a doctor opened a consultation, and triage could take
	vitals, for a cash patient still waiting at the Cashier. The flow's rules
	hold when a station records the patient directly, not only for Send To."""

	check_in = opd.TestOutpatientPayment.check_in
	bill = opd.TestOutpatientPayment.bill

	def setUp(self):
		opd.TestOutpatientPayment.setUp(self)
		frappe.flags.ke_test_flow_gates = True
		frappe.db.set_single_value(flow.SETTINGS, "consultation_fee_due", "Before triage")
		frappe.db.set_single_value(flow.SETTINGS, "consultation_needs_check_in", 1)

	def tearDown(self):
		frappe.flags.ke_test_flow_gates = False
		frappe.flags.ke_test_payment_gate = False
		frappe.db.set_single_value(flow.SETTINGS, "consultation_fee_due", "Before triage")

	def consultation(self):
		return frappe.get_doc(
			{
				"doctype": "Patient Encounter",
				"patient": self.patient,
				"practitioner": self.practitioner,
				"encounter_date": frappe.utils.today(),
				"company": self.company,
			}
		).insert(ignore_permissions=True)

	def vitals(self):
		return frappe.get_doc(
			{
				"doctype": "Vital Signs",
				"patient": self.patient,
				"signs_date": frappe.utils.today(),
				"signs_time": "08:00:00",
				"temperature": "36.8",
			}
		).insert(ignore_permissions=True)

	def test_no_consultation_or_triage_before_the_fee(self):
		visit = self.check_in()
		with self.assertRaisesRegex(frappe.ValidationError, "consultation fee"):
			self.consultation()
		with self.assertRaisesRegex(frappe.ValidationError, "consultation fee"):
			self.vitals()
		self.bill(visit.name, [["Patient Visit", visit.name]])
		self.assertTrue(self.vitals().name)
		self.assertEqual(self.consultation().ke_patient_visit, visit.name)

	def test_manager_approval_lets_the_doctor_see_the_patient(self):
		visit = self.check_in()
		visit_bill.approve_credit(visit.name, "Staff member")
		self.assertTrue(self.consultation().name)

	def test_consultation_needs_a_check_in(self):
		with self.assertRaisesRegex(frappe.ValidationError, "not checked in"):
			self.consultation()
		frappe.db.set_single_value(flow.SETTINGS, "consultation_needs_check_in", 0)
		self.addCleanup(frappe.db.set_single_value, flow.SETTINGS, "consultation_needs_check_in", 1)
		self.assertTrue(self.consultation().name)

	def test_fee_before_the_doctor(self):
		"""Triage first, the fee before the doctor: sent to the doctor unpaid,
		the patient goes to the Cashier and on to the doctor once paid."""
		frappe.db.set_single_value(flow.SETTINGS, "consultation_fee_due", "Before the doctor")
		visit = self.check_in()
		self.assertEqual((visit.fee_first, visit.current_station), (1, "Triage"))
		self.assertTrue(self.vitals().name)  # triage before paying
		with self.assertRaisesRegex(frappe.ValidationError, "consultation fee"):
			self.consultation()

		r = visits.send_to(visit.name, "Consultation")
		self.assertEqual((r["station"], r["redirected_from"]), ("Cashier", "Consultation"))
		self.bill(visit.name, [["Patient Visit", visit.name]])
		visit.reload()
		self.assertEqual((visit.current_station, visit.movements[-1].reason), ("Consultation", flow.FEE_PAID))
		self.assertEqual(visit.practitioner, self.practitioner)
		self.assertTrue(self.consultation().name)
