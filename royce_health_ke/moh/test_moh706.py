# Copyright (c) 2026, Royce Technologies LTD and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase

from royce_health_ke.moh import moh706
from royce_health_ke.moh.seed706 import ROWS


def indicator(kind, words="", low=None, high=None, age_group=None, component=None):
	return frappe._dict(
		kind=kind,
		words=[w.strip() for w in words.split(",") if w.strip()],
		range_low=low,
		range_high=high,
		age_group=age_group,
		tests=[frappe._dict(lab_test_template="URINALYSIS", component=component)],
	)


class IntegrationTestMOH706(IntegrationTestCase):
	def test_positive_words_respect_negatives(self):
		words = ["reactive", "seen", "+", "positive"]
		for value in ("Reactive", "P. falciparum seen (++), trophozoites", "2+", "POSITIVE"):
			self.assertTrue(moh706.is_positive(value, words), value)
		for value in (
			"Non-reactive",
			"Not seen",
			"Negative",
			"nil",
			"",
			None,
			"No parasites seen - negative",
		):
			self.assertFalse(moh706.is_positive(value, words), value)

	def test_numbers_and_ranges(self):
		self.assertEqual(moh706.number("10.8 g/dL"), 10.8)
		self.assertEqual(moh706.number("1,250"), 1250)
		self.assertIsNone(moh706.number("trace"))
		self.assertTrue(moh706.in_range("4.9", 0, 5))
		self.assertFalse(moh706.in_range("5.0", 0, 5))  # the high value is excluded
		self.assertTrue(moh706.in_range("5", 5, 10))
		self.assertFalse(moh706.in_range("3", 0, None))  # no band set

	def test_age_groups(self):
		self.assertTrue(moh706.matches_age(4, "Under 5"))
		self.assertFalse(moh706.matches_age(5, "Under 5"))
		self.assertTrue(moh706.matches_age(5, "5 and above"))
		self.assertFalse(moh706.matches_age(None, "Under 5"))
		self.assertTrue(moh706.matches_age(None, None))

	def test_counting_components_of_a_compound_test(self):
		tests = [frappe._dict(name=f"LT{i}", template="URINALYSIS") for i in (1, 2, 3)]
		results = {
			"LT1": [("glucose", "2+"), ("proteins", "Negative")],
			"LT2": [("glucose", "Negative"), ("proteins", "Trace")],
			"LT3": [("proteins", "1+")],  # glucose not done
		}
		ages = {"LT1": 3, "LT2": 30, "LT3": 40}
		count = moh706.count
		self.assertEqual(count(indicator("Tests done", component="Glucose"), tests, results, ages), 2)
		self.assertEqual(count(indicator("Positive", "+", component="Glucose"), tests, results, ages), 1)
		self.assertEqual(
			count(indicator("Positive", "trace, +", component="Proteins"), tests, results, ages), 2
		)
		self.assertEqual(count(indicator("Tests done", age_group="Under 5"), tests, results, ages), 1)
		self.assertEqual(count(indicator("Tests done"), tests, results, ages), 3)

	def test_seed_rows_are_well_formed(self):
		codes = [r[1] for r in ROWS]
		self.assertEqual(len(codes), len(set(codes)))
		for _section, code, _label, kind, words, low, high, age_group in ROWS:
			self.assertIn(kind, ("Tests done", "Positive", "Numeric range"), code)
			if kind == "Positive":
				self.assertTrue(words, code)
			if kind == "Numeric range" and high is not None:
				self.assertLess(low, high, code)
			self.assertIn(age_group, ("", "Under 5", "5 and above"), code)

	def test_report_lists_unmapped_rows(self):
		company = frappe.db.get_value("Company", {}, "name")
		if not company:
			self.skipTest("no company")
		rows = moh706.compute(company, 2020, 3)
		unmapped = [r for r in rows if r.get("note") == moh706.NOT_MAPPED]
		self.assertTrue(all(r["value"] is None for r in unmapped))
		self.assertTrue(any(r.get("is_section") for r in rows))
