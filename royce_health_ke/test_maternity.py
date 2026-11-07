# Copyright (c) 2026, Royce Technologies LTD and Contributors
# See license.txt

from datetime import date

import frappe
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

	def test_labour_care_guide_alert_column(self):
		from royce_health_ke.maternity import observation_alerts

		quiet = {
			"companion": "Yes", "pain_relief": "Declined", "oral_fluid": "Yes", "posture": "Mobile",
			"fetal_heart_rate": 140, "fhr_deceleration": "Early", "liquor": "Meconium ++", "fetal_position": "Anterior",
			"caput": "++", "moulding": "++", "maternal_pulse": 100, "bp_systolic": 120, "bp_diastolic": 80,
			"temperature": 36.8, "urine_protein": "+", "urine_acetone": "Trace",
			"contractions_per_10min": 4, "contraction_duration_sec": 45,
		}  # fmt: skip
		self.assertEqual(observation_alerts(quiet, 110), [])
		loud = {
			"companion": "No", "pain_relief": "No", "oral_fluid": "No", "posture": "Supine",
			"fetal_heart_rate": 115, "fhr_deceleration": "Late", "liquor": "Meconium +++", "fetal_position": "Transverse",
			"caput": "+++", "moulding": "+++", "maternal_pulse": 55, "bp_systolic": 75, "bp_diastolic": 95,
			"temperature": 34.8, "urine_protein": "++", "urine_acetone": "+++",
			"contractions_per_10min": 6, "contraction_duration_sec": 70,
		}  # fmt: skip
		flagged = {f for f, _m in observation_alerts(loud, 120)}  # a facility alerting below 120
		self.assertEqual(flagged, set(loud))
		self.assertNotIn("fetal_heart_rate", {f for f, _m in observation_alerts(loud, 110)})

	def test_cervix_lag_time_alerts(self):
		from royce_health_ke.maternity import progress_alerts

		def obs(time, cm):
			return frappe._dict(time=f"2026-11-05 {time}:00", cervical_dilatation_cm=cm)

		rows = [
			obs("08:00", 5),
			obs("12:00", 5),
			obs("14:00", 5),
			obs("15:00", 7),
			obs("17:00", 7),
			obs("18:30", 7),
		]
		alerts = progress_alerts(rows)
		messages = {r.time[11:16]: alerts.get(id(r)) for r in rows}
		self.assertIsNone(messages["12:00"])  # 4 h at 5 cm: under 6 h
		self.assertEqual(messages["14:00"], "Cervix 5 cm for 6.0 h")
		self.assertIsNone(messages["17:00"])  # 2 h at 7 cm: under 3 h
		self.assertEqual(messages["18:30"], "Cervix 7 cm for 3.5 h")
