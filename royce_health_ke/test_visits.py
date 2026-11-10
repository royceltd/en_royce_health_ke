# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Patient Visit: check-in, the station queue, insurance at reception, and
vitals and consultations linking to the visit."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, add_to_date, today

from royce_health_ke import visits


def make_patient():
	return (
		frappe.get_doc(
			{
				"doctype": "Patient",
				"first_name": "Visit",
				"last_name": f"Test {frappe.generate_hash(length=6)}",
				"sex": "Male",
				"dob": add_to_date(today(), years=-40),
			}
		)
		.insert(ignore_permissions=True)
		.name
	)


class TestPatientVisit(IntegrationTestCase):
	def setUp(self):
		self.company = frappe.db.get_value("Company", {}, "name")
		self.patient = make_patient()

	def visit(self, **values):
		return frappe.get_doc(
			{
				"doctype": "Patient Visit",
				"patient": self.patient,
				"company": self.company,
				"visit_type": "Lab only",
				**values,
			}
		).insert(ignore_permissions=True)

	def test_check_in_queues_at_the_first_station(self):
		v = self.visit()
		self.assertEqual((v.current_station, v.queue_status, v.status), ("Laboratory", "Waiting", "Open"))
		self.assertEqual(
			(v.movements[0].from_station, v.movements[0].to_station), ("Reception", "Laboratory")
		)
		self.assertEqual(v.age, "40 y")
		self.assertEqual(visits.FIRST_STATION["Outpatient"], "Triage")

	def test_one_open_visit_a_day(self):
		self.visit()
		with self.assertRaises(frappe.ValidationError):
			self.visit()

	def test_send_seen_and_complete(self):
		v = self.visit()
		visits.acknowledge(v.name)
		v.reload()
		self.assertEqual(v.queue_status, "Seen")
		self.assertTrue(v.movements[0].acknowledged_at)
		visits.send_to(v.name, "Pharmacy", note="Collect drugs")
		v.reload()
		self.assertEqual((v.current_station, v.queue_status), ("Pharmacy", "Waiting"))
		self.assertEqual((v.movements[1].from_station, v.movements[1].to_station), ("Laboratory", "Pharmacy"))
		with self.assertRaises(frappe.ValidationError):
			visits.send_to(v.name, "Pharmacy")  # already waiting there
		visits.complete(v.name)
		v.reload()
		self.assertEqual(v.status, "Completed")
		with self.assertRaises(frappe.ValidationError):
			visits.send_to(v.name, "Cashier")

	def test_vital_signs_link_and_flag_the_visit(self):
		v = self.visit()
		vs = frappe.get_doc(
			{
				"doctype": "Vital Signs",
				"patient": self.patient,
				"signs_date": today(),
				"signs_time": "08:00:00",
				"temperature": "39.0",
			}
		).insert(ignore_permissions=True)
		self.assertEqual(vs.ke_patient_visit, v.name)
		self.assertEqual(
			frappe.db.get_value("Patient Visit", v.name, ["vitals_status", "vital_signs"]),
			("Abnormal", vs.name),
		)

	def test_consultation_marks_the_patient_seen(self):
		practitioner = (
			frappe.get_doc(
				{
					"doctype": "Healthcare Practitioner",
					"first_name": "Visit",
					"last_name": "Doctor",
					"status": "Active",
				}
			)
			.insert(ignore_permissions=True)
			.name
		)
		v = self.visit(
			visit_type="Review", appointment_type=frappe.db.get_value("Appointment Type", {}, "name")
		)
		self.assertEqual(v.current_station, "Triage")
		visits.send_to(v.name, "Consultation", practitioner=practitioner)
		encounter = frappe.get_doc(
			{
				"doctype": "Patient Encounter",
				"patient": self.patient,
				"practitioner": practitioner,
				"encounter_date": today(),
				"company": self.company,
			}
		).insert(ignore_permissions=True)
		self.assertEqual(encounter.ke_patient_visit, v.name)
		v.reload()
		self.assertEqual(
			(v.queue_status, v.encounter, v.practitioner), ("Seen", encounter.name, practitioner)
		)


class TestVisitInsurance(IntegrationTestCase):
	def setUp(self):
		self.company = frappe.db.get_value("Company", {}, "name")
		self.payor = frappe.db.get_value("Insurance Payor", {}, "name")
		if not self.payor:
			self.skipTest("needs an Insurance Payor (load the demo)")
		self.patient = make_patient()

	def insured(self, **values):
		return frappe.get_doc(
			{
				"doctype": "Patient Visit",
				"patient": self.patient,
				"company": self.company,
				"visit_type": "Lab only",
				"payment_method": "Insurance",
				"insurance_payor": self.payor,
				**values,
			}
		)

	def test_new_member_gets_a_policy(self):
		v = self.insured(
			member_number="M-555",
			policy_expiry=add_days(today(), 200),
			relation="Spouse",
			principal_member="Principal Test",
			principal_member_number="M-554",
			authorisation_code="AUTH-1",
		).insert(ignore_permissions=True)
		policy = frappe.get_doc("Patient Insurance Policy", v.insurance_policy)
		self.assertEqual(
			(policy.docstatus, policy.policy_number, policy.ke_relation, policy.ke_principal_member_number),
			(1, "M-555", "Spouse", "M-554"),
		)
		# The next visit finds the same policy.
		visits.complete(v.name)
		v2 = self.insured(
			member_number="M-555", policy_expiry=add_days(today(), 200), visit_date=add_days(today(), 1)
		)
		v2.insert(ignore_permissions=True)
		self.assertEqual(v2.insurance_policy, policy.name)

	def test_expired_cover_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			self.insured(member_number="M-556", policy_expiry=add_days(today(), -1)).insert(
				ignore_permissions=True
			)

	def test_missing_member_number_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			self.insured().insert(ignore_permissions=True)
