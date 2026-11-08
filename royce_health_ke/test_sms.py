# Copyright (c) 2026, Royce Technologies LTD and Contributors
# See license.txt

import unittest
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_to_date, getdate, today

from royce_health_ke import sms


def _talk():
	return "royce_talk" in frappe.get_installed_apps()


def patient(first, sex="Female", age=30, consent=1, mobile="+254712000111"):
	return (
		frappe.get_doc(
			{
				"doctype": "Patient",
				"first_name": first,
				"last_name": f"SmsTest {frappe.generate_hash(length=6)}",
				"sex": sex,
				"dob": add_to_date(today(), years=-age, days=-10),
				"mobile": mobile,
				"ke_sms_consent": consent,
			}
		)
		.insert(ignore_permissions=True)
		.name
	)


@unittest.skipUnless(_talk(), "royce_talk not installed on this site")
class IntegrationTestPatientSMS(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		s = frappe.get_single("Bulk SMS Settings")
		s.enabled = 1
		s.api_key = "test-key"
		s.default_sender_id = s.default_sender_id or "TEST"
		s.api_base_url = s.api_base_url or "https://example.invalid"
		s.flags.ignore_validate = True
		s.save(ignore_permissions=True)

	def campaign(self, **filters):
		return frappe._dict(filters)

	def names(self, **filters):
		return {r.name for r in sms.campaign_recipients(self.campaign(**filters))}

	def test_campaign_needs_consent_and_mobile(self):
		yes = patient("Consent")
		no_consent = patient("NoConsent", consent=0)
		no_mobile = patient("NoMobile", mobile=None)
		got = self.names()
		self.assertIn(yes, got)
		self.assertNotIn(no_consent, got)
		self.assertNotIn(no_mobile, got)

	def test_campaign_filters_sex_and_age(self):
		woman_30 = patient("Woman30", "Female", 30)
		man_30 = patient("Man30", "Male", 30)
		woman_60 = patient("Woman60", "Female", 60)
		got = self.names(sex="Female", age_from=18, age_to=49)
		self.assertIn(woman_30, got)
		self.assertNotIn(man_30, got)
		self.assertNotIn(woman_60, got)
		# Age To is inclusive: someone who is 49 and a half is still 49.
		self.assertIn(patient("Woman49", "Female", 49), self.names(age_to=49))

	def test_campaign_pregnant_mothers_only(self):
		mother = patient("Mother")
		other = patient("Other")
		company = frappe.db.get_value("Company", {}, "name")
		frappe.get_doc(
			{
				"doctype": "Pregnancy Record",
				"patient": mother,
				"company": company,
				"lmp": add_to_date(today(), days=-90),
			}
		).insert(ignore_permissions=True)
		got = self.names(active_pregnancy=1)
		self.assertIn(mother, got)
		self.assertNotIn(other, got)

	def test_campaign_visit_dates(self):
		visited = patient("Visited")
		not_visited = patient("NotVisited")
		self._appointment(visited, add_to_date(today(), days=-3))
		got = self.names(visited_from=add_to_date(today(), days=-7), visited_to=today())
		self.assertIn(visited, got)
		self.assertNotIn(not_visited, got)

	def test_send_to_patient_logs_against_patient(self):
		p = patient("Direct")
		with patch("royce_talk.bulk_sms.utils.send_single_sms", return_value={"status": "Sent"}) as send:
			sms.send_to_patient(p, "  Hello  ")
		kwargs = send.call_args.kwargs
		self.assertEqual(kwargs["text_message"], "Hello")
		self.assertEqual((kwargs["reference_doctype"], kwargs["reference_name"]), ("Patient", p))

	def test_send_to_patient_without_mobile_is_refused(self):
		p = patient("NoPhone", mobile=None)
		with self.assertRaises(frappe.ValidationError):
			sms.send_to_patient(p, "Hello")

	def test_reminder_goes_once_with_consent_in_daytime(self):
		settings = frappe.get_single("Kenya Health Settings")
		settings.sms_appointment_reminders = 1
		settings.save(ignore_permissions=True)
		frappe.clear_document_cache("Kenya Health Settings")

		now = getdate(today())
		now = frappe.utils.get_datetime(f"{now} 09:00:00")
		tomorrow = add_to_date(now, hours=20)
		yes = self._appointment(patient("Remind"), tomorrow.date(), tomorrow.time())
		no = self._appointment(patient("NoRemind", consent=0), tomorrow.date(), tomorrow.time())

		with patch("royce_talk.bulk_sms.utils.queue_sms") as queue:
			sms.send_appointment_reminders(now)
			sms.send_appointment_reminders(now)  # second run: already reminded
		sent = [c.kwargs["reference_name"] for c in queue.call_args_list]
		self.assertEqual(sent.count(yes), 1)
		self.assertNotIn(no, sent)
		self.assertEqual(frappe.db.get_value("Patient Appointment", no, "reminded"), 1)

		with patch("royce_talk.bulk_sms.utils.queue_sms") as queue:
			sms.send_appointment_reminders(frappe.utils.get_datetime(f"{now.date()} 22:00:00"))
		queue.assert_not_called()

	def test_lab_message_has_no_results(self):
		settings = frappe.get_single("Kenya Health Settings")
		settings.sms_lab_results = 1
		settings.save(ignore_permissions=True)
		frappe.clear_document_cache("Kenya Health Settings")
		p = patient("Lab")
		doc = frappe._dict(patient=p, company=None, service_unit=None, name="LT-TEST")
		with patch("royce_talk.bulk_sms.utils.queue_sms") as queue:
			sms.lab_test_submitted(doc)
		message = queue.call_args.kwargs["text_message"]
		self.assertIn("Lab", message)  # first name
		self.assertIn("ready", message)
		self.assertNotIn("{{", message)

	def test_failed_campaign_send_is_marked_failed(self):
		patient("Campaign")
		doc = frappe.get_doc(
			{"doctype": "Patient SMS Campaign", "title": "Fail test", "message": "Hello"}
		).insert(ignore_permissions=True)
		with patch("royce_talk.bulk_sms.bulk_send.send_bulk", side_effect=Exception("provider down")):
			with patch("frappe.db.rollback"):  # keep the test's own transaction
				sms.send_campaign(doc.name)
		status, error = frappe.db.get_value("Patient SMS Campaign", doc.name, ["status", "error"])
		self.assertEqual(status, "Failed")
		self.assertIn("Bulk SMS Settings", error)

	def _appointment(self, patient_name, date, time="10:00:00"):
		doc = frappe.get_doc(
			{
				"doctype": "Patient Appointment",
				"name": f"SMS-TEST-{frappe.generate_hash(length=8)}",
				"patient": patient_name,
				"appointment_date": getdate(date),
				"appointment_time": str(time),
				"appointment_datetime": f"{getdate(date)} {time}",
				"status": "Scheduled",
				"reminded": 0,
			}
		)
		doc.db_insert()  # selection logic only; skip Marley's booking rules
		return doc.name
