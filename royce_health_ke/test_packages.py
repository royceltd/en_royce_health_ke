# Copyright (c) 2026, Royce Technologies LTD and Contributors
# See license.txt

from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from royce_health_ke import packages

DEMO_INSURER = "Mlima Health Assurance (Demo)"
DEMO_PLAN = "Corporate Gold (Demo)"


def item(code, rate, group="Services"):
	if not frappe.db.exists("Item", code):
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": code,
				"item_name": code,
				"item_group": group,
				"stock_uom": "Nos",
				"is_stock_item": 0,
				"standard_rate": rate,
			}
		).insert(ignore_permissions=True)
	return code


def package(name, kind="Vaginal delivery", payor=None, nights=2, rate=20000):
	frappe.db.delete("Maternity Package Coverage", {"parent": name})
	frappe.db.delete("Maternity Package", {"name": name})
	return frappe.get_doc(
		{
			"doctype": "Maternity Package",
			"package_name": name,
			"delivery_type": kind,
			"insurance_payor": payor,
			"item": item("_TEST-PKG-ITEM", rate),
			"rate": rate,
			"included_nights": nights,
			"covered": [{"item_code": item("_TEST-COVERED", 500)}],
		}
	).insert(ignore_permissions=True)


class IntegrationTestPackages(IntegrationTestCase):
	def setUp(self):
		self.company = frappe.db.get_value("Company", {}, "name")
		if not self.company:
			self.skipTest("no company")
		# packages are matched by type and payor: keep the site's own out of the way
		own = frappe.get_all(
			"Maternity Package", filters={"name": ["not like", "_Test%"], "disabled": 0}, pluck="name"
		)
		for name in own:
			frappe.db.set_value("Maternity Package", name, "disabled", 1)
		self.addCleanup(self.restore, own)

	def restore(self, own):
		for name in own:
			frappe.db.set_value("Maternity Package", name, "disabled", 0)
		# test records go with the class's rollback; never commit here

	def delivery(self, mode="Spontaneous vaginal delivery", package_name=None):
		mother = (
			frappe.get_doc(
				{"doctype": "Patient", "first_name": "Wairimu", "last_name": "PkgTest", "sex": "Female"}
			)
			.insert(ignore_permissions=True)
			.name
		)
		pregnancy = frappe.get_doc(
			{
				"doctype": "Pregnancy Record",
				"patient": mother,
				"company": self.company,
				"lmp": add_days(today(), -275),
			}
		).insert(ignore_permissions=True)
		doc = frappe.get_doc(
			{
				"doctype": "Delivery Record",
				"pregnancy_record": pregnancy.name,
				"delivery_datetime": f"{add_days(today(), -1)} 05:00:00",
				"mode_of_delivery": mode,
				"maternal_condition": "Alive",
				"maternity_package": package_name,
				"babies": [{"sex": "Female", "outcome": "Live birth", "birth_weight_g": 3100}],
			}
		).insert(ignore_permissions=True)
		doc.submit()
		return doc

	def bill(self, patient, lines, ward=None):
		"""A draft invoice; ward = an Inpatient Occupancy name billed as one
		night (the stay that makes it a discharge bill)."""
		customer = frappe.db.get_value("Patient", patient, "customer") or frappe.db.get_value(
			"Customer", {}, "name"
		)
		si = frappe.get_doc(
			{
				"doctype": "Sales Invoice",
				"customer": customer,
				"patient": patient,
				"company": self.company,
				"posting_date": today(),
				"due_date": today(),
				"items": [{"item_code": code, "qty": qty} for code, qty in lines],
			}
		)
		if ward:
			if not frappe.db.exists("Inpatient Occupancy", ward):
				row = frappe.new_doc("Inpatient Occupancy")
				row.update(
					{
						"name": ward,
						"parent": "_TEST-IP",
						"parenttype": "Inpatient Record",
						"parentfield": "inpatient_occupancies",
					}
				)
				row.db_insert()
			si.append(
				"items",
				{
					"item_code": item("_TEST-WARD-NIGHT", 1500),
					"qty": 1,
					"reference_dt": "Inpatient Occupancy",
					"reference_dn": ward,
				},
			)
		si.set_missing_values()
		si.insert(ignore_permissions=True)
		return si

	def test_delivery_type(self):
		self.assertEqual(packages.delivery_type("Caesarean section"), packages.CAESAREAN)
		for mode in ("Spontaneous vaginal delivery", "Assisted vaginal delivery", "Breech delivery"):
			self.assertEqual(packages.delivery_type(mode), packages.VAGINAL)

	def test_package_chosen_by_type_and_insurer(self):
		cash = package("_Test Cash NVD")
		cs = package("_Test Cash CS", kind="Caesarean section")
		self.assertEqual(self.delivery().maternity_package, cash.name)
		self.assertEqual(self.delivery("Caesarean section").maternity_package, cs.name)
		if not frappe.db.exists("Insurance Payor", DEMO_INSURER):
			return
		insured = package("_Test Insurer NVD", payor=DEMO_INSURER)
		with patch.object(packages, "admission_policy", return_value=(DEMO_INSURER, "POL")):
			self.assertEqual(self.delivery().maternity_package, insured.name)

	def test_discharge_bill_gets_the_package_once(self):
		package("_Test Cash NVD", nights=2)
		delivery = self.delivery()
		extra = item("_TEST-NOT-COVERED", 300)
		si = self.bill(delivery.patient, [("_TEST-COVERED", 2), (extra, 1)], ward="_TEST-OCC")
		rows = {r.item_code: r for r in si.items}
		self.assertEqual(rows["_TEST-PKG-ITEM"].amount, 20000)
		self.assertEqual(rows["_TEST-PKG-ITEM"].reference_dn, delivery.name)
		self.assertEqual(rows["_TEST-COVERED"].amount, 0)
		self.assertEqual(rows["_TEST-WARD-NIGHT"].amount, 0)  # one of the 2 included nights
		self.assertIn("Included in _Test Cash NVD", rows["_TEST-COVERED"].description)
		self.assertEqual(rows[extra].amount, 300)
		self.assertEqual(si.grand_total, 20300)
		si.save()  # saving again doesn't add a second package line
		self.assertEqual(sum(1 for r in si.items if r.item_code == "_TEST-PKG-ITEM"), 1)

		frappe.db.set_value("Delivery Record", delivery.name, "invoiced", 1)
		later = self.bill(delivery.patient, [("_TEST-COVERED", 1)], ward="_TEST-OCC")
		self.assertNotIn("_TEST-PKG-ITEM", [r.item_code for r in later.items])
		self.assertEqual(later.grand_total, 2000)

	def test_outpatient_bill_never_gets_the_package(self):
		package("_Test Cash NVD")
		delivery = self.delivery()
		opd = self.bill(delivery.patient, [("_TEST-COVERED", 1)])
		self.assertNotIn("_TEST-PKG-ITEM", [r.item_code for r in opd.items])
		self.assertEqual(opd.grand_total, 500)
		self.assertEqual(frappe.db.get_value("Delivery Record", delivery.name, "invoiced"), 0)
		# the discharge bill afterwards still gets it
		discharge = self.bill(delivery.patient, [], ward="_TEST-OCC")
		self.assertIn("_TEST-PKG-ITEM", [r.item_code for r in discharge.items])

	def test_package_line_added_by_hand(self):
		package("_Test Cash NVD")
		delivery = self.delivery()
		customer = frappe.db.get_value("Customer", {}, "name")
		si = frappe.get_doc(
			{
				"doctype": "Sales Invoice",
				"customer": frappe.db.get_value("Patient", delivery.patient, "customer") or customer,
				"patient": delivery.patient,
				"company": self.company,
				"posting_date": today(),
				"due_date": today(),
				"items": [
					{"item_code": "_TEST-COVERED", "qty": 1},
					{
						"item_code": "_TEST-PKG-ITEM",
						"qty": 1,
						"rate": 99,
						"reference_dt": "Delivery Record",
						"reference_dn": delivery.name,
					},
				],
			}
		)
		si.set_missing_values()
		si.insert(ignore_permissions=True)
		line = next(r for r in si.items if r.item_code == "_TEST-PKG-ITEM")
		self.assertEqual(line.amount, 20000)
		self.assertEqual(si.grand_total, 20000)  # the covered line is included

	def test_ward_nights_of_another_stay_dont_count(self):
		package("_Test Cash NVD")
		delivery = self.delivery()
		delivery.inpatient_record = "_TEST-IP-DELIVERY"  # her delivery admission
		other_stay = frappe._dict(
			items=[{"reference_dt": "Inpatient Occupancy", "reference_dn": "_TEST-OCC"}]
		)
		self.assertFalse(packages.is_discharge_bill(other_stay, delivery))
		own_line = frappe._dict(items=[{"reference_dt": "Delivery Record", "reference_dn": delivery.name}])
		self.assertTrue(packages.is_discharge_bill(own_line, delivery))

	def test_nights_beyond_the_package_are_billed(self):
		pkg = frappe._dict(package_name="P", included_nights=2, covered=[])

		def ward_line(name, nights):
			return frappe.get_doc(
				{
					"doctype": "Sales Invoice Item",
					"reference_dt": "Inpatient Occupancy",
					"reference_dn": name,
					"item_name": "Ward",
					"qty": nights,
					"rate": 1500,
					"price_list_rate": 1500,
				}
			)

		ward, short = ward_line("X", 3), ward_line("Y", 1)
		doc = SimpleNamespace(items=[ward])
		delivery = frappe._dict(inpatient_record=None)
		packages._include_covered(doc, delivery, pkg, None)
		self.assertEqual((ward.qty, ward.rate), (1, 1500))  # 3 nights, 2 included
		doc.items = [short]
		packages._include_covered(doc, delivery, pkg, None)
		self.assertEqual(short.rate, 0)

	def test_insurer_pays_the_package(self):
		if not frappe.db.exists("Insurance Payor Eligibility Plan", DEMO_PLAN):
			self.skipTest("demo insurer not loaded")
		pkg = package("_Test Insurer NVD", payor=DEMO_INSURER)
		frappe.get_doc(
			{
				"doctype": "Item Insurance Eligibility",
				"insurance_plan": DEMO_PLAN,
				"eligibility_for": "Item",
				"item_code": pkg.item,
				"coverage": 100,
				"discount": 0,
				"mode_of_approval": "Automatic",
				"valid_from": add_days(today(), -30),
				"is_active": 1,
			}
		).insert(ignore_permissions=True)
		delivery = self.delivery(package_name=pkg.name)
		frappe.get_doc(
			{
				"doctype": "Patient Insurance Policy",
				"patient": delivery.patient,
				"insurance_payor": DEMO_INSURER,
				"insurance_plan": DEMO_PLAN,
				"policy_number": "PKG-TEST-1",
				"policy_expiry_date": add_days(today(), 300),
			}
		).insert(ignore_permissions=True).submit()
		si = self.bill(delivery.patient, [("_TEST-COVERED", 1)], ward="_TEST-OCC")
		line = next(r for r in si.items if r.item_code == pkg.item)
		self.assertTrue(line.insurance_coverage)
		self.assertEqual(line.insurance_coverage_amount, 20000)
		self.assertEqual(si.total_insurance_coverage_amount, 20000)
		self.assertEqual(
			frappe.db.get_value("Delivery Record", delivery.name, "package_coverage"), line.insurance_coverage
		)
