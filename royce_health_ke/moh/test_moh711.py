# Copyright (c) 2026, Royce Technologies LTD and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase

from royce_health_ke.moh.moh711 import NOT_CAPTURED, NOT_CAPTURED_SECTIONS, age_band, compute

# a month no real or demo data falls in
YEAR, MONTH = 2020, 3


def patient(first_name, sex, dob):
	return (
		frappe.get_doc(
			{
				"doctype": "Patient",
				"first_name": first_name,
				"last_name": "Moh711Test",
				"sex": sex,
				"dob": dob,
			}
		)
		.insert(ignore_permissions=True)
		.name
	)


def fp_visit(patient_name, method, **kwargs):
	doc = frappe.get_doc(
		{
			"doctype": "Family Planning Visit",
			"patient": patient_name,
			"company": frappe.db.get_value("Company", {}, "name"),
			"visit_date": "2020-03-10",
			"method": method,
			**kwargs,
		}
	).insert(ignore_permissions=True)
	doc.submit()
	return doc


def rows_by_indicator(rows):
	return {r["indicator"]: r for r in rows if not r.get("is_section")}


class IntegrationTestMOH711(IntegrationTestCase):
	def setUp(self):
		self.company = frappe.db.get_value("Company", {}, "name")
		if not self.company:
			self.skipTest("no company")

	def test_age_bands(self):
		self.assertIsNone(age_band(None))
		self.assertIsNone(age_band(9))
		self.assertEqual(age_band(10), "10-14")
		self.assertEqual(age_band(14), "10-14")
		self.assertEqual(age_band(15), "15-19")
		self.assertEqual(age_band(24), "20-24")
		self.assertEqual(age_band(25), "25+")

	def test_family_planning_visit_rules(self):
		woman = patient("Achieng", "Female", "1998-05-01")
		man = patient("Otieno", "Male", "1990-05-01")
		with self.assertRaises(frappe.ValidationError):
			fp_visit(woman, "Implant (1 rod)")  # insertion / removal not said
		with self.assertRaises(frappe.ValidationError):
			fp_visit(man, "DMPA-IM")
		with self.assertRaises(frappe.ValidationError):
			fp_visit(woman, "Vasectomy")
		first = fp_visit(woman, "DMPA-IM", procedure="Insertion")
		self.assertEqual(first.visit_type, "New")
		self.assertIsNone(first.procedure)  # only for implants and IUCDs
		self.assertEqual(fp_visit(woman, "DMPA-IM", visit_date="2020-03-20").visit_type, "Revisit")
		self.assertEqual(fp_visit(man, "Male condoms").visit_type, "New")

	def test_family_planning_section(self):
		woman = patient("Wanjiru", "Female", "2004-01-01")
		fp_visit(woman, "Combined oral contraceptive pills", first_ever_user=1)
		fp_visit(woman, "Combined oral contraceptive pills", visit_date="2020-03-25")
		fp_visit(woman, "Hormonal IUCD", procedure="Insertion", timing="Post abortion")
		fp_visit(woman, "Implant (2 rods)", procedure="Removal", timing="Post abortion")
		rows = rows_by_indicator(compute(self.company, YEAR, MONTH))
		self.assertEqual(rows["First ever users of contraceptives"]["value"], 1)
		self.assertEqual(rows["Combined Oral Contraceptive pills (New)"]["value"], 1)
		self.assertEqual(rows["Combined Oral Contraceptive pills (Revisit)"]["value"], 1)
		self.assertEqual(rows["Hormonal IUCD (1st time insertion)"]["value"], 1)
		self.assertEqual(rows["Implant removal"]["value"], 1)
		# a removal isn't a method received
		self.assertEqual(rows["Receiving post abortion FP method"]["value"], 1)

	def test_anc_first_visit_by_age(self):
		mother = patient("Chebet", "Female", "2003-01-15")  # 17 in March 2020
		pregnancy = frappe.get_doc(
			{
				"doctype": "Pregnancy Record",
				"patient": mother,
				"company": self.company,
				"booking_date": "2020-03-05",
				"lmp": "2019-12-20",
				"haemoglobin": 9.8,
				"syphilis": "Reactive",
			}
		).insert(ignore_permissions=True)
		visit = frappe.get_doc(
			{
				"doctype": "ANC Visit",
				"pregnancy_record": pregnancy.name,
				"visit_date": "2020-03-05",
				"iron_folate": 1,
				"iron_folate_type": "Iron only",
				"breast_exam": 1,
			}
		).insert(ignore_permissions=True)
		visit.submit()
		rows = rows_by_indicator(compute(self.company, YEAR, MONTH))
		first = rows["New ANC clients (1st ANC visit)"]
		self.assertEqual((first["value"], first["15-19"], first["20-24"]), (1, 1, 0))
		self.assertEqual(rows["Clients with 1st ANC contact within 12 weeks"]["value"], 1)  # 10 weeks
		self.assertEqual(rows["Clients with Hb less than 11 g/dl"]["value"], 1)  # booking Hb
		self.assertEqual(rows["Clients tested positive for syphilis"]["value"], 1)
		self.assertEqual(rows["Clients issued with iron"]["value"], 1)
		self.assertEqual(rows["Women done breast examination"]["value"], 1)

	def test_uncaptured_sections_are_listed_blank(self):
		rows = compute(self.company, YEAR, MONTH)
		sections = [r["indicator"] for r in rows if r.get("is_section")]
		for title in NOT_CAPTURED_SECTIONS:
			self.assertIn(title, sections)
		blank = [r for r in rows if r.get("note") == NOT_CAPTURED]
		self.assertEqual(len(blank), sum(len(i) for i in NOT_CAPTURED_SECTIONS.values()))
		self.assertTrue(all(r["value"] is None for r in blank))

	def test_maternity_deaths_and_complications(self):
		mother = patient("Nafula", "Female", "1993-06-01")
		pregnancy = frappe.get_doc(
			{
				"doctype": "Pregnancy Record",
				"patient": mother,
				"company": self.company,
				"booking_date": "2019-10-01",
				"lmp": "2019-07-10",
				"hiv_status": "Known Positive",
			}
		).insert(ignore_permissions=True)
		delivery = frappe.get_doc(
			{
				"doctype": "Delivery Record",
				"pregnancy_record": pregnancy.name,
				"delivery_datetime": "2020-03-08 06:00:00",
				"mode_of_delivery": "Caesarean section",
				"uterotonic": "Carbetocin",
				"pph": 1,
				"maternal_condition": "Alive",
				"babies": [
					{
						"sex": "Male",
						"outcome": "Live birth",
						"birth_weight_g": 2100,
						"condition_at_discharge": "Died",
						"died_on": "2020-03-18 10:00:00",  # day 10: neonatal, not perinatal
					},
					{"sex": "Female", "outcome": "Fresh stillbirth", "birth_weight_g": 1900},
				],
			}
		).insert(ignore_permissions=True)
		delivery.submit()
		rows = rows_by_indicator(compute(self.company, YEAR, MONTH))
		expected = {
			"Caesarean Sections": 1,
			"Mothers given uterotonics - carbetocin": 1,
			"Live births": 1,
			"Low birth weight babies (below 2500 g)": 1,
			"Pre-term babies": 1,  # 34 weeks
			"Total deliveries from HIV+ mothers": 1,
			"Perinatal deaths (fresh stillbirth)": 1,
			"Perinatal deaths 0 to 7 days": 0,
			"Neonatal deaths 0 to 28 days": 1,
			"Post Partum Haemorrhage (PPH) - alive": 1,
			"Post Partum Haemorrhage (PPH) - dead": 0,
		}
		self.assertEqual({k: rows[k]["value"] for k in expected}, expected)
