# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""The patient's way through the hospital (Bethesda, 20 Nov 2026: "OPD to
Admission to Ward to theatre or Maternity ... we send patient and get as a
request in the next tab/module"): theatre requests and ward transfers."""

import frappe
from frappe.utils import add_to_date, now_datetime

from royce_health_ke import flow, inpatient, routing, theatre
from royce_health_ke.test_inpatient import InpatientCase


def _surgical_template():
	routing.add_theatre()
	name = frappe.db.get_value("Clinical Procedure Template", {}, "name")
	if name:
		frappe.db.set_value("Clinical Procedure Template", name, "item_group", routing.SURGICAL_GROUP)
		routing.clear_cache()
	return name


def _theatre():
	types = frappe.get_all("Healthcare Service Unit Type", filters={"is_ot": 1}, pluck="name")
	return frappe.db.get_value(
		"Healthcare Service Unit", {"service_unit_type": ["in", types or [""]], "is_group": 0}, "name"
	)


class TestTheatreRequests(InpatientCase):
	def test_ward_request_reaches_theatre_and_is_booked(self):
		template = _surgical_template()
		place = _theatre()
		if not (template and place):
			self.skipTest("needs a procedure template and an operating theatre")
		self.assertEqual(
			routing.category_for("Clinical Procedure Template", template), ("Theatre", "Theatre")
		)
		self.assertIn("Theatre", flow.STATIONS)

		ip, bed = self.admitted()
		inpatient.add_request(ip, "Theatre", template, urgency="Urgent", note="Acute abdomen")
		row = next(r for r in theatre.theatre_requests() if r.patient == self.patient)
		self.assertEqual((row.template_dn, row.urgency, row.inpatient_record), (template, "Urgent", ip))
		self.assertEqual(row.comment, "Acute abdomen")  # the doctor's note travels with the request
		self.assertIn(bed, row.location)

		booking = frappe.get_doc(
			{
				"doctype": "Theatre Booking",
				"service_request": row.name,
				"company": self.company,
				"theatre": place,
				"surgeon": self.practitioner,
				"scheduled_start": add_to_date(now_datetime(), days=500),
				"duration_minutes": 30,
				"pre_authorisation": "Not required",
			}
		).insert(ignore_permissions=True)
		# filled from the request
		self.assertEqual(
			(booking.patient, booking.procedure_template, booking.inpatient_record),
			(self.patient, template, ip),
		)
		self.assertNotIn(row.name, [r.name for r in theatre.theatre_requests()])
		ward_row = next(r for r in inpatient.admission_list()["on_ward"] if r.name == ip)
		self.assertEqual(ward_row.theatre.status, "Scheduled")

		# a cancelled booking puts the request back on the list
		frappe.db.set_value("Theatre Booking", booking.name, "status", "Cancelled")
		self.assertIn(row.name, [r.name for r in theatre.theatre_requests()])

	def test_request_for_another_patient_is_refused(self):
		template = _surgical_template()
		place = _theatre()
		if not (template and place):
			self.skipTest("needs a procedure template and an operating theatre")
		ip, _bed = self.admitted()
		inpatient.add_request(ip, "Theatre", template)
		row = next(r for r in theatre.theatre_requests() if r.patient == self.patient)
		other = frappe.db.get_value("Patient", {"name": ["!=", self.patient]}, "name")
		with self.assertRaisesRegex(frappe.ValidationError, "another patient"):
			frappe.get_doc(
				{
					"doctype": "Theatre Booking",
					"service_request": row.name,
					"patient": other,
					"company": self.company,
					"theatre": place,
					"surgeon": self.practitioner,
					"scheduled_start": add_to_date(now_datetime(), days=501),
					"duration_minutes": 30,
				}
			).insert(ignore_permissions=True)


class TestWardTransfer(InpatientCase):
	def other_ward(self):
		for ward in inpatient.wards():
			if ward != self.ward and inpatient.vacant_beds(ward):
				return ward
		self.skipTest("needs a second ward with a vacant bed (the demo's Maternity Ward)")

	def test_transfer_asked_then_received(self):
		to = self.other_ward()
		ip, old_bed = self.admitted()
		with self.assertRaisesRegex(frappe.ValidationError, "already on"):
			inpatient.request_transfer(ip, self.ward, "No reason")
		inpatient.request_transfer(ip, to, "In labour", "Urgent")

		lists = inpatient.admission_list(to)
		self.assertIn(ip, [r.name for r in lists["incoming"]])
		self.assertNotIn(ip, [r.name for r in lists["on_ward"]])
		# still on the old ward until a bed is given
		self.assertIn(ip, [r.name for r in inpatient.admission_list(self.ward)["on_ward"]])
		self.assertEqual(inpatient.workspace(ip)["transfer_to"], to)

		new_bed = inpatient.vacant_beds(to)[0].name
		with self.assertRaisesRegex(frappe.ValidationError, "not a bed on"):
			inpatient.receive_transfer(ip, old_bed)
		inpatient.receive_transfer(ip, new_bed)

		self.assertEqual(inpatient.ward_of(ip), to)
		self.assertEqual(inpatient.current_bed(ip).service_unit, new_bed)
		self.assertEqual(
			frappe.db.get_value("Healthcare Service Unit", old_bed, "occupancy_status"), "Vacant"
		)
		self.assertEqual(
			frappe.db.get_value("Healthcare Service Unit", new_bed, "occupancy_status"), "Occupied"
		)
		left = frappe.get_all(
			"Inpatient Occupancy",
			filters={"parent": ip, "service_unit": old_bed},
			fields=["left", "check_out"],
		)[0]
		self.assertTrue(left.left and left.check_out)
		self.assertFalse(frappe.db.get_value("Inpatient Record", ip, "ke_transfer_to"))
		self.assertNotIn(ip, [r.name for r in inpatient.admission_list(to)["incoming"]])

	def test_transfer_cancelled(self):
		to = self.other_ward()
		ip, _bed = self.admitted()
		inpatient.request_transfer(ip, to, "Wrong ward")
		inpatient.cancel_transfer(ip)
		self.assertNotIn(ip, [r.name for r in inpatient.admission_list(to)["incoming"]])
		with self.assertRaisesRegex(frappe.ValidationError, "No transfer"):
			inpatient.receive_transfer(ip, inpatient.vacant_beds(to)[0].name)


class TestOutpatientToTheatre(InpatientCase):
	def test_consultation_sends_the_patient_to_theatre(self):
		from royce_health_ke import consultation

		template = _surgical_template()
		if not template:
			self.skipTest("needs a procedure template")
		enc = self.encounter(lab=False)
		enc.append("procedure_prescription", {"procedure": template})
		enc.save()
		info = consultation.send_requests(enc.name)
		self.assertIn("Theatre", info["stations"])
		self.assertIn(self.patient, [r.patient for r in theatre.theatre_requests()])
		row = next(r for r in theatre.theatre_requests() if r.patient == self.patient)
		self.assertEqual(row.location, "Outpatient")
		flow.send(frappe.get_doc("Patient Visit", self.visit.name), "Theatre")
		self.assertEqual(frappe.db.get_value("Patient Visit", self.visit.name, "current_station"), "Theatre")
