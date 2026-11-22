# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""v0.58, Bethesda's feedback of 21 Nov 2026: the consultation's request
table, ICD-11 codes on every ward diagnosis, the ward drug form and Give Dose,
and the partograph's draft defaults."""

import frappe
from frappe.utils import add_to_date, now_datetime

from royce_health_ke import consultation, diagnosis, inpatient, marley, partograph, prescribing
from royce_health_ke.codes import ICD11, set_coding, upsert_codes
from royce_health_ke.test_inpatient import InpatientCase


def _coded_diagnosis(name, code, title):
	if frappe.db.exists("Diagnosis", name):
		doc = frappe.get_doc("Diagnosis", name)
	else:
		doc = frappe.new_doc("Diagnosis")
		doc.diagnosis = name
	set_coding(doc, ICD11, code, title)
	doc.flags.ignore_permissions = True
	doc.save()
	return doc.name


def _uncoded_diagnosis(name):
	if frappe.db.exists("Diagnosis", name):
		frappe.db.delete("Codification Table", {"parenttype": "Diagnosis", "parent": name})
		return name
	doc = frappe.new_doc("Diagnosis")
	doc.diagnosis = name
	doc.flags.ignore_permissions = True
	doc.insert()
	return doc.name


class TestWardDiagnosisIsCoded(InpatientCase):
	def test_a_code_is_needed(self):
		ip, _bed = self.admitted()
		upsert_codes(ICD11, [("ZZ58", "Royce v058 condition", None, 0)])
		bare = _uncoded_diagnosis("ROYCE V058 UNCODED")
		with self.assertRaisesRegex(frappe.ValidationError, "no ICD-11 code yet"):
			inpatient.add_diagnosis(ip, diagnosis=bare)
		# with the code chosen it goes in, and the diagnosis keeps the code for next time
		inpatient.add_diagnosis(ip, diagnosis=bare, code_value=f"ZZ58-{ICD11}")
		self.assertEqual(diagnosis.icd11_of(bare)[1], "ZZ58")
		coded = _coded_diagnosis("Royce v058 coded", "ZZ57", "Royce v058 coded")
		enc = inpatient.add_diagnosis(ip, diagnosis=coded)
		codes = {r.ke_icd11_code for r in frappe.get_doc("Patient Encounter", enc).diagnosis}
		self.assertIn(f"ZZ57-{ICD11}", codes)

	def test_legacy_diagnosis_coded_by_title(self):
		upsert_codes(ICD11, [("ZZ56", "Royce v058 legacy", None, 0)])
		name = _uncoded_diagnosis("ROYCE V058 LEGACY")
		self.assertIn(name, diagnosis.code_uncoded_by_title())
		self.assertEqual(diagnosis.icd11_of(name)[1], "ZZ56")


class TestWardDrugForm(InpatientCase):
	def test_says_why_it_is_locked(self):
		ip, _bed = self.admitted()
		lists = prescribing.ward_lists(ip)
		self.assertEqual(lists["can_prescribe"], int(not lists["why_not"]))
		doc = frappe.get_doc("Inpatient Record", ip)
		doc.status = "Discharged"
		self.assertIn("not admitted", prescribing._why_not_prescribe(doc))

	def test_give_dose_checks(self):
		ip, _bed = self.admitted()
		self.assertIsInstance(inpatient.due_doses(ip), list)
		with self.assertRaisesRegex(frappe.ValidationError, "what happened"):
			inpatient.give_dose(ip, "HLC-MA-NONE", "Lost")
		with self.assertRaisesRegex(frappe.ValidationError, "not for this patient"):
			inpatient.give_dose(ip, "HLC-MA-NONE", "Given")

	def test_marley_dose_functions_in_the_adapter(self):
		self.assertTrue(callable(marley.get_due_medications))
		self.assertTrue(callable(marley.record_administration))


class TestRequestTable(InpatientCase):
	def test_request_status_of_a_consultation(self):
		ip, _bed = self.admitted()
		category = frappe.db.get_value("Request Category", {"request_kind": "Lab Test"}, "name")
		enc = inpatient.add_request(ip, category, self.template, urgency="Urgent")
		status = consultation.request_status(enc)
		self.assertTrue(status)
		row = next(iter(status.values()))
		self.assertTrue(row["status"])
		self.assertNotIn("-Request", row["status"])


class TestPartographDraft(InpatientCase):
	def test_no_mode_or_answers_nobody_gave(self):
		ip, _bed = self.admitted()
		start = add_to_date(now_datetime(), hours=-2).replace(microsecond=0)
		# a first entry with only labour readings (no pregnancy details) saves
		delivery = partograph.record(ip, {"observation_time": str(start), "cervical_dilatation_cm": 4})
		self.assertFalse(frappe.db.get_value("Delivery Record", delivery, "mode_of_delivery"))
		values = partograph.get(ip)["values"]
		for f in (*partograph.DELIVERY_CHECKS, "haemoglobin", "mode_of_delivery"):
			self.assertNotIn(f, values, f)

	def test_patch_clears_a_defaulted_mode(self):
		ip, _bed = self.admitted()
		delivery = partograph.record(ip, {"cervical_dilatation_cm": 4})
		frappe.db.set_value("Delivery Record", delivery, "mode_of_delivery", "Spontaneous vaginal delivery")
		partograph.clear_default_mode_of_delivery()
		self.assertFalse(frappe.db.get_value("Delivery Record", delivery, "mode_of_delivery"))
