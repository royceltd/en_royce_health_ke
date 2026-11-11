# Copyright (c) 2026, Royce Technologies LTD and Contributors
# See license.txt

"""Theatre continuation notes and the post-operative treatment sheet."""

from datetime import datetime

import frappe
from frappe.tests import IntegrationTestCase

from royce_health_ke import postop, theatre


class IntegrationTestPostOp(IntegrationTestCase):
	def setUp(self):
		self.booking = frappe.db.get_value(
			"Theatre Booking",
			{"inpatient_record": ["is", "set"], "status": ["in", ["In Theatre", "Completed"]]},
			["name", "inpatient_record", "surgeon"],
			as_dict=True,
		)
		if (
			not self.booking
			or frappe.db.get_value("Inpatient Record", self.booking.inpatient_record, "status") != "Admitted"
		):
			self.skipTest("needs the demo theatre patient (admitted, operated)")
		self.drug = frappe.db.get_value("Medication Linked Item", {}, "item")
		if not self.drug:
			self.skipTest("needs a drug linked to a Medication")
		frappe.db.set_value("Theatre Booking", self.booking.name, "treatment_sheet", None)

	def test_dose_times(self):
		row = frappe._dict(every_hours=8, duration_days=2, first_dose_at=datetime(2026, 11, 11, 14, 30, 45))
		times = postop.dose_times(row, None)
		self.assertEqual(len(times), 6)
		self.assertEqual((times[0].hour, times[0].minute, times[0].second), (14, 30, 0))
		self.assertEqual(times[-1], datetime(2026, 11, 13, 6, 30))
		self.assertEqual(postop.dose_times(frappe._dict(prn=1, every_hours=6), None), [])

	def test_progress_notes_are_kept_as_written(self):
		theatre.add_note(self.booking.name, "Extubated, stable.", "Recovery")
		doc = frappe.get_doc("Theatre Booking", self.booking.name)
		note = doc.progress_notes[-1]
		self.assertEqual((note.stage, note.recorded_by), ("Recovery", frappe.session.user))
		self.assertTrue(note.noted_at)
		note.note = "changed"
		with self.assertRaises(frappe.ValidationError):
			doc.save()
		doc.reload()
		doc.progress_notes = doc.progress_notes[:-1]
		with self.assertRaises(frappe.ValidationError):
			doc.save()

	def sheet(self, **values):
		return frappe.get_doc(
			{
				"doctype": "Treatment Sheet",
				"theatre_booking": self.booking.name,
				"practitioner": self.booking.surgeon,
				"drugs": [
					{
						"drug": self.drug,
						"dose": "500 mg",
						"route": "PO",
						"every_hours": 8,
						"duration_days": 1,
					},
					{"drug": self.drug, "dose": "1 g", "route": "PO", "prn": 1},
				],
				"once_only": [{"drug": self.drug, "dose": "1 g", "qty_per_dose": 2, "route": "IV"}],
				**values,
			}
		).insert(ignore_permissions=True)

	def test_sheet_schedules_the_ward_doses(self):
		sheet = self.sheet()
		self.assertEqual(sheet.inpatient_record, self.booking.inpatient_record)  # from the booking
		self.assertTrue(sheet.drugs[0].dosage_form)  # from the drug's Medication
		self.assertEqual(
			frappe.db.get_value("Theatre Booking", self.booking.name, "treatment_sheet"), sheet.name
		)
		sheet.submit()
		order = frappe.get_doc("Inpatient Medication Order", sheet.medication_order)
		self.assertEqual(order.docstatus, 1)
		self.assertEqual(
			len(order.medication_orders), 4
		)  # 3 regular (every 8 h, 1 day) + 1 once; PRN not scheduled
		once = [e for e in order.medication_orders if e.dosage == 2]
		self.assertEqual(len(once), 1)
		self.assertIn("1 g IV", once[0].instructions)

		sheet.cancel()
		self.assertEqual(frappe.db.get_value("Inpatient Medication Order", order.name, "docstatus"), 2)

	def test_cancel_refused_once_the_ward_has_given_a_dose(self):
		sheet = self.sheet()
		sheet.submit()
		entry = frappe.db.get_value(
			"Inpatient Medication Order Entry", {"parent": sheet.medication_order}, "name"
		)
		frappe.db.set_value("Inpatient Medication Order Entry", entry, "status", "Completed")
		with self.assertRaises(frappe.ValidationError):
			sheet.cancel()

	def test_regular_drug_needs_an_interval(self):
		with self.assertRaises(frappe.ValidationError):
			self.sheet(drugs=[{"drug": self.drug, "dose": "500 mg", "route": "PO"}])

	def test_prints(self):
		theatre.add_note(self.booking.name, "Wound dry, handed over.", "Back to ward")
		html = frappe.get_print("Theatre Booking", self.booking.name, "Continuation Sheet")
		self.assertIn("Wound dry, handed over.", html)
		sheet = self.sheet()
		html = frappe.get_print("Treatment Sheet", sheet.name, "Treatment Sheet")
		self.assertIn("Every 8 h", html)
		self.assertIn("X Taken", html)
