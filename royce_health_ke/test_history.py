# Copyright (c) 2026, Royce Technologies LTD and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import today

from royce_health_ke.test_visits import make_patient


class IntegrationTestHistory(IntegrationTestCase):
	def setUp(self):
		self.company = frappe.db.get_value("Company", {}, "name")
		self.patient = make_patient()
		frappe.db.set_value(
			"Patient",
			self.patient,
			{"allergies": "Penicillin", "medical_history": "Hypertension since 2019"},
		)
		self.practitioner = (
			frappe.get_doc(
				{
					"doctype": "Healthcare Practitioner",
					"first_name": "Hx",
					"last_name": "Doctor",
					"status": "Active",
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

	def consultation(self, **values):
		return frappe.get_doc(
			{
				"doctype": "Patient Encounter",
				"patient": self.patient,
				"practitioner": self.practitioner,
				"encounter_date": today(),
				"company": self.company,
				"appointment_type": frappe.db.get_value("Appointment Type", {}, "name"),
				**values,
			}
		).insert(ignore_permissions=True)

	def test_history_shows_in_the_consultation(self):
		c = self.consultation(ke_chief_complaint="Headache for 2 days")
		self.assertEqual((c.ke_hx_allergies, c.ke_hx_medical), ("Penicillin", "Hypertension since 2019"))
		self.assertEqual(c.ke_chief_complaint, "Headache for 2 days")
		# nothing changed: no note on the patient
		self.assertFalse(
			frappe.db.exists("Comment", {"reference_doctype": "Patient", "reference_name": self.patient})
		)

	def test_changes_are_saved_to_the_patient(self):
		c = self.consultation()
		c.ke_hx_allergies = "Penicillin, sulfa drugs"
		c.ke_hx_family = "Mother diabetic"
		c.save(ignore_permissions=True)
		p = frappe.db.get_value(
			"Patient", self.patient, ["allergies", "ke_family_history", "medical_history"], as_dict=True
		)
		self.assertEqual(
			(p.allergies, p.ke_family_history, p.medical_history),
			("Penicillin, sulfa drugs", "Mother diabetic", "Hypertension since 2019"),
		)
		note = frappe.db.get_value(
			"Comment", {"reference_doctype": "Patient", "reference_name": self.patient}, "content"
		)
		self.assertIn(c.name, note)
		self.assertIn("Allergies", note)
		self.assertIn("Family History", note)
		# the next consultation starts from the updated record
		self.assertEqual(self.consultation().ke_hx_family, "Mother diabetic")
