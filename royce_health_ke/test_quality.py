# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Quality measures: calculation from recorded data, saved results, FHIR
MeasureReport and CSV export, and import of both. Each test uses its own
company-wide period of one day and its own measures where it needs counts."""

import json

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_to_date, today

from royce_health_ke import quality
from royce_health_ke.codes import set_coding


class TestQualityMeasures(IntegrationTestCase):
	def setUp(self):
		frappe.flags.in_test = True
		self.company = frappe.db.get_single_value(
			"Global Defaults", "default_company"
		) or frappe.db.get_value("Company", {}, "name")
		self.tag = frappe.generate_hash(length=6).upper()
		self.practitioner = (
			frappe.get_doc(
				{
					"doctype": "Healthcare Practitioner",
					"first_name": "QM",
					"last_name": self.tag,
					"status": "Active",
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

	def measure(self, **values):
		code = f"QM-T-{self.tag}-{frappe.generate_hash(length=3).upper()}"
		frappe.get_doc(
			{"doctype": "Quality Measure", "measure_code": code, "measure_name": f"Test {code}", **values}
		).insert(ignore_permissions=True)
		return code

	def patient(self, years=50):
		return (
			frappe.get_doc(
				{
					"doctype": "Patient",
					"first_name": "QM",
					"last_name": f"Patient {frappe.generate_hash(length=6)}",
					"sex": "Male",
					"dob": add_to_date(today(), years=-years),
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

	def consult(self, patient, code):
		dx = frappe.get_doc(
			{"doctype": "Diagnosis", "diagnosis": f"QM {code} {frappe.generate_hash(length=4)}"}
		)
		set_coding(dx, "ICD-10", code, f"Test {code}")
		dx.insert(ignore_permissions=True)
		e = frappe.get_doc(
			{
				"doctype": "Patient Encounter",
				"patient": patient,
				"practitioner": self.practitioner,
				"encounter_date": today(),
				"company": self.company,
				"appointment_type": frappe.db.get_value("Appointment Type", {}, "name"),
				"diagnosis": [{"diagnosis": dx.name}],
			}
		).insert(ignore_permissions=True)
		e.submit()

	def row(self, code):
		return next(r for r in quality.calculate(self.company, today(), today(), [code]))

	def test_vital_recorded_for_a_diagnosis(self):
		prefix = f"Y{self.tag}"
		code = self.measure(
			method="Vital Recorded at Consultation",
			diagnosis_prefixes=f"{prefix}",
			min_age_years=18,
			vital_sign="bp_systolic",
			target_percent=60,
		)
		recorded, missing, child = self.patient(), self.patient(), self.patient(years=10)
		for p in (recorded, missing, child):
			self.consult(p, f"{prefix}.0")
		frappe.get_doc(
			{"doctype": "Vital Signs", "patient": recorded, "signs_date": today(), "bp_systolic": "150"}
		).insert(ignore_permissions=True)
		r = self.row(code)
		self.assertEqual((r["numerator"], r["denominator"], r["rate"]), (1, 2, 50.0))  # the child is excluded
		self.assertEqual(r["met"], "No")

	def test_lab_result_for_diagnosis(self):
		prefix = f"W{self.tag}"
		code = self.measure(
			method="Lab Result for Diagnosis",
			diagnosis_prefixes=prefix,
			lab_result_names=f"glyco{self.tag.lower()}",
			look_back_days=30,
		)
		tested, untested = self.patient(), self.patient()
		lab = frappe.new_doc("Lab Test")
		lab.update({"patient": tested, "company": self.company, "result_date": today()})
		lab.append("normal_test_items", {"lab_test_name": f"Glyco{self.tag}", "result_value": "7.1"})
		lab.flags.ignore_mandatory = True
		lab.insert(ignore_permissions=True)
		for p in (tested, untested):
			self.consult(p, prefix)
		r = self.row(code)
		self.assertEqual((r["numerator"], r["denominator"]), (1, 2))

	def test_lower_is_better_target(self):
		code = self.measure(method="Entered or Imported", higher_is_better=0, target_percent=5)
		self.assertEqual(quality.score(code, 2, 100), (2.0, 5, "Yes"))
		self.assertEqual(quality.score(code, 8, 100), (8.0, 5, "No"))
		self.assertEqual(quality.score(code, 0, 0), (0, 5, ""))

	def test_save_export_and_import_round_trip(self):
		entered = self.measure(method="Entered or Imported", target_percent=80)
		self.assertIsNone(self.row(entered)["denominator"])  # nothing entered yet
		frappe.get_doc(
			{
				"doctype": "Quality Measure Result",
				"measure": entered,
				"company": self.company,
				"period_start": today(),
				"period_end": today(),
				"numerator": 45,
				"denominator": 50,
			}
		).insert(ignore_permissions=True)
		self.assertEqual(self.row(entered)["rate"], 90.0)

		rows = [r for r in quality.calculate(self.company, today(), today(), [entered])]
		bundle = quality.to_fhir(rows, self.company, today(), today())
		report = bundle["entry"][0]["resource"]
		self.assertEqual((bundle["resourceType"], report["resourceType"]), ("Bundle", "MeasureReport"))
		self.assertEqual(report["measure"], quality.MEASURE_URI + entered)
		self.assertEqual(report["group"][0]["measureScore"]["value"], 0.9)

		# FHIR import into another period: saved as Imported
		report["period"] = {"start": "2026-01-01", "end": "2026-01-31"}
		parsed = quality.parse_import(json.dumps(bundle))
		self.assertEqual(parsed, [(entered, "2026-01-01", "2026-01-31", 45, 50)])

		csv_text = quality.to_csv(rows, today(), today())
		self.assertTrue(csv_text.startswith(",".join(quality.CSV_COLUMNS)))
		parsed_csv = quality.parse_import(
			csv_text.replace(today(), "2026-02-01", 1).replace(today(), "2026-02-28", 1)
		)
		self.assertEqual(parsed_csv[0][:3], (entered, "2026-02-01", "2026-02-28"))

		file = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": f"qm-{self.tag}.json",
				"content": json.dumps(bundle),
				"is_private": 1,
			}
		).insert(ignore_permissions=True)
		result = quality.import_results(self.company, file.file_url)
		self.assertEqual(result["imported"], 1)
		saved = frappe.db.get_value(
			"Quality Measure Result",
			{"measure": entered, "period_start": "2026-01-01"},
			["source", "rate", "met_target"],
			as_dict=True,
		)
		self.assertEqual((saved.source, saved.rate, saved.met_target), ("Imported", 90.0, "Yes"))

	def test_calculated_results_are_saved_once_per_period(self):
		quality.save_results(self.company, today(), today())
		first = frappe.db.count("Quality Measure Result", {"company": self.company, "period_start": today()})
		quality.save_results(self.company, today(), today())
		self.assertEqual(
			frappe.db.count("Quality Measure Result", {"company": self.company, "period_start": today()}),
			first,
		)
		self.assertTrue(
			frappe.db.exists("Quality Measure Result", {"measure": "QM-U5-WEIGHT", "source": "Calculated"})
		)

	def test_every_seeded_measure_calculates(self):
		rows = {r["measure"]: r for r in quality.calculate(self.company, "2026-01-01", today())}
		for code in (
			"QM-HTN-BP",
			"QM-U5-WEIGHT",
			"QM-DM-HBA1C",
			"QM-MAL-TEST",
			"QM-LAB-TAT",
			"QM-IP-DEATHS",
			"QM-ANC4",
		):
			self.assertIsNotNone(rows[code]["denominator"], code)
