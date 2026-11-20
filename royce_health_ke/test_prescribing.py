# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""The Order Drug panel (prescribing.py): drafts are held back, Submit sends,
Buy Externally and Chronic reach the Medication Request, the lists."""

import json

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from royce_health_ke import consultation, inpatient, pharmacy, prescribing
from royce_health_ke.test_consultation import ConsultationCase
from royce_health_ke.test_inpatient import InpatientCase


def _mrs(encounter):
	return frappe.get_all(
		"Medication Request",
		filters={"order_group": encounter, "docstatus": 1},
		fields=["name", "ke_pharmacy_status", "ke_chronic", "medication_item"],
	)


class TestOrderDrug(ConsultationCase):
	def _draft(self, enc, **extra):
		row = {
			"drug_code": "DRG-PCM500",
			"medication": self.medication,
			"dosage": self.dosage,
			"period": self.period,
			"ke_dose": 1,
			"ke_route": "Oral",
			"ke_draft": 1,
			**extra,
		}
		enc.append("drug_prescription", row)
		enc.save()
		return enc

	def test_draft_is_held_back_and_submit_sends_it(self):
		enc = self._draft(self.encounter(lab=False))
		# even when saving places the orders, a draft is not sent
		enc.submit_orders_on_save = 1
		enc.save()
		self.assertEqual(_mrs(enc.name), [])
		self.assertEqual(consultation.new_drugs(enc), [])
		self.assertEqual(prescribing.submit(enc.name), {"sent": 1})
		enc.reload()
		row = enc.drug_prescription[0]
		self.assertFalse(row.ke_draft)
		self.assertTrue(row.medication_request)
		self.assertEqual(len(_mrs(enc.name)), 1)
		with self.assertRaisesRegex(frappe.ValidationError, "No drugs to send"):
			prescribing.submit(enc.name)

	def test_buy_externally_and_chronic_reach_the_order(self):
		enc = self._draft(self.encounter(lab=False), ke_buy_externally=1, ke_chronic=1)
		prescribing.submit(enc.name)
		(mr,) = _mrs(enc.name)
		self.assertEqual(mr.ke_pharmacy_status, pharmacy.BUY_OUTSIDE)
		self.assertEqual(mr.ke_chronic, 1)

	def test_completing_with_a_draft_is_refused(self):
		enc = self._draft(self.encounter(lab=False))
		with self.assertRaisesRegex(frappe.ValidationError, "still in draft"):
			consultation.complete(enc.name)
		prescribing.submit(enc.name)
		consultation.complete(enc.name)
		self.assertEqual(frappe.db.get_value("Patient Encounter", enc.name, "docstatus"), 1)

	def test_lists(self):
		first = self._draft(self.encounter(lab=False), ke_chronic=1)
		prescribing.submit(first.name)
		second = self._draft(self.encounter(lab=False))
		prescribing.submit(second.name)
		lists = prescribing.history(second.name)
		self.assertEqual([m["encounter"] for m in lists["sent"]], [second.name])
		self.assertIn(first.name, [m["encounter"] for m in lists["active"]])
		self.assertEqual([m["encounter"] for m in lists["chronic"]], [first.name])
		self.assertEqual(lists["chronic"][0]["drug_code"], "DRG-PCM500")
		# a course that ended is Past
		mr = frappe.db.get_value("Medication Request", {"order_group": first.name}, "name")
		frappe.db.set_value(
			"Medication Request", mr, {"order_date": add_days(today(), -60), "ke_start": None}
		)
		lists = prescribing.history(second.name)
		self.assertIn(first.name, [m["encounter"] for m in lists["past"]])
		self.assertNotIn(first.name, [m["encounter"] for m in lists["active"]])
		# still a chronic medicine
		self.assertEqual([m["encounter"] for m in lists["chronic"]], [first.name])


class TestOrderDrugLookups(IntegrationTestCase):
	def test_duration_found_or_made(self):
		name = prescribing.duration(17, "Day")
		self.assertEqual(
			frappe.db.get_value("Prescription Duration", name, ["number", "period"]), (17, "Day")
		)
		self.assertEqual(prescribing.duration(17, "Day"), name)
		with self.assertRaises(frappe.ValidationError):
			prescribing.duration(3, "Fortnight")
		with self.assertRaises(frappe.ValidationError):
			prescribing.duration(0, "Day")
		frappe.db.rollback()

	def test_drug_search_and_info(self):
		if not frappe.db.exists("Item", "DRG-PCM500"):
			self.skipTest("needs the demo's paracetamol")
		group = frappe.db.get_value("Item", "DRG-PCM500", "item_group")
		if group not in pharmacy.drug_groups():
			self.skipTest("paracetamol is not under the pharmacy's drug group here")
		rows = prescribing.drug_query("Item", "PCM500", "name", 0, 20, {})
		self.assertIn("DRG-PCM500", [r[0] for r in rows])
		self.assertTrue(all("Available" in r[2] for r in rows))
		info = prescribing.drug_info("DRG-PCM500")
		self.assertEqual(info["item_code"], "DRG-PCM500")
		self.assertTrue(info["stock_uom"])

	def test_package_drugs(self):
		if not frappe.db.exists("Item", "DRG-PCM500"):
			self.skipTest("needs the demo's paracetamol")
		name = f"Pain pack {frappe.generate_hash(length=5)}"
		frappe.get_doc(
			{
				"doctype": "Treatment Plan Template",
				"template_name": name,
				"drugs": [{"drug_code": "DRG-PCM500", "ke_dose": 2, "ke_route": "Oral", "ke_chronic": 1}],
			}
		).insert(ignore_permissions=True, ignore_mandatory=True)
		self.assertIn(
			name,
			[r[0] for r in prescribing.package_query("Treatment Plan Template", "Pain", "name", 0, 20, {})],
		)
		(row,) = prescribing.package_drugs(name)
		self.assertEqual((row["drug_code"], row["ke_dose"], row["ke_chronic"]), ("DRG-PCM500", 2, 1))
		frappe.db.rollback()

	def test_panel_on_the_prescription_tab(self):
		order = json.loads(
			frappe.db.get_value(
				"Property Setter", {"doc_type": "Patient Encounter", "property": "field_order"}, "value"
			)
			or "[]"
		)
		if "ke_prescribe_html" not in order:
			self.skipTest("the consultation layout is the hospital's own here")
		self.assertEqual(order.index("ke_prescribe_html"), order.index("ke_pharmacy_html") + 1)
		self.assertLess(order.index("ke_tab_prescription"), order.index("ke_prescribe_html"))
		self.assertLess(order.index("ke_prescribe_html"), order.index("ke_tab_complete"))


class TestDrugScreen(ConsultationCase):
	"""The drug screen to Bethesda's design (v0.52): add, remove, preview, save."""

	def row(self, **extra):
		return {
			"drug_code": "DRG-PCM500",
			"ke_dose": 1,
			"dosage": self.dosage,
			"period": self.period,
			"ke_route": "Oral",
			"ke_start_time": "08:00:00",
			**extra,
		}

	def test_add_remove_and_save(self):
		enc = self.encounter(lab=False)
		r = prescribing.add_drug(enc.name, self.row())
		self.assertEqual(len(r["pending"]), 1)
		self.assertTrue(r["pending"][0]["draft"])
		self.assertIn("will be dispensed as", r["mapping"]["text"])
		self.assertEqual(r["pending"][0]["quantity"], r["mapping"]["quantity"])
		# a package (a list) adds every drug
		r = prescribing.add_drug(enc.name, [self.row(ke_quantity=5), self.row(ke_chronic=1)])
		self.assertEqual(len(r["pending"]), 3)
		self.assertEqual(r["pending"][1]["quantity"], 5)  # the doctor's quantity is kept
		r = prescribing.remove_drug(enc.name, r["pending"][0]["name"])
		self.assertEqual(len(r["pending"]), 2)
		self.assertEqual(_mrs(enc.name), [])
		self.assertEqual(prescribing.save_prescription(enc.name), {"sent": 2})
		lists = prescribing.current(enc.name)
		self.assertEqual((len(lists["pending"]), len(lists["sent"])), (0, 2))
		with self.assertRaisesRegex(frappe.ValidationError, "Only a drug not sent"):
			prescribing.remove_drug(
				enc.name, frappe.get_doc("Patient Encounter", enc.name).drug_prescription[0].name
			)

	def test_preview(self):
		r = prescribing.preview(self.row())
		self.assertTrue(r["quantity"] >= 1)
		self.assertTrue(r["text"].endswith("."))
		self.assertIsNone(prescribing.preview(self.row(dosage=None)))


