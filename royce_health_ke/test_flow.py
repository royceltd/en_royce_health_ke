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
