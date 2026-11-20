# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""MOH reports from Bethesda's monthly list (18 Nov 2026): the commodity
reports (F-CDRR), the vaccine fridge's temperature log, the immunisation
register and MOH 710."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, flt, get_first_day, getdate, nowdate

from royce_health_ke import immunisation
from royce_health_ke.moh import cold_chain, commodities


def _patient(sex="Female", age_days=120):
	p = frappe.get_doc(
		{
			"doctype": "Patient",
			"first_name": "CWC",
			"last_name": f"Test {frappe.generate_hash(length=6)}",
			"sex": sex,
			"dob": add_days(nowdate(), -age_days),
			"mobile": "0712345678",
		}
	)
	p.flags.ignore_registration_check = True
	p.flags.ignore_consent_check = True
	return p.insert(ignore_permissions=True).name


class TestCommodityReports(IntegrationTestCase):
	def setUp(self):
		commodities.seed()
		self.company = frappe.db.get_single_value("Global Defaults", "default_company")

	def test_forms_and_loss_type_seeded(self):
		for form in ("MOH 747A", "MOH 730A", "MOH 730B", "MOH 643B", "TB and Leprosy"):
			doc = frappe.get_doc(commodities.FORM, form)
			self.assertTrue(doc.items, form)
		self.assertEqual(
			frappe.db.get_value("Stock Entry Type", commodities.LOSS_TYPE, "ke_counts_as_loss"), 1
		)

	def test_classify(self):
		c = commodities.classify
		self.assertEqual(c("Stock Reconciliation", "x", 4), ("adjust_plus", 4))
		self.assertEqual(c("Stock Reconciliation", "x", -3), ("adjust_minus", 3))
		self.assertEqual(c("Purchase Receipt", "x", 50), ("received", 50))
		self.assertEqual(c("Delivery Note", "x", -5), ("dispensed", 5))
		self.assertEqual(c("Delivery Note", "x", 2), ("dispensed", -2))  # a return
		commodities._entry_info.update(
			{"loss": ("Material Issue", 1), "ward": ("Material Issue", 0), "in": ("Material Transfer", 0)}
		)
		self.assertEqual(c("Stock Entry", "loss", -6), ("losses", 6))
		self.assertEqual(c("Stock Entry", "ward", -6), ("dispensed", 6))
		self.assertEqual(c("Stock Entry", "in", 10), ("received", 10))
		self.assertEqual(c("Stock Entry", "in", -10), ("adjust_minus", 10))

	def test_columns_add_up_to_the_stock_balance(self):
		item = frappe.db.get_value("Bin", {"actual_qty": [">", 0]}, "item_code", order_by="modified desc")
		if not item:
			self.skipTest("needs an item in stock")
		stores = commodities.warehouses(self.company)
		start = get_first_day(nowdate())
		f = commodities.item_figures(item, stores, start, nowdate())
		total = (
			f["beginning"]
			+ f["received"]
			- f["dispensed"]
			- f["losses"]
			+ f["adjust_plus"]
			- f["adjust_minus"]
		)
		self.assertAlmostEqual(total, f["ending"], places=3)
		on_hand = sum(
			flt(q)
			for q in frappe.get_all(
				"Bin", filters={"item_code": item, "warehouse": ["in", stores]}, pluck="actual_qty"
			)
		)
		self.assertAlmostEqual(f["ending"], on_hand, places=3)

	def test_report_in_the_forms_units(self):
		item = frappe.db.get_value("Bin", {"actual_qty": [">", 0]}, "item_code", order_by="modified desc")
		if not item:
			self.skipTest("needs an item in stock")
		form = frappe.get_doc(
			{
				"doctype": commodities.FORM,
				"form_name": f"TEST {frappe.generate_hash(length=5)}",
				"items": [
					{
						"section": "Pills",
						"commodity": "Mapped",
						"unit": "Pack of 10",
						"item": item,
						"units_per_issue": 10,
					},
					{"section": "Pills", "commodity": "Not stocked", "unit": "Piece"},
				],
			}
		).insert(ignore_permissions=True)
		rows = commodities.report(form.name, get_first_day(nowdate()), nowdate(), self.company)
		self.assertEqual(rows[0], {"commodity": "Pills", "is_section": 1, "indent": 0})
		stores = commodities.warehouses(self.company)
		f = commodities.item_figures(item, stores, get_first_day(nowdate()), nowdate())
		self.assertAlmostEqual(rows[1]["ending"], flt(f["ending"] / 10, 2), places=2)
		self.assertTrue(rows[2]["not_mapped"])


