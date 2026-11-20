# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""The patient screen, "a form and a table for every entry" (Bethesda,
20 Nov 2026): vitals, diagnosis, requests and notes from the tabs, and the
charts to their designs."""

import frappe
from frappe.utils import now_datetime

from royce_health_ke import charts, inpatient
from royce_health_ke.test_inpatient import InpatientCase


class TestWardForms(InpatientCase):
	def test_vitals_from_the_tab(self):
		ip, _bed = self.admitted()
		name = inpatient.record_vitals(
			ip, {"temperature": "38.9", "pulse": "112", "ke_spo2": "95", "vital_signs_note": "Febrile"}
		)
		vs = frappe.get_doc("Vital Signs", name)
		self.assertEqual((vs.docstatus, vs.inpatient_record, vs.temperature), (1, ip, "38.9"))
		self.assertFalse(vs.get("ke_patient_visit"))
		rows = inpatient.panel(ip, "Vitals")["rows"]
		self.assertEqual(rows[-1]["vital_signs_note"], "Febrile")
		with self.assertRaisesRegex(frappe.ValidationError, "at least one reading"):
			inpatient.record_vitals(ip, {"vital_signs_note": "nothing measured"})

	def test_diagnosis_on_the_ward_round(self):
		ip, _bed = self.admitted()
		diagnosis = frappe.db.get_value("Diagnosis", {}, "name")
		if not diagnosis:
			self.skipTest("needs a diagnosis")
		enc = inpatient.add_diagnosis(ip, diagnosis=diagnosis)
		self.assertEqual(frappe.db.get_value("Patient Encounter", enc, "inpatient_record"), ip)
		self.assertIn(diagnosis, [d["diagnosis"] for d in inpatient.panel(ip, "Diagnosis")["diagnoses"]])
		# the same open ward round takes the next one
		self.assertEqual(inpatient.add_diagnosis(ip, diagnosis=diagnosis), enc)

	def test_request_is_sent_from_the_tab(self):
		ip, _bed = self.admitted()
		category = frappe.db.get_value("Request Category", {"request_kind": "Lab Test"}, "name")
		inpatient.add_request(ip, category, self.template, urgency="Urgent", note="Before the next dose")
		requests = inpatient.panel(ip, "Requests")["requests"]
		self.assertIn(self.template, [r.template_dn for r in requests])
		sr = frappe.get_doc("Service Request", requests[0].name)
		self.assertEqual(sr.docstatus, 1)
		with self.assertRaisesRegex(frappe.ValidationError, "request type"):
			inpatient.add_request(ip, "No such type", self.template)

	def test_note_with_its_time(self):
		ip, _bed = self.admitted()
		when = now_datetime().replace(microsecond=0)
		name = inpatient.record_note(
			ip, "Nursing Note", "<p><b>Care Provided:</b> bed bath</p>", "Stable", str(when)
		)
		note = frappe.get_doc("Clinical Note", name)
		self.assertEqual((note.ke_patient_status, str(note.posting_date)[:16]), ("Stable", str(when)[:16]))


class TestChartDesigns(InpatientCase):
	def test_their_charts_and_columns(self):
		charts.seed()
		for name in ("Fluid Balance Chart", "Turning Chart"):
			self.assertTrue(frappe.db.exists(charts.TEMPLATE, name), name)
		columns = {c.label for c in frappe.get_doc(charts.TEMPLATE, "Blood Transfusion").columns}
		self.assertTrue({"Blood group", "Rhesus", "Rate", "Intervention drugs"} <= columns)
		self.assertIn("RBS", {c.label for c in frappe.get_doc(charts.TEMPLATE, "Diabetic Chart").columns})
		ip, _bed = self.admitted()
		entry = charts.record(
			ip, "Turning Chart", {"Position before": "Supine", "Position turned to": "Left Lateral"}
		)
		self.assertTrue(entry)
		fluid = charts.record(ip, "Fluid Balance Chart", {"Infused": 500, "Urine": 300})
		self.assertTrue(fluid)
