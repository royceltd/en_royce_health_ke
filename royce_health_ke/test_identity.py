# Copyright (c) 2026, Royce Technologies LTD and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, getdate

from royce_health_ke.identity import REMIND_AT, normalise_phone, validate_id_number


class IntegrationTestIdentity(IntegrationTestCase):
	def test_kenyan_phone_numbers_are_normalised(self):
		for typed in ("0712 000 001", "254712000001", "+254-712-000-001", "712000001", "(0712) 000-001"):
			self.assertEqual(normalise_phone(typed), "+254712000001", typed)
		self.assertEqual(normalise_phone("0110 123 456"), "+254110123456")

	def test_foreign_and_empty_numbers_are_left_alone(self):
		self.assertEqual(normalise_phone("+44 20 7946 0958"), "+44 20 7946 0958")
		self.assertIsNone(normalise_phone(None))

	def test_national_id_must_be_digits(self):
		self.assertEqual(validate_id_number("National ID", " 2938 4756 "), "29384756")
		for bad in ("A1234567", "12345", "1234567890"):
			with self.assertRaises(frappe.ValidationError):
				validate_id_number("National ID", bad)

	def test_other_documents_are_cleaned_not_policed(self):
		self.assertEqual(validate_id_number("Passport", "ak 123456"), "AK123456")
		self.assertIsNone(validate_id_number("None", "whatever"))
		self.assertIsNone(validate_id_number(None, ""))
		with self.assertRaises(frappe.ValidationError):
			validate_id_number("Birth Certificate", "  ")


class IntegrationTestLicenceReminders(IntegrationTestCase):
	def test_reminder_days(self):
		from royce_health_ke.identity import licences_needing_attention

		name = (
			frappe.get_doc(
				{
					"doctype": "Healthcare Practitioner",
					"first_name": "Test",
					"last_name": "Licence",
					"status": "Active",
					"ke_licence_number": "T-1",
					"ke_licence_expiry": "2030-01-31",
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

		def due(on_date):
			return name in [r.name for r in licences_needing_attention(on_date)]

		expiry = getdate("2030-01-31")
		for days in REMIND_AT:
			self.assertTrue(due(add_days(expiry, -days)), days)
		self.assertFalse(due(add_days(expiry, -10)))
		self.assertTrue(due(expiry))  # expires today
		self.assertTrue(due(add_days(expiry, 7)))  # weekly once expired
		self.assertFalse(due(add_days(expiry, 3)))
