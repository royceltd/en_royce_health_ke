# Copyright (c) 2026, Royce Technologies LTD and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from royce_health_ke.kenya_health.report.patients_by_residence import patients_by_residence
from royce_health_ke.patches.v0_22 import residences_from_patients


def patient(first, residence=None):
	return (
		frappe.get_doc(
			{
				"doctype": "Patient",
				"first_name": first,
				"last_name": "ResTest",
				"sex": "Female",
				"ke_residence": residence,
			}
		)
		.insert(ignore_permissions=True)
		.name
	)


class IntegrationTestResidence(IntegrationTestCase):
	def test_name_is_tidied(self):
		doc = frappe.get_doc({"doctype": "Residence", "residence_name": "  _Test   Kiamumbi "}).insert()
		self.assertEqual(doc.name, "_Test Kiamumbi")

	def test_typed_residences_become_the_list(self):
		a, b = patient("Achieng"), patient("Wanjiru")
		# as typed before v0.22, when the field was free text
		frappe.db.set_value("Patient", a, {"ke_residence": " _Test  Lanet ", "ke_county": "Nakuru"})
		frappe.db.set_value("Patient", b, {"ke_residence": "_test lanet", "ke_sub_county": "Nakuru East"})
		residences_from_patients.execute()
		place = frappe.get_doc("Residence", "_Test Lanet")
		self.assertEqual((place.county, place.sub_county), ("Nakuru", "Nakuru East"))
		self.assertEqual(frappe.db.get_value("Patient", a, "ke_residence"), "_Test Lanet")
		self.assertEqual(frappe.db.get_value("Patient", b, "ke_residence"), "_Test Lanet")
		residences_from_patients.execute()  # again: nothing new
		self.assertEqual(frappe.db.count("Residence", {"name": ["like", "_Test Lanet%"]}), 1)

	def test_patient_picks_a_residence_and_gets_its_county(self):
		frappe.get_doc(
			{
				"doctype": "Residence",
				"residence_name": "_Test Milimani",
				"residence_type": "Estate",
				"county": "Nakuru",
				"sub_county": "Nakuru West",
			}
		).insert()
		name = patient("Njeri", "_Test Milimani")
		self.assertEqual(
			frappe.db.get_value("Patient", name, ["ke_county", "ke_sub_county"]), ("Nakuru", "Nakuru West")
		)
		with self.assertRaises(frappe.LinkValidationError):
			patient("Akinyi", "_Test Nowhere")

	def test_report_counts_patients_per_place(self):
		frappe.get_doc(
			{"doctype": "Residence", "residence_name": "_Test Bahati", "residence_type": "Village"}
		).insert()
		patient("Chebet", "_Test Bahati")
		patient("Moraa", "_Test Bahati")
		_cols, rows, _msg, chart = patients_by_residence.execute(
			{"from_date": add_days(today(), -1), "to_date": today(), "residence_type": "Village"}
		)
		row = next(r for r in rows if r["residence"] == "_Test Bahati")
		self.assertEqual(row["new_patients"], 2)
		self.assertTrue(all(r["residence_type"] == "Village" for r in rows))
		self.assertIn("_Test Bahati", chart["data"]["labels"])
