# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""v0.44 (IT demo, 17 Nov 2026): fewer clicks. A queue opens the vital signs
or the consultation; vital signs mark the patient seen and, submitted, send
them to the doctor; a cash visit's fee and requests go on a draft bill by
themselves (once each); the consultation shows the latest vital signs."""

import frappe
from frappe.utils import nowdate, nowtime

from royce_health_ke import consultation, visit_bill, visits
from royce_health_ke.test_consultation import ConsultationCase


def _settings(**values):
	for field, value in values.items():
		frappe.db.set_single_value("Kenya Health Settings", field, value)


class FlowCase(ConsultationCase):
	def vital_signs(self, visit=None, submit=False):
		doc = frappe.get_doc(
			{
				"doctype": "Vital Signs",
				"patient": self.patient,
				"company": self.company,
				"signs_date": nowdate(),
				"signs_time": nowtime(),
				"temperature": "37.2",
				"pulse": "80",
				"bp_systolic": "120",
				"bp_diastolic": "80",
				"ke_patient_visit": (visit or self.visit).name,
			}
		).insert(ignore_permissions=True)
		if submit:
			doc.submit()
		return doc


class TestTriage(FlowCase):
	def setUp(self):
		super().setUp()
		frappe.flags.ke_test_triage_moves = True
		_settings(vitals_send_to_doctor=1)

	def tearDown(self):
		frappe.flags.ke_test_triage_moves = False
		super().tearDown()

	def test_vitals_mark_seen_then_send_to_the_doctor(self):
		self.assertEqual((self.visit.current_station, self.visit.queue_status), ("Triage", "Waiting"))
		vitals = self.vital_signs()
		self.visit.reload()
		self.assertEqual((self.visit.current_station, self.visit.queue_status), ("Triage", "Seen"))
		vitals.submit()
		self.visit.reload()
		self.assertEqual((self.visit.current_station, self.visit.queue_status), ("Consultation", "Waiting"))
		self.assertEqual(self.visit.practitioner, self.practitioner)

	def test_switched_off_the_patient_stays_at_triage(self):
		_settings(vitals_send_to_doctor=0)
		self.vital_signs(submit=True)
		self.visit.reload()
		self.assertEqual((self.visit.current_station, self.visit.queue_status), ("Triage", "Seen"))


class TestOpenStation(FlowCase):
	def test_triage_opens_the_vital_signs(self):
		r = visits.open_station(self.visit.name)
		self.assertEqual(r["doctype"], "Vital Signs")
		self.assertEqual(r["new"]["ke_patient_visit"], self.visit.name)
		draft = self.vital_signs()
		self.assertEqual(visits.open_station(self.visit.name), {"doctype": "Vital Signs", "name": draft.name})

	def test_doctors_queue_opens_the_consultation(self):
		self.visit.reload()
		visits.send_to(self.visit.name, "Consultation", self.practitioner)
		r = visits.open_station(self.visit.name)
		self.assertEqual(r["doctype"], "Patient Encounter")
		self.assertEqual((r["new"]["patient"], r["new"]["practitioner"]), (self.patient, self.practitioner))
		enc = self.encounter(lab=False)
		self.assertEqual(
			visits.open_station(self.visit.name), {"doctype": "Patient Encounter", "name": enc.name}
		)

	def test_unassigned_patient_taken_by_the_doctor_who_opens_them(self):
		visits.send_to(self.visit.name, "Consultation", self.practitioner)
		frappe.db.set_value(
			"Patient Visit", self.visit.name, {"practitioner": None, "consultation_room": None}
		)
		self.encounter(lab=False)
		self.visit.reload()
		self.assertEqual((self.visit.practitioner, self.visit.queue_status), (self.practitioner, "Seen"))

	def test_other_stations_open_the_visit(self):
		visits.send_to(self.visit.name, "Pharmacy")
		self.assertEqual(
			visits.open_station(self.visit.name), {"doctype": "Patient Visit", "name": self.visit.name}
		)


class TestCashDraft(FlowCase):
	def setUp(self):
		super().setUp()
		frappe.flags.ke_test_cash_draft = True
		_settings(auto_bill_cash=1, pay_before_triage=1)

	def tearDown(self):
		frappe.flags.ke_test_cash_draft = False
		super().tearDown()

	def check_in(self):
		return frappe.get_doc(
			{
				"doctype": "Patient Visit",
				"patient": self.patient,
				"company": self.company,
				"visit_type": "Outpatient",
				"appointment_type": self.appointment_type,
				"practitioner": self.practitioner,
			}
		).insert(ignore_permissions=True)

	def lines(self, draft):
		return {(r.reference_dt, r.reference_dn) for r in frappe.get_doc("Sales Invoice", draft).items}

	def test_fee_then_requests_on_one_draft(self):
		frappe.db.set_value("Patient Visit", self.visit.name, "status", "Cancelled")
		visit = self.check_in()
		if not visit.fee_first:
			self.skipTest("needs a consultation fee for the demo's doctor")
		draft = visit_bill._draft(visit.name)
		self.assertTrue(draft)
		self.assertEqual(self.lines(draft), {("Patient Visit", visit.name)})
		self.assertEqual(frappe.db.get_value("Sales Invoice", draft, "docstatus"), 0)

		# the doctor's requests join the same draft when sent
		frappe.db.set_value("Patient Visit", visit.name, "allow_credit", 1)
		enc = self.encounter()
		consultation.send_requests(enc.name)
		request = frappe.db.get_value("Service Request", {"order_group": enc.name}, "name")
		self.assertIn(("Service Request", request), self.lines(draft))
		self.assertEqual(visit_bill._draft(visit.name), draft)
		self.assertTrue(frappe.db.get_value("Service Request", request, "ke_auto_billed"))

		# the cashier takes it off: saving the consultation again doesn't put it back
		si = frappe.get_doc("Sales Invoice", draft)
		si.items = [r for r in si.items if r.reference_dn != request]
		si.save(ignore_permissions=True)
		enc.reload()
		enc.save(ignore_permissions=True)
		self.assertNotIn(("Service Request", request), self.lines(draft))

	def test_insured_visits_are_not_drafted_here(self):
		frappe.db.set_value("Patient Visit", self.visit.name, "payment_method", "Insurance")
		visit = frappe.get_doc("Patient Visit", self.visit.name)
		self.assertIsNone(visit_bill.draft_cash_bill(visit, [("Patient Visit", visit.name)]))

	def test_switched_off(self):
		_settings(auto_bill_cash=0)
		frappe.db.set_value("Patient Visit", self.visit.name, "status", "Cancelled")
		visit = self.check_in()
		self.assertIsNone(visit_bill._draft(visit.name))


class TestLatestVitals(FlowCase):
	def test_consultation_shows_the_visits_vitals(self):
		vitals = self.vital_signs(submit=True)
		v = consultation.latest_vitals(self.patient, self.visit.name)
		self.assertEqual((v["name"], v["bp_systolic"]), (vitals.name, vitals.bp_systolic))
