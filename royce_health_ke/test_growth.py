# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Child growth (WHO z-scores) and the allied clinical services. The tests use
a small synthetic LMS table, so they never need the internet or the real WHO
download; the real tables were checked against WHO's published charts."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from royce_health_ke import clinical, growth

# L, M, S chosen so the arithmetic is easy to follow: with L = 1 a value is
# M * (1 + S * z), so 10 kg is the median and each SD is 1 kg.
FLAT = [1.0, 10.0, 0.1]
SKEWED = [-0.5, 10.0, 0.1]


def synthetic_tables(params=FLAT):
	age = {str(d): list(params) for d in range(0, growth.MAX_DAYS + 1)}
	length = {f"{x / 10:.1f}": list(params) for x in range(450, 1201)}
	return {
		ind: {"1": dict(table), "2": dict(table)}
		for ind, table in (("wfa", age), ("lhfa", age), ("bmi", age), ("wfl", length), ("wfh", length))
	}


class TestGrowth(IntegrationTestCase):
	def setUp(self):
		growth._tables = synthetic_tables()

	def tearDown(self):
		growth._tables = None

	def test_lms_zscore(self):
		self.assertEqual(growth.zscore("lhfa", 1, 100, 10.0), 0)
		self.assertEqual(growth.zscore("lhfa", 1, 100, 8.0), -2)
		self.assertEqual(growth.zscore("lhfa", 2, 100, 11.5), 1.5)
		self.assertIsNone(growth.zscore("lhfa", 1, 100, None))
		self.assertIsNone(growth.zscore("lhfa", 1, growth.MAX_DAYS + 10, 10.0))  # beyond 5 years

	def test_weight_beyond_three_sd_uses_who_restricted_method(self):
		growth._tables = synthetic_tables(SKEWED)
		L, M, S = SKEWED
		sd3, sd2 = growth._value_at(L, M, S, 3), growth._value_at(L, M, S, 2)
		value = sd3 + (sd3 - sd2)  # one SD3-SD2 distance above +3 SD
		self.assertEqual(growth.zscore("wfa", 1, 100, value), 4)
		# length/height is not restricted: the plain LMS z-score
		plain = round(((value / M) ** L - 1) / (L * S), 2)
		self.assertEqual(growth.zscore("lhfa", 1, 100, value), plain)

	def test_classification(self):
		self.assertEqual(
			growth.status({"wflh": -3.2, "lhfa": -2.5, "wfa": -3.1}),
			"Severe wasting (SAM), Stunted, Severely underweight",
		)
		self.assertEqual(growth.status({"wflh": -2.4, "lhfa": 0, "wfa": -1}), "Moderate wasting (MAM)")
		self.assertEqual(growth.status({"wflh": 2.5, "lhfa": 0.2, "wfa": 1}), "Overweight")
		self.assertEqual(growth.status({"wflh": 0.1, "lhfa": -0.3, "wfa": 0}), "Normal growth")
		self.assertEqual(growth.status({"wflh": None, "lhfa": None, "wfa": None}), "")

	def test_length_under_two_height_from_two(self):
		baby = growth.assess("Female", add_days(today(), -300), today(), weight=10, height_cm=70)
		child = growth.assess("Female", add_days(today(), -1000), today(), weight=10, height_cm=90)
		self.assertEqual((baby["wflh"], child["wflh"]), (0, 0))
		self.assertIsNone(growth.assess("Female", add_days(today(), -2500), today(), weight=10))  # over 5
		self.assertIsNone(growth.assess(None, add_days(today(), -300), today(), weight=10))

	def make_child(self, days_old=400):
		return (
			frappe.get_doc(
				{
					"doctype": "Patient",
					"first_name": "Growth",
					"last_name": f"Child {frappe.generate_hash(length=6)}",
					"sex": "Male",
					"dob": add_days(today(), -days_old),
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

	def test_vital_signs_get_z_scores_and_status(self):
		child = self.make_child()
		vs = frappe.get_doc(
			{"doctype": "Vital Signs", "patient": child, "signs_date": today(), "weight": 6.5, "height": 0.75}
		).insert(ignore_permissions=True)
		self.assertEqual((vs.ke_wfa_z, vs.ke_wflh_z), (-3.5, -3.5))
		self.assertIn("Severe wasting (SAM)", vs.ke_nutrition_status)
		adult = frappe.get_doc(
			{
				"doctype": "Vital Signs",
				"patient": self.make_child(days_old=9000),
				"signs_date": today(),
				"weight": 60,
				"height": 1.7,
			}
		).insert(ignore_permissions=True)
		self.assertFalse(adult.ke_nutrition_status)

	def test_growth_chart_has_who_curves_and_measurements(self):
		child = self.make_child()
		for days_ago, weight in ((200, 8.0), (0, 9.0)):
			frappe.get_doc(
				{
					"doctype": "Vital Signs",
					"patient": child,
					"signs_date": add_days(today(), -days_ago),
					"weight": weight,
				}
			).insert(ignore_permissions=True)
		data = growth.chart(child, "wfa")
		self.assertEqual([c["z"] for c in data["curves"]], [-3, -2, 0, 2, 3])
		self.assertEqual(len(data["curves"][0]["values"]), 61)
		self.assertEqual(data["curves"][2]["values"][0], 10.0)
		self.assertEqual([m["value"] for m in data["measurements"]], [8.0, 9.0])
		self.assertEqual(data["measurements"][1]["z"], -1)

	def test_parse_who_table(self):
		text = "sex\tlength\tl\tm\ts\tlorh\n1\t45\t-0.3521\t2.441\t0.09182\tL\n2\t45.1\t-0.3833\t2.4607\t0.09029\tL\n"
		table = growth.parse(text, "length")
		self.assertEqual(table["1"]["45.0"], [-0.3521, 2.441, 0.09182])
		self.assertIn("45.1", table["2"])


class TestClinicalServices(IntegrationTestCase):
	def test_services_are_orderable_and_not_billed_until_priced(self):
		clinical.setup_services()
		for name, _item_code, _description in clinical.SERVICES:
			t = frappe.db.get_value("Therapy Type", name, ["is_billable", "item"], as_dict=True)
			self.assertIsNotNone(t, name)
			self.assertEqual(t.is_billable, 0)
		clinical.setup_services()  # idempotent
		self.assertEqual(
			frappe.db.count("Therapy Type", {"name": ["in", [s[0] for s in clinical.SERVICES]]}), 4
		)
		for note in clinical.NOTE_TYPES:
			self.assertTrue(frappe.db.exists("Clinical Note Type", note))

	def test_counselling_session_keeps_notes(self):
		clinical.setup_services()
		self.assertTrue(frappe.get_meta("Therapy Session").has_field("ke_session_notes"))
