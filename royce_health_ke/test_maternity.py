# Copyright (c) 2026, Royce Technologies LTD and Contributors
# See license.txt

from datetime import date

from frappe.tests import IntegrationTestCase

from royce_health_ke.maternity import edd_from_lmp, gestation_weeks, labour_alert, pnc_timing


class IntegrationTestMaternity(IntegrationTestCase):
	def test_dates(self):
		self.assertEqual(edd_from_lmp("2026-02-01"), date(2026, 11, 8))
		self.assertEqual(gestation_weeks("2026-02-01", "2026-11-05"), 39)
		self.assertIsNone(gestation_weeks(None, "2026-11-05"))

	def test_pnc_timing_buckets(self):
		self.assertEqual(pnc_timing("2026-11-05 04:30:00", "2026-11-07"), "Within 48 hours")
		self.assertEqual(pnc_timing("2026-11-05 04:30:00", "2026-11-08"), "3 days to under 6 weeks")
		self.assertEqual(pnc_timing("2026-11-05 04:30:00", "2026-12-17"), "6 weeks and after")

	def test_labour_alerts(self):
		self.assertEqual(
			labour_alert({"fetal_heart_rate": 140, "maternal_pulse": 88, "contractions_per_10min": 4}), ""
		)
		alert = labour_alert(
			{
				"fetal_heart_rate": 165,
				"bp_systolic": 150,
				"bp_diastolic": 95,
				"liquor": "Meconium",
				"contractions_per_10min": 2,
			}
		)
		for part in ("FHR 165", "BP 150/95", "Liquor Meconium", "Contractions 2/10 min"):
			self.assertIn(part, alert)
