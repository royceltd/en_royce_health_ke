# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Disease surveillance: notifiable disease cases from consultations, real-time
alerts, outbreak thresholds, staff-reported events and the IDSR weekly summary.
Each test uses its own diseases and codes, so the seeded list never interferes."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, add_to_date, getdate, today

from royce_health_ke import surveillance
from royce_health_ke.codes import set_coding
from royce_health_ke.moh.seed_idsr import rows as seed_rows


class TestSurveillance(IntegrationTestCase):
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
					"first_name": "Surv",
					"last_name": self.tag,
					"status": "Active",
				}
			)
			.insert(ignore_permissions=True)
			.name
		)
		self.officer = f"dso.{self.tag.lower()}@example.test"
		user = frappe.get_doc(
			{"doctype": "User", "email": self.officer, "first_name": "DSO", "send_welcome_email": 0}
		).insert(ignore_permissions=True)
		user.add_roles(surveillance.OFFICER_ROLE, "Physician")

	# helpers ------------------------------------------------------------------

	def disease(self, label, category=surveillance.IMMEDIATE, threshold=1, days=7, ihr=0):
		code = f"X{self.tag}{label[:3].upper()}"
		name = f"{label} {self.tag}"
		frappe.get_doc(
			{
				"doctype": "Notifiable Disease",
				"disease_name": name,
				"category": category,
				"ihr_notifiable": ihr,
				"alert_threshold": threshold,
				"threshold_days": days,
				"codes": [{"code_system": "ICD-10", "code_prefix": code}],
			}
		).insert(ignore_permissions=True)
		return name, code

	def diagnosis(self, code, system="ICD-10"):
		dx = frappe.get_doc(
			{"doctype": "Diagnosis", "diagnosis": f"Dx {code} {frappe.generate_hash(length=4)}"}
		)
		set_coding(dx, system, code, f"Test {code}")
		return dx.insert(ignore_permissions=True).name

	def patient(self, years=30):
		return (
			frappe.get_doc(
				{
					"doctype": "Patient",
					"first_name": "Surv",
					"last_name": f"Patient {frappe.generate_hash(length=6)}",
					"sex": "Female",
					"dob": add_to_date(today(), years=-years),
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

	def consult(self, patient, *diagnoses, on=None):
		e = frappe.get_doc(
			{
				"doctype": "Patient Encounter",
				"patient": patient,
				"practitioner": self.practitioner,
				"encounter_date": on or today(),
				"company": self.company,
				"appointment_type": frappe.db.get_value("Appointment Type", {}, "name"),
				"diagnosis": [{"diagnosis": d} for d in diagnoses],
			}
		).insert(ignore_permissions=True)
		e.submit()
		return e

	def cases(self, disease):
		return frappe.get_all(
			"Notifiable Disease Case",
			filters={"disease": disease},
			fields=["name", "patient", "event", "age_years"],
		)

	def alerts(self, doctype=None):
		filters = {"for_user": self.officer}
		if doctype:
			filters["document_type"] = doctype
		return frappe.get_all("Notification Log", filters=filters, pluck="subject")

	# tests --------------------------------------------------------------------

	def test_immediately_reportable_case_alerts_the_officer(self):
		disease, code = self.disease("Cholera", ihr=1)
		patient = self.patient(years=3)
		self.consult(patient, self.diagnosis(f"{code}.9"))  # prefix match
		cases = self.cases(disease)
		self.assertEqual(len(cases), 1)
		self.assertEqual((cases[0].patient, cases[0].age_years), (patient, 3))
		subjects = self.alerts("Notifiable Disease Case")
		self.assertEqual(len(subjects), 1)
		self.assertIn("24 hours", subjects[0])
		self.assertIn("IHR", subjects[0])
		self.assertNotIn(patient, subjects[0])  # the alert names no patient

	def test_follow_up_visit_is_not_a_new_case(self):
		disease, code = self.disease("Measles")
		patient, dx = self.patient(), self.diagnosis(code)
		self.consult(patient, dx, on=add_days(today(), -3))
		self.consult(patient, dx)
		self.assertEqual(len(self.cases(disease)), 1)

	def test_icd11_code_and_direct_diagnosis_link_match(self):
		disease, _code = self.disease("Anthrax")
		linked = frappe.get_doc(
			{"doctype": "Diagnosis", "diagnosis": f"Suspected anthrax {self.tag}"}
		).insert(ignore_permissions=True)
		doc = frappe.get_doc("Notifiable Disease", disease)
		doc.append("codes", {"code_system": "ICD-11", "code_prefix": f"1X{self.tag}"})
		doc.append("codes", {"diagnosis": linked.name})
		doc.save()
		self.consult(self.patient(), self.diagnosis(f"1X{self.tag}.0", system="ICD-11"))
		self.consult(self.patient(), linked.name)
		self.assertEqual(len(self.cases(disease)), 2)

	def test_other_diagnoses_record_nothing(self):
		disease, _code = self.disease("Plague")
		self.consult(self.patient(), self.diagnosis(f"Q{self.tag}"))
		self.assertEqual(self.cases(disease), [])
		self.assertEqual(self.alerts(), [])

	def test_weekly_disease_reaching_its_threshold_opens_one_outbreak_alert(self):
		disease, code = self.disease("Typhoid", category="Weekly Reportable", threshold=3, days=7)
		dx = self.diagnosis(code)
		self.consult(self.patient(), dx)
		self.consult(self.patient(), dx)
		self.assertEqual(self.alerts(), [])  # weekly disease, below threshold: no alert
		self.consult(self.patient(), dx)
		events = frappe.get_all(
			"Public Health Event", filters={"disease": disease}, fields=["name", "cases", "status"]
		)
		self.assertEqual(len(events), 1)
		self.assertEqual((events[0].cases, events[0].status), (3, "Open"))
		self.consult(self.patient(), dx)  # joins the open event, no second alert
		self.assertEqual(frappe.db.count("Public Health Event", {"disease": disease}), 1)
		self.assertEqual(frappe.db.get_value("Public Health Event", events[0].name, "cases"), 4)
		self.assertTrue(all(c.event == events[0].name for c in self.cases(disease)))
		self.assertEqual(len(self.alerts("Public Health Event")), 1)

	def test_staff_reported_rumour_alerts_the_officer(self):
		frappe.get_doc(
			{
				"doctype": "Public Health Event",
				"event_type": "Rumour",
				"company": self.company,
				"description": "Several pupils at a local school with vomiting and diarrhoea",
				"location": "Test Primary School",
			}
		).insert(ignore_permissions=True)
		self.assertEqual(len(self.alerts("Public Health Event")), 1)

	def test_weekly_summary_counts_cases_and_deaths_by_age_group(self):
		disease, code = self.disease("Dysentery")
		dx = self.diagnosis(code)
		self.consult(self.patient(years=2), dx)
		self.consult(self.patient(years=40), dx)
		self.consult(self.patient(years=50), dx)
		died = self.cases(disease)[0].name
		frappe.db.set_value("Notifiable Disease Case", died, "outcome", "Died")
		age = frappe.db.get_value("Notifiable Disease Case", died, "age_years")
		year, week = surveillance.epi_week(today())
		row = next(
			r for r in surveillance.weekly_summary(self.company, year, week) if r["disease"] == disease
		)
		self.assertEqual((row["cases_u5"], row["cases_o5"], row["cases"]), (1, 2, 3))
		self.assertEqual(row["deaths"], 1)
		self.assertEqual(row["deaths_u5" if age < 5 else "deaths_o5"], 1)

	def test_epi_weeks_run_monday_to_sunday(self):
		start, end = surveillance.week_dates(2026, 1)
		self.assertEqual((str(start), str(end)), ("2025-12-29", "2026-01-04"))
		self.assertEqual(surveillance.epi_week("2026-01-04"), (2026, 1))
		self.assertEqual(getdate(start).weekday(), 0)

	def test_weekly_digest_reaches_the_officer(self):
		self.disease("Rabies")
		surveillance.send_weekly_digest(today())
		self.assertTrue(any("IDSR week" in s for s in self.alerts()))

	def test_seed_list_is_well_formed(self):
		names = [r[0] for r in seed_rows()]
		self.assertEqual(len(names), len(set(names)))
		for _name, category, _ihr, _alert, _days, codes in seed_rows():
			self.assertIn(category, (surveillance.IMMEDIATE, "Weekly Reportable"))
			for system, _prefix in codes:
				self.assertIn(system, ("ICD-10", "ICD-11"))
		self.assertTrue(frappe.db.exists("Notifiable Disease", "Cholera"))
