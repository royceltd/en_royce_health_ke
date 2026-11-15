# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Clinical decision support: rules on demographics, problem list, vital
signs, lab results, allergies and medicines; recalled and side-effect
medicine alerts; the clinician's response; the alert summary."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, add_to_date, today

from royce_health_ke import cds
from royce_health_ke.codes import set_coding
from royce_health_ke.kenya_health.report.clinical_alert_summary.clinical_alert_summary import (
	execute as summary,
)


class TestClinicalAlerts(IntegrationTestCase):
	def setUp(self):
		frappe.flags.in_test = True
		frappe.db.set_single_value("Kenya Health Settings", "clinical_alerts", 1)
		self.company = frappe.db.get_single_value(
			"Global Defaults", "default_company"
		) or frappe.db.get_value("Company", {}, "name")
		self.tag = frappe.generate_hash(length=6).upper()
		self.practitioner = (
			frappe.get_doc(
				{
					"doctype": "Healthcare Practitioner",
					"first_name": "CDS",
					"last_name": self.tag,
					"status": "Active",
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

	# helpers ------------------------------------------------------------------

	def patient(self, years=40, sex="Female", allergies=None):
		return (
			frappe.get_doc(
				{
					"doctype": "Patient",
					"first_name": "CDS",
					"last_name": f"Patient {frappe.generate_hash(length=6)}",
					"sex": sex,
					"dob": add_to_date(today(), years=-years),
					"allergies": allergies,
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

	def vitals(self, patient, **values):
		frappe.get_doc(
			{"doctype": "Vital Signs", "patient": patient, "signs_date": today(), **values}
		).insert(ignore_permissions=True)

	def diagnosis(self, code):
		dx = frappe.get_doc(
			{"doctype": "Diagnosis", "diagnosis": f"CDS {code} {frappe.generate_hash(length=4)}"}
		)
		set_coding(dx, "ICD-10", code, f"Test {code}")
		return dx.insert(ignore_permissions=True).name

	def consult(self, patient, diagnoses=(), drugs=(), on=None, submit=False):
		e = frappe.get_doc(
			{
				"doctype": "Patient Encounter",
				"patient": patient,
				"practitioner": self.practitioner,
				"encounter_date": on or today(),
				"company": self.company,
				"appointment_type": frappe.db.get_value("Appointment Type", {}, "name"),
				"diagnosis": [{"diagnosis": d} for d in diagnoses],
				"drug_prescription": list(drugs),
			}
		).insert(ignore_permissions=True)
		if submit:
			e.submit()
		return e

	def keys(self, encounter):
		return set(frappe.get_all("Clinical Alert Log", filters={"encounter": encounter.name}, pluck="key"))

	def rule(self, conditions, **values):
		name = f"Test rule {self.tag} {frappe.generate_hash(length=4)}"
		frappe.get_doc(
			{
				"doctype": "Clinical Alert Rule",
				"rule_name": name,
				"severity": "Warning",
				"recommendation": "Do the right thing",
				"evidence_source": "Test guideline",
				"conditions": conditions,
				**values,
			}
		).insert(ignore_permissions=True)
		return f"rule:{name}"

	def medication(self):
		med = frappe.db.get_value("Medication Linked Item", {"item": "DRG-PCM500"}, "parent")
		if not med:
			self.skipTest("needs the demo's paracetamol (load the demo)")
		return {
			"medication": med,
			"drug_code": "DRG-PCM500",
			"dosage": frappe.db.get_value("Prescription Dosage", {}, "name"),
			"period": frappe.db.get_value("Prescription Duration", {}, "name"),
			"dosage_form": frappe.db.get_value("Dosage Form", {}, "name"),
		}

	# seeded, guideline rules ----------------------------------------------------

	def test_fever_in_a_child_under_five_but_not_an_adult(self):
		child, adult = self.patient(years=2), self.patient(years=30)
		self.vitals(child, temperature="38.4")
		self.vitals(adult, temperature="38.4")
		self.assertIn("rule:Fever in a child under 5", self.keys(self.consult(child)))
		self.assertNotIn("rule:Fever in a child under 5", self.keys(self.consult(adult)))

	def test_low_oxygen_is_critical(self):
		p = self.patient()
		self.vitals(p, ke_spo2="86")
		alerts = frappe.get_all(
			"Clinical Alert Log", filters={"encounter": self.consult(p).name}, fields=["key", "severity"]
		)
		self.assertIn({"key": "rule:Low oxygen saturation", "severity": "Critical"}, alerts)

	# rule conditions -------------------------------------------------------------

	def test_problem_list_from_earlier_consultations(self):
		code = f"Z{self.tag}"
		key = self.rule([{"condition": "Diagnosis", "code_prefix": f"X0, {code}", "look_back_days": 365}])
		p = self.patient()
		self.consult(p, diagnoses=[self.diagnosis(f"{code}.1")], on=add_days(today(), -60), submit=True)
		self.assertIn(key, self.keys(self.consult(p)))  # today's visit: no diagnosis, history matches
		self.assertNotIn(key, self.keys(self.consult(self.patient())))

	def test_lab_result_and_demographics(self):
		key = self.rule(
			[
				{
					"condition": "Lab Result",
					"lab_result_name": f"Marker {self.tag}",
					"operator": "<",
					"value": 5,
				}
			],
			sex="Male",
			min_age_years=18,
		)
		man, woman = self.patient(sex="Male"), self.patient(sex="Female")
		for p in (man, woman):
			lab = frappe.new_doc("Lab Test")
			lab.update({"patient": p, "company": self.company, "result_date": today()})
			lab.append("normal_test_items", {"lab_test_name": f"Marker {self.tag}", "result_value": "3.2"})
			lab.flags.ignore_mandatory = True
			lab.insert(ignore_permissions=True)
		self.assertIn(key, self.keys(self.consult(man)))
		self.assertNotIn(key, self.keys(self.consult(woman)))  # sex doesn't match

	def test_allergy_and_medication_together(self):
		drug = self.medication()
		key = self.rule(
			[
				{"condition": "Allergy", "text": f"sulfa, allergen{self.tag.lower()}"},
				{"condition": "Medication", "text": "paracetamol, pcm500"},
			]
		)
		allergic = self.patient(allergies=f"Allergen{self.tag} - rash")
		self.assertIn(key, self.keys(self.consult(allergic, drugs=[drug])))
		self.assertNotIn(key, self.keys(self.consult(allergic)))  # no drug prescribed
		self.assertNotIn(key, self.keys(self.consult(self.patient(), drugs=[drug])))  # no allergy

	def test_recalled_medicine_and_side_effects(self):
		drug = self.medication()
		frappe.db.set_value(
			"Medication",
			drug["medication"],
			{"ke_recalled": 1, "ke_recall_note": "PPB recall batch X1", "ke_side_effects": "Nausea"},
		)
		alerts = frappe.get_all(
			"Clinical Alert Log",
			filters={"encounter": self.consult(self.patient(), drugs=[drug]).name},
			fields=["kind", "severity", "message"],
		)
		kinds = {a.kind: a for a in alerts}
		self.assertEqual(kinds["Recalled Medication"].severity, "Critical")
		self.assertIn("PPB recall batch X1", kinds["Recalled Medication"].message)
		self.assertIn("Nausea", kinds["Side Effects"].message)

	# logging, response, report -----------------------------------------------------

	def test_alert_logged_once_and_answered(self):
		p = self.patient()
		self.vitals(p, ke_spo2="85")
		e = self.consult(p)
		e.save(ignore_permissions=True)  # saved again: no duplicate
		pending = cds.pending_alerts(e.name)
		low = [a for a in pending if "Low oxygen" in a.message]
		self.assertEqual(len(low), 1)
		with self.assertRaises(frappe.ValidationError):
			cds.respond(low[0].name, "Overridden")  # a reason is required
		cds.respond(low[0].name, "Overridden", "Pulse oximeter probe on a cold finger; repeat 97%")
		self.assertNotIn(low[0].name, [a.name for a in cds.pending_alerts(e.name)])
		_cols, rows = summary(
			{"from_date": today(), "to_date": today(), "group_by": "Alert", "company": self.company}
		)
		row = next(r for r in rows if r["key"] == "Low oxygen saturation")
		self.assertGreaterEqual(row["overridden"], 1)

	def test_switched_off(self):
		frappe.db.set_single_value("Kenya Health Settings", "clinical_alerts", 0)
		p = self.patient()
		self.vitals(p, ke_spo2="80")
		self.assertEqual(self.keys(self.consult(p)), set())

	def test_rule_with_nothing_to_check_never_fires(self):
		key = self.rule([])
		self.assertNotIn(key, self.keys(self.consult(self.patient())))
