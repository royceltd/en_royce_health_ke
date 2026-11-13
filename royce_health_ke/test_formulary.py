# Copyright (c) 2026, Royce Technologies LTD and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase


def ensure(doctype, name, data):
	if not frappe.db.exists(doctype, name):
		frappe.get_doc({"doctype": doctype, **data}).insert(ignore_permissions=True)


def medication(generic, item_code, rate=0, stock_uom="Nos", strength=500):
	return frappe.get_doc(
		{
			"doctype": "Medication",
			"generic_name": generic,
			"medication_class": "_Test Formulary Class",
			"strength": strength,
			"strength_uom": "mg",
			"dosage_form": "Tablet",
			"linked_items": [
				{
					"item_code": item_code,
					"item_group": "Drug",
					"stock_uom": stock_uom,
					"rate": rate,
					"is_billable": 1,
				}
			],
		}
	).insert(ignore_permissions=True)


def uploaded_item(code, name, price=None):
	"""An Item (and selling price) as a migration uploads them, before the formulary."""
	if not frappe.db.exists("Item", code):
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": code,
				"item_name": name,
				"item_group": "Drug",
				"stock_uom": "Nos",
				"is_stock_item": 1,
			}
		).insert(ignore_permissions=True)
	if price:
		frappe.get_doc(
			{
				"doctype": "Item Price",
				"item_code": code,
				"price_list": "Standard Selling",
				"price_list_rate": price,
			}
		).insert(ignore_permissions=True)


class IntegrationTestFormulary(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		ensure("Medication Class", "_Test Formulary Class", {"medication_class": "_Test Formulary Class"})
		ensure("UOM", "mg", {"uom_name": "mg"})
		ensure("Dosage Form", "Tablet", {"dosage_form": "Tablet"})

	def test_existing_item_keeps_its_name_and_price(self):
		uploaded_item("_TFRM-MET500", "Metformin 500mg Tablet", price=5)
		med = medication("_Test Formulary Metformin", "_TFRM-MET500", rate=7)
		self.assertEqual(med.linked_items[0].item, "_TFRM-MET500")
		self.assertEqual(frappe.db.get_value("Item", "_TFRM-MET500", "item_name"), "Metformin 500mg Tablet")
		prices = frappe.get_all("Item Price", {"item_code": "_TFRM-MET500"}, pluck="price_list_rate")
		self.assertEqual(prices, [5])

	def test_existing_item_without_price_gets_the_rows_price(self):
		uploaded_item("_TFRM-NIF20", "Nifedipine 20mg Tablet")
		medication("_Test Formulary Nifedipine", "_TFRM-NIF20", rate=4)
		prices = frappe.get_all("Item Price", {"item_code": "_TFRM-NIF20"}, ["price_list", "price_list_rate"])
		self.assertEqual([(p.price_list, p.price_list_rate) for p in prices], [("Standard Selling", 4)])

	def test_unit_must_match(self):
		uploaded_item("_TFRM-ATE50", "Atenolol 50mg Tablet")
		frappe.db.exists("UOM", "Box") or frappe.get_doc({"doctype": "UOM", "uom_name": "Box"}).insert()
		with self.assertRaises(frappe.ValidationError):
			medication("_Test Formulary Atenolol", "_TFRM-ATE50", stock_uom="Box")

	def test_uploaded_strength_is_in_the_name(self):
		# Data Import hands over floats; Frappe's naming used to drop them
		med = medication("_Test Formulary Glibenclamide", "_TFRM-GLB5", strength=5.0)
		self.assertEqual(med.name, "Tablet _Test Formulary Glibenclamide 5mg")
		self.assertEqual(med.strength, 5)
		med = medication("_Test Formulary Warfarin", "_TFRM-WAR25", strength=2.5)
		self.assertEqual(med.name, "Tablet _Test Formulary Warfarin 2.5mg")
		self.assertEqual(frappe.db.get_value("Medication", med.name, "strength"), 2.5)

	def test_new_code_still_creates_the_item(self):
		medication("_Test Formulary Losartan", "_TFRM-LOS50", rate=12)
		self.assertTrue(frappe.db.exists("Item", "_TFRM-LOS50"))
		self.assertEqual(
			frappe.db.get_value("Item Price", {"item_code": "_TFRM-LOS50"}, "price_list_rate"), 12
		)
