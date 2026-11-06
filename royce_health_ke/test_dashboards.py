# Copyright (c) 2026, Royce Technologies LTD and Contributors
# See license.txt

from datetime import date, datetime
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from royce_health_ke import dashboards as d


class IntegrationTestDashboards(IntegrationTestCase):
	def test_period_dates(self):
		on = date(2026, 11, 7)  # a Saturday
		self.assertEqual(d.period_dates("Today", on), (on, on))
		self.assertEqual(d.period_dates("This Week", on), (date(2026, 11, 2), on))
		self.assertEqual(d.period_dates("This Month", on), (date(2026, 11, 1), on))
		self.assertEqual(d.period_dates("Last Month", on), (date(2026, 10, 1), date(2026, 10, 31)))
		self.assertEqual(d.period_dates("This Quarter", on), (date(2026, 10, 1), on))
		self.assertEqual(d.period_dates("This Year", on), (date(2026, 1, 1), on))
		self.assertEqual(d.period_dates("Last 30 Days", on), (date(2026, 10, 9), on))
		self.assertEqual(d.period_dates("Last 12 Months", on), (date(2025, 11, 8), on))

	def test_revenue_department_from_what_was_ordered(self):
		pharmacy = {"Drug"}
		ordered = {
			("Service Request", "SR-LAB"): d.LABORATORY,
			("Service Request", "SR-XRAY"): d.RADIOLOGY,
		}
		inpatients = {"P1": {date(2026, 11, 6)}}

		def dept(
			reference_dt=None, reference_dn=None, item_group="Services", patient=None, day=date(2026, 11, 6)
		):
			line = frappe._dict(
				reference_dt=reference_dt,
				reference_dn=reference_dn,
				item_group=item_group,
				patient=patient,
				posting_date=day,
			)
			return d._department(line, pharmacy, ordered, inpatients)

		self.assertEqual(dept("Inpatient Occupancy"), d.INPATIENT)
		self.assertEqual(dept("Medication Request"), d.PHARMACY)
		self.assertEqual(dept(item_group="Drug"), d.PHARMACY)  # over-the-counter sale
		self.assertEqual(dept("Patient Encounter"), d.CONSULTATION)
		self.assertEqual(dept("Patient Appointment"), d.CONSULTATION)
		self.assertEqual(dept("Clinical Procedure"), d.PROCEDURES)
		self.assertEqual(dept("Service Request", "SR-LAB"), d.LABORATORY)
		self.assertEqual(dept("Service Request", "SR-XRAY"), d.RADIOLOGY)
		self.assertEqual(dept(patient="P1"), d.INPATIENT)  # nursing charge while admitted
		self.assertEqual(dept(patient="P1", day=date(2026, 11, 9)), d.OTHER)
		self.assertEqual(dept(), d.OTHER)

	def test_midnight_census(self):
		beds = [frappe._dict(name="B1"), frappe._dict(name="B2")]
		stays = [
			# in on the 5th, out at 23:02 on the 6th: one night (the 5th)
			frappe._dict(check_in=datetime(2026, 11, 5, 13), check_out=datetime(2026, 11, 6, 23, 2)),
			# still in: every night from the 6th
			frappe._dict(check_in=datetime(2026, 11, 6, 8), check_out=None),
			# left before the period
			frappe._dict(check_in=datetime(2026, 10, 1, 8), check_out=datetime(2026, 10, 3, 8)),
		]
		with (
			patch.object(d, "beds", return_value=beds),
			patch.object(d.frappe, "get_all", return_value=stays),
		):
			census = d.midnight_census("X", date(2026, 11, 4), date(2026, 11, 8))
		self.assertEqual(
			[census[date(2026, 11, n)] for n in range(4, 9)],
			[0, 1, 1, 1, 1],
		)

	def test_stock_status_worst_first(self):
		s = frappe._dict(min_days_of_cover=14, expiry_warning_days=90)
		on = date(2026, 11, 7)
		self.assertEqual(d.stock_status(0, 10, None, None, on, s), "Out of Stock")
		self.assertEqual(d.stock_status(10, 10, 5, "2026-11-20", on, s), "Below Reorder Level")
		self.assertEqual(d.stock_status(50, 10, 5, "2026-11-20", on, s), "Low Cover")
		self.assertEqual(d.stock_status(50, 10, 30, "2026-12-20", on, s), "Expiring")
		self.assertEqual(d.stock_status(50, 0, None, "2027-06-01", on, s), "OK")

	def test_dashboards_refuse_users_who_cannot_read_the_records(self):
		frappe.set_user("Guest")
		try:
			for card in (
				d.revenue_card,
				d.claims_awaiting_payment_card,
				d.bed_occupancy_card,
				d.out_of_stock_card,
			):
				with self.assertRaises(frappe.PermissionError):
					card()
		finally:
			frappe.set_user("Administrator")

	def test_every_card_and_chart_runs(self):
		company = frappe.db.get_value("Company", {}, "name")
		if not company:
			self.skipTest("no company")
		filters = frappe.as_json({"company": company, "period": "This Year"})
		for name, method in frappe.get_all(
			"Number Card", filters={"module": "Kenya Health"}, fields=["name", "method"], as_list=True
		):
			result = frappe.get_attr(method)(filters=filters)
			self.assertIn("value", result, name)
		for chart in (
			d.revenue_by_department,
			d.bed_occupancy_by_ward,
			d.bed_occupancy_trend,
			d.claims_by_payor,
			d.practitioner_activity,
		):
			result = chart(filters=filters)
			self.assertEqual(len(result["labels"]), len(result["datasets"][0]["values"]))