class TestFridgeLog(IntegrationTestCase):
	def setUp(self):
		self.fridge = f"Test Fridge {frappe.generate_hash(length=5)}"
		frappe.get_doc({"doctype": "Cold Chain Fridge", "fridge_name": self.fridge}).insert(
			ignore_permissions=True
		)

	def reading(self, session, temp, action=None, day=None):
		return frappe.get_doc(
			{
				"doctype": cold_chain.READING,
				"fridge": self.fridge,
				"reading_date": day or nowdate(),
				"session": session,
				"temperature": temp,
				"action_taken": action,
			}
		).insert(ignore_permissions=True)

	def test_out_of_range_needs_an_action(self):
		ok = self.reading("Morning", 5)
		self.assertFalse(ok.out_of_range)
		with self.assertRaisesRegex(frappe.ValidationError, "action taken"):
			self.reading("Evening", 9.5)
		warm = self.reading("Evening", 9.5, "Door left open; closed, rechecked in 30 min")
		self.assertEqual(warm.out_of_range, "Too warm")
		with self.assertRaisesRegex(frappe.ValidationError, "already recorded"):
			self.reading("Morning", 4)
		cold = self.reading("Morning", 1, "Thermostat turned up", day=add_days(nowdate(), -1))
		self.assertEqual(cold.out_of_range, "Too cold")

	def test_monthly_sheet(self):
		self.reading("Morning", 4.5)
		self.reading("Evening", 6)
		rows = cold_chain.sheet(self.fridge, add_days(nowdate(), -2), nowdate())
		self.assertEqual(len(rows), 3)
		today = rows[-1]
		self.assertEqual((today["am_temp"], today["pm_temp"]), (4.5, 6))
		self.assertNotIn("am_temp", rows[0])  # a day with no reading


class TestImmunisation(IntegrationTestCase):
	def setUp(self):
		immunisation.seed()

	def test_schedule_and_record(self):
		child = _patient(age_days=120)  # about 4 months
		rows = {r["dose"]: r for r in immunisation.schedule(child)["rows"]}
		self.assertEqual(rows["BCG"]["status"], "Overdue")
		self.assertEqual(rows["Measles-Rubella 1"]["status"], "Not yet due")
		self.assertNotIn("HPV 1", rows)
		immunisation.record(child, "BCG", given_on=add_days(nowdate(), -110))
		self.assertEqual(
			{r["dose"]: r for r in immunisation.schedule(child)["rows"]}["BCG"]["status"], "Given"
		)
		with self.assertRaisesRegex(frappe.ValidationError, "already recorded"):
			immunisation.record(child, "BCG")
		with self.assertRaisesRegex(frappe.ValidationError, "future"):
			immunisation.record(child, "OPV 1", given_on=add_days(nowdate(), 1))
		boy = _patient(sex="Male", age_days=11 * 365)
		with self.assertRaisesRegex(frappe.ValidationError, "women and girls"):
			immunisation.record(boy, "HPV 1")

	def test_moh710_counts_and_fully_immunised(self):
		child = _patient(age_days=300)
		dob = getdate(add_days(nowdate(), -300))
		needed = frappe.get_all(
			immunisation.DOSE,
			filters={"disabled": 0, "counts_for_fic": 1},
			fields=["name", "due_age_days"],
			order_by="sequence",
		)
		for d in needed:
			# the earlier doses from the child's card, the last one given here today
			last = d.name == needed[-1].name
			immunisation.record(
				child,
				d.name,
				given_on=nowdate() if last else str(add_days(dob, d.due_age_days or 0)),
				given_here=1 if last else 0,
			)
		rows = {r["indicator"]: r for r in immunisation.moh710(nowdate(), nowdate())}
		self.assertGreaterEqual(rows[needed[-1].name]["under_1"], 1)
		self.assertGreaterEqual(immunisation.fully_immunised(nowdate(), nowdate()), 1)
		self.assertGreaterEqual(rows["Fully Immunised Child (under 1 year)"]["under_1"], 1)
