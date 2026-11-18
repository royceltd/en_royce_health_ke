# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""v0.46 compliance pack: consent at registration with its history, patients'
data requests (export of the record, corrections) with reply dates, and the
data breach register with the 72-hour notice."""

import json

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, add_to_date, getdate, now_datetime, today

from royce_health_ke import compliance, dataprotection
from royce_health_ke.test_visits import make_patient


def _new_patient(**values):
	return frappe.get_doc(
		{
			"doctype": "Patient",
			"first_name": "Consent",
			"last_name": f"Test {frappe.generate_hash(length=6)}",
			"sex": "Female",
			"dob": "1990-01-01",
			**values,
		}
	)


class TestConsent(IntegrationTestCase):
	def setUp(self):
		frappe.flags.ke_test_consent = True
		frappe.db.set_single_value("Kenya Health Settings", "consent_at_registration", 1)

	def tearDown(self):
		frappe.flags.ke_test_consent = False

	def test_new_patient_needs_the_privacy_notice(self):
		with self.assertRaises(frappe.ValidationError):
			_new_patient().insert(ignore_permissions=True)

	def test_setting_off_lets_it_through(self):
		frappe.db.set_single_value("Kenya Health Settings", "consent_at_registration", 0)
		self.addCleanup(frappe.db.set_single_value, "Kenya Health Settings", "consent_at_registration", 1)
		self.assertTrue(_new_patient().insert(ignore_permissions=True).name)

	def test_consent_stamped_and_logged(self):
		p = _new_patient(
			ke_privacy_notice=1,
			ke_sms_consent=1,
			ke_consent_given_by="Mother Test",
			ke_consent_relation="Parent",
		).insert(ignore_permissions=True)
		self.assertTrue(p.ke_consent_at)
		self.assertEqual(p.ke_consent_recorded_by, frappe.session.user)
		logs = frappe.get_all(
			"Patient Consent Log", filters={"patient": p.name}, fields=["purpose", "decision", "given_by"]
		)
		self.assertEqual(
			{(r.purpose, r.decision) for r in logs}, {("Privacy notice", "Given"), ("SMS", "Given")}
		)
		self.assertEqual({r.given_by for r in logs}, {"Mother Test"})
		# SMS withdrawn: a new entry, the first one kept
		p.reload()
		p.ke_sms_consent = 0
		p.save(ignore_permissions=True)
		decisions = frappe.get_all(
			"Patient Consent Log",
			filters={"patient": p.name, "purpose": "SMS"},
			pluck="decision",
			order_by="creation",
		)
		self.assertEqual(decisions, ["Given", "Withdrawn"])
		# saving without a change adds nothing
		p.reload()
		p.save(ignore_permissions=True)
		self.assertEqual(frappe.db.count("Patient Consent Log", {"patient": p.name}), 3)

	def test_log_never_changed(self):
		p = _new_patient(ke_privacy_notice=1).insert(ignore_permissions=True)
		log = frappe.get_doc("Patient Consent Log", {"patient": p.name})
		log.decision = "Withdrawn"
		with self.assertRaises(frappe.ValidationError):
			log.save(ignore_permissions=True)
		with self.assertRaises(frappe.ValidationError):
			log.delete(ignore_permissions=True)


class TestDataSubjectRequests(IntegrationTestCase):
	def setUp(self):
		self.patient = make_patient()
		frappe.db.set_single_value("Kenya Health Settings", "dsr_access_days", 7)
		frappe.db.set_single_value("Kenya Health Settings", "dsr_correction_days", 14)

	def request(self, kind=dataprotection.ACCESS, **values):
		return frappe.get_doc(
			{
				"doctype": "Data Subject Request",
				"patient": self.patient,
				"request_type": kind,
				"details": "Wants a copy",
				**values,
			}
		).insert(ignore_permissions=True)

	def test_due_dates_from_settings(self):
		self.assertEqual(getdate(self.request().due_date), getdate(add_days(today(), 7)))
		self.assertEqual(
			getdate(self.request(dataprotection.CORRECTION).due_date), getdate(add_days(today(), 14))
		)

	def test_completing_needs_outcome_and_export(self):
		r = self.request()
		r.status = "Completed"
		with self.assertRaises(frappe.ValidationError):
			r.save(ignore_permissions=True)
		r.resolution = "Copy given"
		with self.assertRaises(frappe.ValidationError):
			r.save(ignore_permissions=True)  # not exported yet
		r.reload()
		r.status = "Refused"
		with self.assertRaises(frappe.ValidationError):
			r.save(ignore_permissions=True)  # no reason

	def test_export_attaches_the_record(self):
		r = self.request()
		out = dataprotection.export_record(r.name)
		self.assertTrue(out["json"])
		content = frappe.get_doc("File", {"file_url": out["json"]}).get_content()
		data = json.loads(content)
		self.assertEqual(data["patient"]["patient_number"], self.patient)
		self.assertIn("consultations", data)
		r.reload()
		self.assertEqual(r.status, "In Progress")
		self.assertTrue(r.export_file)
		self.assertTrue(
			frappe.db.exists("Patient Record Access", {"reference_name": r.name, "action": "Export"})
		)
		self.assertTrue(frappe.db.get_value("File", {"file_url": out["json"]}, "is_private"))
		r.resolution = "Copy handed to the patient"
		r.status = "Completed"
		r.save(ignore_permissions=True)
		self.assertTrue(r.completed_on)

	def test_overdue_shows_in_the_compliance_check(self):
		r = self.request(received_on=add_days(now_datetime(), -30))
		self.assertIn(r.name, dataprotection.overdue_requests())
		row = next(x for x in compliance.checks() if "answered on time" in x["safeguard"])
		self.assertEqual(row["status"], "Fail")
		frappe.db.rollback()


class TestBreachRegister(IntegrationTestCase):
	def breach(self, hours_ago=1, **values):
		return frappe.get_doc(
			{
				"doctype": "Data Breach",
				"discovered_at": add_to_date(now_datetime(), hours=-hours_ago),
				"cause": "Sent to the wrong person",
				"description": "Lab result emailed to the wrong patient",
				**values,
			}
		).insert(ignore_permissions=True)

	def test_72_hour_deadline(self):
		b = self.breach()
		self.assertEqual(
			frappe.utils.get_datetime(b.odpc_due),
			add_to_date(frappe.utils.get_datetime(b.discovered_at), hours=72),
		)
		self.assertNotIn(b.name, dataprotection.unnotified_breaches())
		self.assertIn(b.name, dataprotection.unnotified_breaches(within_hours=72))

	def test_late_breach_fails_the_check_until_notified(self):
		b = self.breach(hours_ago=80)
		self.assertIn(b.name, dataprotection.unnotified_breaches())
		b.odpc_notified_at = now_datetime()
		b.odpc_reference = "ODPC/TEST/1"
		b.save(ignore_permissions=True)
		self.assertNotIn(b.name, dataprotection.unnotified_breaches())

	def test_closing_needs_notice_and_lessons(self):
		b = self.breach()
		b.status = "Closed"
		with self.assertRaises(frappe.ValidationError):
			b.save(ignore_permissions=True)
		b.reload()
		b.status = "Closed"
		b.odpc_notified_at = now_datetime()
		with self.assertRaises(frappe.ValidationError):
			b.save(ignore_permissions=True)
		b.reload()
		b.update(
			{
				"status": "Closed",
				"odpc_notified_at": now_datetime(),
				"lessons": "Check the address before sending",
			}
		)
		b.save(ignore_permissions=True)
		self.assertTrue(b.closed_at)

	def test_not_notifiable_needs_a_reason(self):
		with self.assertRaises(frappe.ValidationError):
			self.breach(odpc_notification_required=0)
		b = self.breach(
			odpc_notification_required=0, not_notified_reason="Encrypted laptop, key safe", hours_ago=100
		)
		self.assertNotIn(b.name, dataprotection.unnotified_breaches())


class TestDailyAlert(IntegrationTestCase):
	def test_notify_runs(self):
		dataprotection.notify_overdue()
