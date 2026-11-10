# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Registration details, vitals flags and masked patient details."""

from contextlib import contextmanager

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_to_date, today

from royce_health_ke import vitals
from royce_health_ke.identity import missing_registration_details


@contextmanager
def checks_on():
	"""Tests normally skip the registration check; turn it on for one block."""
	in_test = frappe.flags.in_test
	frappe.flags.in_test = False
	try:
		yield
	finally:
		frappe.flags.in_test = in_test


def patient_doc(**values):
	base = {"doctype": "Patient", "first_name": "Reg", "last_name": f"Test {frappe.generate_hash(length=6)}"}
	return frappe.get_doc({**base, **values})


ADULT = {
	"sex": "Female",
	"dob": add_to_date(today(), years=-30),
	"ke_id_type": "Passport",
	"ke_id_number": "AK123456",
	"mobile": "+254712000555",
	"ke_nationality": "Uganda",
	"ke_residence": "Lanet",
}


class TestRegistration(IntegrationTestCase):
	def test_adult_needs_every_detail(self):
		missing = missing_registration_details(patient_doc(sex="Male"))
		self.assertEqual(len(missing), 5)  # DOB, ID, mobile, nationality, residence
		self.assertEqual(missing_registration_details(patient_doc(**ADULT)), [])

	def test_adult_must_have_a_real_id(self):
		doc = patient_doc(**{**ADULT, "ke_id_type": "None", "ke_id_number": None})
		self.assertEqual(len(missing_registration_details(doc)), 1)

	def test_child_may_have_no_id_and_use_next_of_kin_phone(self):
		child = {
			**ADULT,
			"dob": add_to_date(today(), years=-4),
			"ke_id_type": "None",
			"ke_id_number": None,
			"mobile": None,
			"ke_nok_phone": "+254712000556",
		}
		self.assertEqual(missing_registration_details(patient_doc(**child)), [])

	def test_kenyans_need_a_county(self):
		doc = patient_doc(**{**ADULT, "ke_nationality": "Kenya"})
		self.assertEqual(missing_registration_details(doc), ["County of Residence"])
		doc.ke_county = "Nakuru"
		self.assertEqual(missing_registration_details(doc), [])

	def test_new_patient_refused_until_registered(self):
		with checks_on():
			with self.assertRaises(frappe.ValidationError):
				patient_doc(sex="Male").insert(ignore_permissions=True)
			name = patient_doc(**ADULT).insert(ignore_permissions=True).name
		self.assertTrue(frappe.db.exists("Patient", name))

	def test_unidentified_emergency_patient_is_exempt(self):
		with checks_on():
			doc = patient_doc(sex="Other", naming_series="ER-.YYYY.-")
			doc.insert(ignore_permissions=True)
		self.assertTrue(doc.name)

	def test_setting_off_skips_the_check(self):
		frappe.db.set_single_value("Kenya Health Settings", "require_registration_details", 0)
		with checks_on():
			doc = patient_doc(sex="Male").insert(ignore_permissions=True)
		self.assertTrue(doc.name)


class TestVitals(IntegrationTestCase):
	def test_adult_ranges(self):
		flags = dict(
			vitals.abnormal_readings(
				{
					"temperature": "38.6",
					"pulse": "88",
					"ke_spo2": 91,
					"bp_systolic": "150",
					"bp_diastolic": "85",
				},
				age=40,
			)
		)
		self.assertEqual(set(flags), {"temperature", "ke_spo2", "bp_systolic"})
		self.assertEqual(flags["temperature"], "Temperature 38.6 °C (high)")
		self.assertIn("(low)", flags["ke_spo2"])

	def test_child_ranges(self):
		# 130/min is normal at 2 years, fast for an adult; BP isn't flagged under 13.
		self.assertEqual(vitals.abnormal_readings({"pulse": "130", "bp_systolic": "85"}, age=2), [])
		self.assertEqual([f for f, _t in vitals.abnormal_readings({"pulse": "130"}, age=30)], ["pulse"])
		self.assertEqual([f for f, _t in vitals.abnormal_readings({"respiratory_rate": "50"}, age=0)], [])

	def test_bmi_only_for_adults_and_text_is_ignored(self):
		self.assertEqual([f for f, _t in vitals.abnormal_readings({"bmi": 31}, age=40)], ["bmi"])
		self.assertEqual(vitals.abnormal_readings({"bmi": 31}, age=12), [])
		self.assertEqual(vitals.abnormal_readings({"temperature": "warm"}, age=40), [])

	def test_saved_vital_signs_are_flagged(self):
		patient = patient_doc(**ADULT).insert(ignore_permissions=True).name
		doc = frappe.get_doc(
			{
				"doctype": "Vital Signs",
				"patient": patient,
				"signs_date": today(),
				"signs_time": "08:00:00",
				"temperature": "39.1",
				"pulse": "120",
				"ke_spo2": 97,
			}
		).insert(ignore_permissions=True)
		self.assertEqual(doc.ke_vitals_status, "Abnormal")
		self.assertEqual(doc.ke_abnormal_fields, "temperature,pulse")
		doc.temperature, doc.pulse = "36.8", "80"
		doc.save()
		self.assertEqual(doc.ke_vitals_status, "Normal")
		self.assertFalse(doc.ke_vitals_flags)


class TestMasking(IntegrationTestCase):
	def user(self, role):
		email = f"mask-{frappe.scrub(role)}@example.com"
		if not frappe.db.exists("User", email):
			frappe.get_doc(
				{"doctype": "User", "email": email, "first_name": role, "send_welcome_email": 0}
			).insert(ignore_permissions=True)
		user = frappe.get_doc("User", email)
		user.add_roles(role)
		return email

	def test_clinical_staff_see_masked_details_reception_sees_them(self):
		patient = patient_doc(**ADULT).insert(ignore_permissions=True).name
		nurse, reception = self.user("Nursing User"), self.user("Receptionist")
		try:
			frappe.set_user(nurse)
			row = frappe.get_list("Patient", filters={"name": patient}, fields=["mobile", "ke_id_number"])[0]
			self.assertEqual(row.mobile, "+25XXXXXX")
			self.assertEqual(row.ke_id_number, "XXXXXXXX")
			# Server code (SMS, prints) still reads the real number.
			self.assertEqual(frappe.db.get_value("Patient", patient, "mobile"), "+254712000555")
			frappe.set_user(reception)
			row = frappe.get_list("Patient", filters={"name": patient}, fields=["mobile"])[0]
			self.assertEqual(row.mobile, "+254712000555")
		finally:
			frappe.set_user("Administrator")
