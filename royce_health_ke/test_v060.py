# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""v0.60, Bethesda 23 Nov 2026: "search by name fills the code, start with
the code and it fills the name", for a diagnosis typed rather than picked."""

import frappe

from royce_health_ke import diagnosis, inpatient
from royce_health_ke.codes import ICD11, upsert_codes
from royce_health_ke.test_inpatient import InpatientCase


class TestTypedDiagnosis(InpatientCase):
	def setUp(self):
		super().setUp()
		upsert_codes(ICD11, [("ZZ60", "Royce v060 fever", None, 0)])

	def test_code_typed_in_the_name(self):
		r = diagnosis.resolve(diagnosis="zz60")
		self.assertEqual((r["code"], r["code_value"]), ("ZZ60", f"ZZ60-{ICD11}"))
		self.assertTrue(frappe.db.exists("Diagnosis", r["diagnosis"]))

	def test_name_in_any_case(self):
		r = diagnosis.resolve(diagnosis="ROYCE V060 FEVER")
		self.assertEqual(r["code"], "ZZ60")
		again = diagnosis.resolve(diagnosis=r["diagnosis"].lower())
		self.assertEqual(again["diagnosis"], r["diagnosis"])

	def test_nothing_matches_suggests_instead_of_failing(self):
		r = diagnosis.resolve(diagnosis="Royce v060")
		self.assertEqual(r["not_found"], "Royce v060")
		self.assertIn("Royce v060 fever", r["suggestions"])
		ip, _bed = self.admitted()
		with self.assertRaisesRegex(frappe.ValidationError, "Choose one from the list"):
			inpatient.add_diagnosis(ip, diagnosis="Royce v060")
		enc = inpatient.add_diagnosis(ip, diagnosis="ZZ60")
		codes = {d.ke_icd11_code for d in frappe.get_doc("Patient Encounter", enc).diagnosis}
		self.assertIn(f"ZZ60-{ICD11}", codes)
