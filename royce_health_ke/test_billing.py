# Copyright (c) 2026, Royce Technologies LTD and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase

from royce_health_ke.billing import nights


class IntegrationTestBilling(IntegrationTestCase):
	def test_nights_count_midnights_at_least_one(self):
		self.assertEqual(nights("2026-11-05 13:00:00", "2026-11-06 10:00:00"), 1)
		self.assertEqual(nights("2026-11-05 13:00:00", "2026-11-05 18:00:00"), 1)  # day case
		self.assertEqual(nights("2026-11-05 23:30:00", "2026-11-08 08:00:00"), 3)

	def test_settle_rejected_refuses_unknown_action(self):
		from royce_health_ke.claims import settle_rejected

		with self.assertRaises(frappe.ValidationError):
			settle_rejected("does-not-matter", "Ignore")
