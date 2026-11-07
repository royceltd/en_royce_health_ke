# Copyright (c) 2026, Royce Technologies LTD and Contributors
# See license.txt

from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from royce_health_ke import kitchen, laundry


def order(name, diet, start, end=None, meals=3, ip="IP1"):
	return frappe._dict(
		name=name, diet_type=diet, start_date=start, end_date=end, meals_per_day=meals, inpatient_record=ip
	)


class IntegrationTestKitchen(IntegrationTestCase):
	def test_later_order_wins_on_overlap(self):
		orders = [
			order("A", "Normal", date(2026, 11, 1), date(2026, 11, 3)),
			order("B", "Soft", date(2026, 11, 3)),
		]
		self.assertIsNone(kitchen.active_order(orders, date(2026, 10, 31)))
		self.assertEqual(kitchen.active_order(orders, date(2026, 11, 2)).name, "A")
		self.assertEqual(kitchen.active_order(orders, date(2026, 11, 3)).name, "B")
		self.assertEqual(kitchen.active_order(orders, date(2026, 11, 9)).name, "B")

	def runs(self, orders, billed=(), until=date(2026, 11, 6), discharged=None):
		ip = frappe._dict(
			name="IP1", admitted_datetime=datetime(2026, 11, 1, 10), discharge_datetime=discharged
		)

		def get_all(doctype, **kwargs):
			return ["Nil by Mouth"] if doctype == "Diet Type" else [ip]

		with (
			patch.object(kitchen, "orders_of", return_value=orders),
			patch.object(kitchen, "billed_days", return_value=set(billed)),
			patch.object(kitchen.frappe, "get_all", side_effect=get_all),
		):
			return [
				(r.order.name, r.start.day, r.end.day, r.days) for r in kitchen.unbilled_runs(["IP1"], until)
			]

	def test_meal_days_by_diet_skipping_nil_by_mouth(self):
		orders = [
			order("NBM", "Nil by Mouth", date(2026, 11, 1), date(2026, 11, 2), meals=0),
			order("SOFT", "Soft", date(2026, 11, 2), date(2026, 11, 4)),
			order("NORMAL", "Normal", date(2026, 11, 4)),
		]
		# 1st nil by mouth; 2nd-3rd soft (soft wins on the 2nd); 4th-6th normal
		self.assertEqual(self.runs(orders), [("SOFT", 2, 3, 2), ("NORMAL", 4, 6, 3)])

	def test_days_already_billed_and_discharge(self):
		orders = [order("NORMAL", "Normal", date(2026, 11, 1))]
		billed = {("NORMAL", date(2026, 11, d)) for d in (1, 2, 3)}  # on the interim bill
		self.assertEqual(self.runs(orders, billed), [("NORMAL", 4, 6, 3)])
		self.assertEqual(
			self.runs(orders, billed, discharged=datetime(2026, 11, 5, 11)), [("NORMAL", 4, 5, 2)]
		)


class IntegrationTestLaundry(IntegrationTestCase):
	def route(self, movement, condemn_from=None):
		s = frappe._dict(linen_store="STORE", laundry="LAUNDRY", item_group="Linen")
		doc = SimpleNamespace(movement_type=movement, ward="Ward A", condemn_from=condemn_from)
		with (
			patch.object(laundry, "settings", return_value=s),
			patch.object(laundry, "ward_store", return_value="WARD-A"),
		):
			return laundry.route(doc)

	def test_routes(self):
		self.assertEqual(self.route(laundry.ISSUE), ("STORE", "WARD-A"))
		self.assertEqual(self.route(laundry.COLLECT), ("WARD-A", "LAUNDRY"))
		self.assertEqual(self.route(laundry.RETURN), ("LAUNDRY", "STORE"))
		self.assertEqual(self.route(laundry.CONDEMN, "Laundry"), ("LAUNDRY", None))
		self.assertEqual(self.route(laundry.CONDEMN, "Linen store"), ("STORE", None))
		self.assertEqual(self.route(laundry.LOST), ("WARD-A", None))

	def test_missing_setup_is_explained(self):
		with patch.object(laundry, "settings", return_value=frappe._dict(linen_store=None, laundry=None)):
			with self.assertRaises(frappe.ValidationError):
				laundry.route(SimpleNamespace(movement_type=laundry.RETURN, ward=None, condemn_from=None))
		with self.assertRaises(frappe.ValidationError):
			laundry.ward_store("_Test No Such Ward")

	def test_only_linen_stock_items_move(self):
		if not frappe.db.exists("Item Group", "_Test Linen"):
			frappe.get_doc(
				{
					"doctype": "Item Group",
					"item_group_name": "_Test Linen",
					"parent_item_group": "All Item Groups",
				}
			).insert(ignore_permissions=True)
		for code, group in (("_TEST-LIN-SHEET", "_Test Linen"), ("_TEST-NOT-LINEN", "Services")):
			if not frappe.db.exists("Item", code):
				frappe.get_doc(
					{
						"doctype": "Item",
						"item_code": code,
						"item_group": group,
						"stock_uom": "Nos",
						"is_stock_item": 1,
					}
				).insert(ignore_permissions=True)
		s = frappe._dict(linen_store="STORE", laundry="LAUNDRY", item_group="_Test Linen")

		def movement(code, qty=2):
			return SimpleNamespace(
				movement_type=laundry.RETURN,
				ward="x",
				condemn_from=None,
				items=[frappe._dict(idx=1, item_code=code, qty=qty)],
			)

		with patch.object(laundry, "settings", return_value=s):
			doc = movement("_TEST-LIN-SHEET")
			laundry.validate_movement(doc)
			self.assertEqual((doc.from_warehouse, doc.to_warehouse, doc.ward), ("LAUNDRY", "STORE", None))
			for bad in (movement("_TEST-NOT-LINEN"), movement("_TEST-LIN-SHEET", 0)):
				with self.assertRaises(frappe.ValidationError):
					laundry.validate_movement(bad)
