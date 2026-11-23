# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""v0.61, Bethesda 23 Nov 2026: a starter service list with placeholder
prices, and casualty beds not charged."""

import frappe
from frappe.tests import IntegrationTestCase

from royce_health_ke import casualty, catalogue, routing


class TestStarterServices(IntegrationTestCase):
	def setUp(self):
		self.company = frappe.db.get_single_value("Global Defaults", "default_company")
		routing.seed()

	def test_loads_once_and_routes(self):
		catalogue.load(self.company)
		again = catalogue.load(self.company)
		self.assertEqual(again, {"lab": [], "imaging": [], "procedures": []})
		for name, code, *_rest in catalogue.LAB:
			self.assertTrue(
				frappe.db.exists("Lab Test Template", name) or frappe.db.exists("Item", code), name
			)
		cs = frappe.db.get_value("Clinical Procedure Template", "Caesarean Section", "item_code")
		if cs == "PROC-CS":
			self.assertEqual(frappe.db.get_value("Item", cs, "item_group"), "Surgical Procedures")
			self.assertEqual(
				routing.category_for("Clinical Procedure Template", "Caesarean Section")[1], "Theatre"
			)
			self.assertIn(catalogue.PLACEHOLDER, frappe.db.get_value("Item", cs, "description"))
		self.assertEqual(
			frappe.db.get_value("Observation Template", "Chest X-ray (PA)", "observation_category"), "Imaging"
		)

	def test_casualty_unit_with_free_beds(self):
		parent = frappe.db.get_value(
			"Healthcare Service Unit", {"is_group": 1, "company": self.company}, "name", order_by="lft"
		)
		unit = casualty.make_unit(self.company, parent, beds=2, name="_Test Casualty V061")
		self.assertIn(unit, casualty.units())
		beds = frappe.get_all(
			"Healthcare Service Unit",
			filters={"parent_healthcare_service_unit": unit},
			pluck="service_unit_type",
		)
		self.assertEqual(len(beds), 2)
		if (
			beds[0] == casualty.BED_TYPE
			and frappe.db.get_value("Healthcare Service Unit Type", casualty.BED_TYPE, "item") is None
		):
			self.assertEqual(
				frappe.db.get_value("Healthcare Service Unit Type", casualty.BED_TYPE, "is_billable"), 0
			)
		self.assertEqual(casualty.make_unit(self.company, parent, beds=2, name="_Test Casualty V061"), unit)
