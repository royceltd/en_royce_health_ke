# Copyright (c) 2026, Royce Technologies LTD and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase, UnitTestCase

from royce_health_ke.moh.periods import combine, months_in


class TestPeriods(UnitTestCase):
	def test_months_in_each_period(self):
		self.assertEqual(months_in({"year": 2026, "month": 4}), [(2026, 4)])
		self.assertEqual(
			months_in({"year": 2026, "period": "Quarter", "quarter": 2}), [(2026, 4), (2026, 5), (2026, 6)]
		)
		self.assertEqual(len(months_in({"year": "2026", "period": "Year"})), 12)

	def test_combine_sums_counts_per_section(self):
		jan = [
			{"indicator": "Ward A", "value": None, "is_section": 1},
			{"indicator": "Admissions", "value": 3, "<5": 1},
			{"indicator": "Not captured", "value": None, "note": "Not captured yet"},
			{"indicator": "Ward B", "value": None, "is_section": 1},
			{"indicator": "Admissions", "value": 2},
		]
		feb = [
			{"indicator": "Ward A", "value": None, "is_section": 1},
			{"indicator": "Admissions", "value": 4, "<5": 2},
			{"indicator": "Sex not recorded", "value": 1},
			{"indicator": "Not captured", "value": None, "note": "Not captured yet"},
			{"indicator": "Ward B", "value": None, "is_section": 1},
			{"indicator": "Admissions", "value": 5},
		]
		rows = combine([jan, feb])
		values = [(r["indicator"], r["value"]) for r in rows]
		self.assertEqual(
			values,
			[
				("Ward A", None),
				("Admissions", 7),
				("Not captured", None),
				("Ward B", None),
				("Admissions", 7),
				("Sex not recorded", 1),
			],
		)
		self.assertEqual(rows[1]["<5"], 3)
		self.assertEqual(rows[2]["note"], "Not captured yet")


class IntegrationTestPeriodReports(IntegrationTestCase):
	def test_every_moh_report_runs_for_a_quarter_and_a_year(self):
		company = frappe.db.get_single_value("Global Defaults", "default_company") or frappe.db.get_value(
			"Company", {}, "name"
		)
		for report in (
			"MOH 705 Outpatient Summary",
			"MOH 706 Laboratory Summary",
			"MOH 711 Integrated Summary",
			"MOH 717 Service Workload",
		):
			module = frappe.get_attr(
				f"royce_health_ke.kenya_health.report.{frappe.scrub(report)}.{frappe.scrub(report)}.execute"
			)
			for filters in (
				{"period": "Quarter", "quarter": 3},
				{"period": "Year"},
			):
				columns, data = module({"company": company, "year": 2026, **filters})[:2]
				self.assertTrue(columns, report)
				self.assertTrue(data, report)
		columns, _data = frappe.get_attr(
			"royce_health_ke.kenya_health.report.moh_705_outpatient_summary.moh_705_outpatient_summary.execute"
		)({"company": company, "year": 2026, "period": "Quarter", "quarter": 3})
		self.assertEqual([c["fieldname"] for c in columns][2:6], ["m7", "m8", "m9", "total"])
