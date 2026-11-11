# Copyright (c) 2026, Royce Technologies LTD and Contributors
# See license.txt

from datetime import datetime, timedelta

import frappe
from frappe.tests import IntegrationTestCase

from royce_health_ke import tat

T0 = datetime(2026, 11, 11, 8, 0)


def row(test, ordered_min, started_min, result_min, target=None, approximate=0):
	return tat.with_minutes(
		{
			"department": "Laboratory",
			"test": test,
			"ordered_at": T0 + timedelta(minutes=ordered_min),
			"collected_at": None,
			"started_at": T0 + timedelta(minutes=started_min),
			"result_at": T0 + timedelta(minutes=result_min),
			"approximate": approximate,
			"target": target,
		}
	)


class IntegrationTestTat(IntegrationTestCase):
	def test_steps_in_minutes(self):
		r = row("Hb", 0, 20, 65, target=60)
		self.assertEqual((r["wait_minutes"], r["work_minutes"], r["total_minutes"]), (20, 45, 65))
		self.assertEqual(r["within_target"], "No")
		self.assertEqual(row("Hb", 0, 10, 50, target=60)["within_target"], "Yes")
		self.assertEqual(row("Hb", 0, 10, 50)["within_target"], "")  # no target
		self.assertIsNone(row("Hb", 30, 10, 20)["wait_minutes"])  # out of order: not counted

	def test_summary_per_test(self):
		rows = [row("Hb", 0, 5, m, target=60) for m in (30, 40, 50, 70, 90)] + [row("WBC", 0, 5, 20)]
		hb, wbc = tat.summarise(rows)
		self.assertEqual(
			(hb["test"], hb["count"], hb["median_minutes"], hb["average_minutes"]), ("Hb", 5, 50, 56)
		)
		self.assertEqual(hb["p90_minutes"], 90)
		self.assertEqual(hb["within_target_pct"], 60)  # 3 of 5
		self.assertIsNone(wbc["within_target_pct"])

	def test_result_time_is_stamped_on_submit(self):
		stamped = {}

		class Doc(frappe._dict):
			def db_set(self, field, value, update_modified=True):
				stamped[field] = value

		tat.lab_test_submitted(Doc(ke_result_at=None))
		self.assertIn("ke_result_at", stamped)
		stamped.clear()
		tat.lab_test_submitted(Doc(ke_result_at=T0))  # already stamped: kept
		self.assertEqual(stamped, {})

	def test_report_runs(self):
		from royce_health_ke.kenya_health.report.turnaround_time import turnaround_time

		result = turnaround_time.execute({"from_date": "2026-01-01", "to_date": "2026-12-31"})
		self.assertEqual(len(result[0]), 8)
		detail = turnaround_time.execute(
			{"from_date": "2026-01-01", "to_date": "2026-12-31", "each_request": 1}
		)
		self.assertTrue(all(r["total_minutes"] is None or r["total_minutes"] >= 0 for r in detail[1]))
