# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""The pharmacy worklist: billing, paying, dispensing in parts, returns,
buying outside, sending back to the doctor, counter sales and labels."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_to_date, flt, nowdate, today

from royce_health_ke import pharmacy, visit_bill


class TestPharmacy(IntegrationTestCase):
	def setUp(self):
		self.company = frappe.db.get_single_value(
			"Global Defaults", "default_company"
		) or frappe.db.get_value("Company", {}, "name")
		self.practitioner = frappe.db.get_value(
			"Healthcare Practitioner",
			{"status": "Active", "op_consulting_charge_item": ["is", "set"]},
			"name",
		)
		self.appointment_type = frappe.db.get_value("Appointment Type", {}, "name")
		self.medication = frappe.db.get_value("Medication Linked Item", {"item": "DRG-PCM500"}, "parent")
		self.dosage = frappe.db.exists("Prescription Dosage", "1-1-1 (three times daily)")
		self.period = frappe.db.exists("Prescription Duration", "3 Day")
		self.store = frappe.db.get_value(
			"Bin", {"item_code": "DRG-PCM500", "actual_qty": [">", 50]}, "warehouse"
		)
		if not all(
			(self.practitioner, self.appointment_type, self.medication, self.dosage, self.period, self.store)
		):
			self.skipTest(
				"needs the demo's paracetamol with stock, a practitioner and dosages (load the demo)"
			)
		frappe.flags.ke_test_payment_gate = True
		frappe.db.set_single_value("Kenya Health Settings", "pay_before_pharmacy", 1)
		self.patient = (
			frappe.get_doc(
				{
					"doctype": "Patient",
					"first_name": "Pharmacy",
					"last_name": f"Test {frappe.generate_hash(length=6)}",
					"sex": "Male",
					"dob": add_to_date(today(), years=-40),
				}
			)
			.insert(ignore_permissions=True)
			.name
		)
		self.visit = frappe.get_doc(
			{
				"doctype": "Patient Visit",
				"patient": self.patient,
				"company": self.company,
				"visit_type": "Outpatient",
				"appointment_type": self.appointment_type,
				"practitioner": self.practitioner,
			}
		).insert(ignore_permissions=True)

	def tearDown(self):
		frappe.flags.ke_test_payment_gate = False

	def prescribe(self):
		encounter = frappe.get_doc(
			{
				"doctype": "Patient Encounter",
				"patient": self.patient,
				"practitioner": self.practitioner,
				"encounter_date": today(),
				"company": self.company,
				"drug_prescription": [
					{
						"medication": self.medication,
						"drug_code": "DRG-PCM500",
						"dosage": self.dosage,
						"period": self.period,
						"dosage_form": frappe.db.get_value("Dosage Form", {}, "name"),
					}
				],
			}
		).insert(ignore_permissions=True)
		encounter.submit()
		mr = frappe.db.get_value("Medication Request", {"order_group": encounter.name}, "name")
		# the quantity depends on each site's dosage set-up: fix it for the test
		frappe.db.set_value("Medication Request", mr, {"quantity": 9, "total_dispensable_quantity": 9})
		return frappe._dict(name=mr, quantity=9)

	def line(self, ref, key=None):
		order = pharmacy.order(key or f"visit:{self.visit.name}", today(), today(), self.store)
		return next(x for x in order["lines"] if x["ref"] == ref)

	def pay(self, invoice):
		from royce_health_ke.demo.journey import _pay

		si = frappe.get_doc("Sales Invoice", invoice)
		if si.docstatus == 0:
			si.submit()
		_pay(si, f"TEST-{frappe.generate_hash(length=5)}")

	def test_bill_pay_dispense_in_parts_and_return(self):
		mr = self.prescribe()
		self.assertGreater(mr.quantity, 2)
		line = self.line(mr.name)
		self.assertEqual((line["stage"], line["pay"], line["blocked"]), ("Waiting", "not_billed", True))
		self.assertGreater(line["available"], 0)

		with self.assertRaisesRegex(frappe.ValidationError, "only when paid"):
			pharmacy.dispense([{"kind": "mr", "ref": mr.name, "qty": 1}], self.store)

		invoice = pharmacy.bill_drugs(self.visit.name)
		self.assertIn(
			mr.name, frappe.get_all("Sales Invoice Item", filters={"parent": invoice}, pluck="reference_dn")
		)
		self.assertEqual(self.line(mr.name)["pay"], "billed")
		self.pay(invoice)
		self.assertEqual(self.line(mr.name)["pay"], "paid")

		# Part now (the store is short), the rest later.
		before = flt(
			frappe.db.get_value("Bin", {"item_code": "DRG-PCM500", "warehouse": self.store}, "actual_qty")
		)
		notes = pharmacy.dispense(
			[{"kind": "mr", "ref": mr.name, "qty": 2, "instructions": "Take after food"}], self.store
		)
		dn = frappe.get_doc("Delivery Note", notes[0])
		self.assertEqual((dn.ke_patient, dn.ke_patient_visit), (self.patient, self.visit.name))
		self.assertEqual(dn.items[0].against_sales_invoice, invoice)
		self.assertEqual(dn.items[0].ke_instructions, "Take after food")
		after = flt(
			frappe.db.get_value("Bin", {"item_code": "DRG-PCM500", "warehouse": self.store}, "actual_qty")
		)
		self.assertEqual(before - after, 2)
		self.assertEqual(
			frappe.db.get_value("Medication Request", mr.name, ["ke_dispensed_qty", "ke_pharmacy_status"]),
			(2, "Partly Dispensed"),
		)
		with self.assertRaisesRegex(frappe.ValidationError, "left to dispense"):
			pharmacy.dispense([{"kind": "mr", "ref": mr.name, "qty": mr.quantity}], self.store)

		pharmacy.dispense([{"kind": "mr", "ref": mr.name, "qty": mr.quantity - 2}], self.store)
		self.assertEqual(
			frappe.db.get_value("Medication Request", mr.name, "ke_pharmacy_status"), "Dispensed"
		)
		self.assertEqual(self.line(mr.name)["stage"], "Dispensed")

		labels = pharmacy.health_medicine_labels(dn)
		self.assertEqual(labels[0].instructions, "Take after food")

		# The patient brings one back.
		pharmacy.return_lines([{"kind": "mr", "ref": mr.name, "qty": 1}])
		self.assertEqual(
			frappe.db.get_value("Medication Request", mr.name, ["ke_dispensed_qty", "ke_pharmacy_status"]),
			(mr.quantity - 1, "Partly Dispensed"),
		)
		with self.assertRaisesRegex(frappe.ValidationError, "More is being returned"):
			pharmacy.return_lines([{"kind": "mr", "ref": mr.name, "qty": mr.quantity}])

	def test_buy_outside_and_send_back(self):
		mr = self.prescribe()
		pharmacy.buy_outside([mr.name], "Out of stock")
		self.assertEqual(self.line(mr.name)["stage"], "Buy Outside")
		self.assertNotIn(mr.name, [x["dn"] for x in visit_bill.unbilled_lines(self.visit)])
		with self.assertRaises(frappe.ValidationError):
			pharmacy.bill_drugs(self.visit.name)  # nothing left to bill

		pharmacy.back_to_waiting([mr.name])
		self.assertEqual(self.line(mr.name)["stage"], "Waiting")

		pharmacy.send_back([mr.name], "Patient allergic, please change")
		self.assertEqual(self.line(mr.name)["stage"], "Sent Back")
		visit = frappe.get_doc("Patient Visit", self.visit.name)
		self.assertEqual((visit.current_station, visit.queue_status), ("Consultation", "Waiting"))
		self.assertIn("Patient allergic", visit.movements[-1].note)

		pharmacy.back_to_waiting([mr.name])
		pharmacy.bill_drugs(self.visit.name)
		with self.assertRaisesRegex(frappe.ValidationError, "already on a bill"):
			pharmacy.buy_outside([mr.name])

	def test_counter_sale_for_a_walk_in(self):
		made = pharmacy.counter_sale(
			[{"item_code": "DRG-PCM500", "qty": 10, "instructions": "2 tablets when needed"}],
			walk_in_name="Walk-in Test",
			company=self.company,
		)
		si = frappe.get_doc("Sales Invoice", made["invoice"])
		self.assertEqual(
			(si.docstatus, si.ke_pharmacy_sale, si.customer), (0, 1, pharmacy.walk_in_customer())
		)
		self.assertEqual(made["key"], f"sale:{si.name}")
		line = self.line(si.items[0].name, made["key"])
		self.assertEqual((line["pay"], line["blocked"]), ("draft", True))
		with self.assertRaisesRegex(frappe.ValidationError, "not submitted"):
			pharmacy.dispense([{"kind": "sale", "ref": si.items[0].name, "qty": 10}], self.store)

		self.pay(si.name)
		notes = pharmacy.dispense([{"kind": "sale", "ref": si.items[0].name, "qty": 10}], self.store)
		dn = frappe.get_doc("Delivery Note", notes[0])
		self.assertEqual(
			(dn.ke_walk_in_name, dn.items[0].ke_instructions), ("Walk-in Test", "2 tablets when needed")
		)
		self.assertEqual(
			flt(frappe.db.get_value("Sales Invoice Item", si.items[0].name, "delivered_qty")), 10
		)
		self.assertEqual(self.line(si.items[0].name, made["key"])["stage"], "Dispensed")
		self.assertEqual(pharmacy.health_medicine_labels(dn)[0].patient, "Walk-in Test")

	def test_counter_sale_for_a_patient_goes_on_their_visit(self):
		made = pharmacy.counter_sale(
			[{"item_code": "DRG-PCM500", "qty": 5}], patient=self.patient, company=self.company
		)
		self.assertEqual(made["key"], f"visit:{self.visit.name}")
		self.assertEqual(
			frappe.db.get_value("Sales Invoice", made["invoice"], "ke_patient_visit"), self.visit.name
		)

	def test_bill_with_update_stock_counts_as_dispensed(self):
		mr = self.prescribe()
		si = frappe.get_doc(visit_bill.make_bill(self.visit.name))
		si.update_stock = 1
		si.set_warehouse = self.store
		for row in si.items:
			row.warehouse = self.store
		si.is_pos = 0
		si.insert(ignore_permissions=True)
		frappe.flags.ke_test_payment_gate = False  # paid on the spot is the cashier's business here
		si.submit()
		self.assertEqual(
			frappe.db.get_value("Medication Request", mr.name, "ke_pharmacy_status"), "Dispensed"
		)
		self.assertEqual(nowdate(), str(si.posting_date))

	def test_batch_drug_picks_a_batch_by_expiry(self):
		store = frappe.db.get_value("Bin", {"item_code": "DRG-MET500", "actual_qty": [">", 10]}, "warehouse")
		if not (store and frappe.db.get_value("Item", "DRG-MET500", "has_batch_no")):
			self.skipTest("needs the demo's batch-tracked metformin in stock")
		made = pharmacy.counter_sale(
			[{"item_code": "DRG-MET500", "qty": 4}], walk_in_name="Batch Test", company=self.company
		)
		self.pay(made["invoice"])
		item = frappe.db.get_value("Sales Invoice Item", {"parent": made["invoice"]}, "name")
		dn = frappe.get_doc(
			"Delivery Note", pharmacy.dispense([{"kind": "sale", "ref": item, "qty": 4}], store)[0]
		)
		label = pharmacy.health_medicine_labels(dn)[0]
		self.assertTrue(label.batch, "the batch dispensed is on the label")
		self.assertTrue(label.expiry)