class TestWardDrugScreen(InpatientCase):
	def test_ward_prescription_makes_the_dose_schedule(self):
		ip, _bed = self.admitted()
		lists = prescribing.ward_lists(ip)
		self.assertEqual((lists["encounter"], lists["pending"]), (None, []))
		enc = prescribing.ward_encounter(ip)
		self.assertEqual(prescribing.ward_encounter(ip), enc)  # the same open ward round
		prescribing.add_drug(
			enc,
			{
				"drug_code": "DRG-PCM500",
				"ke_dose": 1,
				"dosage_by_interval": 1,
				"interval": 8,
				"interval_uom": "Hour",
				"period": prescribing.duration(2, "Day"),
				"ke_route": "Oral",
				"ke_start_date": today(),
				"ke_start_time": "14:00:00",
			},
		)
		self.assertEqual(len(prescribing.ward_lists(ip)["pending"]), 1)
		self.assertEqual(prescribing.save_prescription(enc), {"sent": 1, "completed": 1})
		self.assertEqual(frappe.db.get_value("Patient Encounter", enc, "docstatus"), 1)
		# billed with the admission, not linked to the outpatient visit on any save
		self.assertFalse(frappe.db.get_value("Patient Encounter", enc, "ke_patient_visit"))
		order = frappe.get_doc("Inpatient Medication Order", {"patient_encounter": enc})
		times = [(str(e.date), str(e.time)) for e in order.medication_orders]
		# every 8 hours from 14:00: today 14:00 and 22:00, tomorrow 06:00, 14:00, 22:00
		self.assertEqual([t for _d, t in times], ["14:00:00", "22:00:00", "6:00:00", "14:00:00", "22:00:00"])
		lists = prescribing.ward_lists(ip)
		self.assertIsNone(lists["encounter"])
		self.assertEqual(len(lists["sent"]), 1)

	def test_row_times(self):
		row = frappe._dict(dosage_by_interval=1, interval=6, interval_uom="Hour", ke_start_time=None)
		self.assertEqual(inpatient.row_times(row), ["00:00:00", "06:00:00", "12:00:00", "18:00:00"])
		row.interval, row.interval_uom = 1, "Day"
		self.assertEqual(inpatient.row_times(row), ["06:00:00"])
