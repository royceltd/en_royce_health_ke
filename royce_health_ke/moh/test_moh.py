# Copyright (c) 2026, Royce Technologies LTD and Contributors
# See license.txt

from datetime import date

from frappe.tests import IntegrationTestCase

from royce_health_ke.moh.moh705 import age_on, longest_prefix
from royce_health_ke.moh.moh717 import age_band
from royce_health_ke.moh.seed705 import rng, rows


class IntegrationTestMOH(IntegrationTestCase):
	def test_longest_prefix_wins(self):
		prefixes = [("ICD-10", "F", "mental"), ("ICD-10", "F84.0", "autism"), ("ICD-10", "B50", "malaria")]
		self.assertEqual(longest_prefix(prefixes, [("ICD-10", "F84.0")]), "autism")
		self.assertEqual(longest_prefix(prefixes, [("ICD-10", "F32.9")]), "mental")
		self.assertEqual(longest_prefix(prefixes, [("ICD-11", "1F40.Z"), ("ICD-10", "b50.9")]), "malaria")
		self.assertIsNone(longest_prefix(prefixes, [("ICD-11", "F84.0")]))  # other system

	def test_age_on_birthday_boundary(self):
		self.assertEqual(age_on("2021-11-30", date(2026, 11, 30)), 5)
		self.assertEqual(age_on("2021-12-01", date(2026, 11, 30)), 4)
		self.assertIsNone(age_on(None, date(2026, 11, 30)))
		self.assertEqual(
			[age_band(a) for a in (0, 4, 5, 59, 60, None)], ["<5", "<5", "5-59", "5-59", "60+", "5-59"]
		)

	def test_seed_rows_are_well_formed(self):
		self.assertEqual(rng("J12", "J18"), ["J12", "J13", "J14", "J15", "J16", "J17", "J18"])
		seen = set()
		for form, _seq, code, label, _kind, codes in rows():
			self.assertNotIn((form, code), seen)
			seen.add((form, code))
			self.assertTrue(label)
			for system, prefix in codes:
				self.assertIn(system, ("ICD-10", "ICD-11", "LOINC"))
				self.assertEqual(prefix, prefix.upper())
		for form in ("705A", "705B"):
			kinds = [k for f, _s, _c, _l, k, _x in rows() if f == form]
			for kind in ("All Other Diseases", "First Attendance", "Re-Attendance", "Lab Test"):
				self.assertEqual(kinds.count(kind), 1, (form, kind))
