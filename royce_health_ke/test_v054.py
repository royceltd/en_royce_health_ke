# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""The Partograph on the ward's Nursing Charts (Bethesda's 7-section form,
20 Nov 2026): it writes into Pregnancy Record, Labour Observation, Delivery
Record and Delivery Newborn."""

import frappe
from frappe.utils import add_to_date, now_datetime

from royce_health_ke import inpatient, partograph
from royce_health_ke.test_inpatient import InpatientCase


def _listed(ip):
	return next((c for c in inpatient.panel(ip, "Nursing Care")["charts"] if c["name"] == "Partograph"), None)


class TestPartograph(InpatientCase):
	def test_labour_to_delivery(self):
		ip, _bed = self.admitted()
		self.assertIsNone(_listed(ip)["status"])
		start = add_to_date(now_datetime(), hours=-6).replace(microsecond=0)
		delivery = partograph.record(
			ip,
			{
				"observation_time": str(start),
				# 1. patient information, 2. blood group
				"gravida": 2,
				"parity": "1",
				"previous_cs": "No",
				"membranes_ruptured_hours": 2,
				"blood_group": "O",
				"rhesus": "Positive",
				"haemoglobin": 9.5,
				# 3. labour progression, 4. vital signs
				"cervical_dilatation_cm": 5,
				"descent": "3",
				"fetal_heart_rate": 170,
				"contractions_per_10min": 3,
				"contraction_intensity": "Moderate",
				"liquor": "Clear",
				"drugs_and_fluids": "Ringer's lactate 500 ml",
				"bp_systolic": 120,
				"bp_diastolic": 80,
				"maternal_pulse": 90,
				"induction": "No",
			},
		)
		self.assertEqual(_listed(ip)["status"], "In labour")
		d = frappe.get_doc("Delivery Record", delivery)
		self.assertEqual((d.docstatus, d.inpatient_record, d.onset_of_labour), (0, ip, "Spontaneous"))
		self.assertEqual(str(d.membranes_ruptured_datetime), str(add_to_date(start, hours=-2)))
		self.assertIn("FHR 170", d.labour_observations[0].alert)
		p = frappe.get_doc("Pregnancy Record", d.pregnancy_record)
		self.assertEqual((p.gravida, p.blood_group, p.hb_flag), (2, "O+", "Anaemia"))

		# a second observation is a new row; nothing else is lost
		partograph.record(
			ip, {"observation_time": str(add_to_date(start, hours=4)), "cervical_dilatation_cm": 9}
		)
		got = partograph.get(ip)
		self.assertEqual(len(got["observations"]), 2)
		self.assertEqual((got["values"]["blood_group"], got["values"]["rhesus"]), ("O", "Positive"))
		self.assertEqual(got["values"]["gravida"], 2)

		with self.assertRaisesRegex(frappe.ValidationError, "To complete the delivery"):
			partograph.complete(ip)

		# 5. delivery details, 6. baby, 7. additional notes
		born = add_to_date(start, hours=5)
		partograph.record(
			ip,
			{
				"observation_time": str(born),
				"mode_of_delivery": "Spontaneous vaginal delivery",
				"amtsl": "Yes",
				"uterotonic": "Oxytocin",
				"placenta_complete": "Yes",
				"perineum": "2nd degree tear",
				"perineum_repaired": "Yes",
				"blood_loss_ml": 600,
				"complication": "PPH",
				"mother_pulse": 96,
				"outcome": "Live birth",
				"sex": "Female",
				"birth_weight_g": 3100,
				"length_cm": 49,
				"head_circumference_cm": 34,
				"apgar_1": 8,
				"apgar_5": 9,
				"teo": "Yes",
				"vitamin_k": "Yes",
				"asphyxia": "No",
				"delivery_datetime": str(born),
				"birth_notification_number": "BN-0001",
			},
		)
		d.reload()
		self.assertEqual((d.amtsl, d.pph, d.perineum_repaired, d.duration_of_labour_hours), (1, 1, 1, 5.0))
		self.assertEqual((d.babies[0].length_cm, d.babies[0].teo, d.babies[0].asphyxia), (49, 1, 0))
		self.assertEqual(len(d.labour_observations), 2)  # no labour readings in that save

		self.assertEqual(partograph.complete(ip), delivery)
		self.assertEqual(_listed(ip)["status"], "Delivered")
		self.assertEqual(frappe.db.get_value("Pregnancy Record", d.pregnancy_record, "status"), "Delivered")
		d.reload()
		self.assertTrue(d.babies[0].baby_patient)
		with self.assertRaisesRegex(frappe.ValidationError, "completed"):
			partograph.record(ip, {"cervical_dilatation_cm": 10})

	def test_only_for_women(self):
		ip, _bed = self.admitted()
		frappe.db.set_value("Patient", self.patient, "sex", "Male")
		self.assertIsNone(_listed(ip))
		with self.assertRaisesRegex(frappe.ValidationError, "women"):
			partograph.record(ip, {"cervical_dilatation_cm": 4})


def _theatre():
	types = frappe.get_all("Healthcare Service Unit Type", filters={"is_ot": 1}, pluck="name")
	return frappe.db.get_value(
		"Healthcare Service Unit", {"service_unit_type": ["in", types or [""]], "is_group": 0}, "name"
	)


class TestTheatreScreen(InpatientCase):
	"""Theatre List → the patient's theatre screen (Bethesda, 20 Nov 2026):
	Drug Administration and Theatre Doctor Notes tabs."""

	def booking(self, ip, day=400):
		theatre = _theatre()
		template = frappe.db.get_value("Clinical Procedure Template", {}, "name")
		if not (theatre and template):
			self.skipTest("needs an operating theatre and a procedure template")
		# a free slot, far ahead, so it can't clash with the demo's bookings
		start = add_to_date(now_datetime(), days=day)
		return (
			frappe.get_doc(
				{
					"doctype": "Theatre Booking",
					"patient": self.patient,
					"company": self.company,
					"inpatient_record": ip,
					"procedure_template": template,
					"theatre": theatre,
					"scheduled_start": start,
					"duration_minutes": 30,
					"priority": "Elective",
					"surgeon": self.practitioner,
					"pre_authorisation": "Not required",
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

	def test_theatre_tabs_and_doctor_notes(self):
		from royce_health_ke import theatre

		inpatient.seed()
		ip, _bed = self.admitted()
		booking = self.booking(ip)
		self.assertEqual(theatre.booking_admission(booking), ip)

		ws = inpatient.workspace(ip, booking)
		self.assertEqual(ws["theatre"]["name"], booking)
		panels = [t["panel"] for t in ws["tabs"]]
		self.assertEqual(panels[:2], ["Theatre Doctor Notes", "Drug Administration"])
		self.assertNotIn("Theatre Doctor Notes", [t["panel"] for t in inpatient.workspace(ip)["tabs"]])

		theatre.add_note(
			booking,
			"Laparotomy, appendix removed",
			noted_at=str(now_datetime().replace(microsecond=0)),
			complications="Bleeding from the mesentery, controlled",
			practitioner=self.practitioner,
		)
		notes = inpatient.panel(ip, "Theatre Doctor Notes", booking)["notes"]
		self.assertEqual(notes[0]["complications"], "Bleeding from the mesentery, controlled")
		self.assertTrue(notes[0]["doctor"])
		# a saved note is not changed (a correction is a new note)
		doc = frappe.get_doc("Theatre Booking", booking)
		doc.progress_notes[0].complications = "None"
		with self.assertRaisesRegex(frappe.ValidationError, "can't be changed"):
			doc.save()

		from royce_health_ke.kenya_health.report.theatre_list.theatre_list import execute

		day = frappe.db.get_value("Theatre Booking", booking, "scheduled_start")
		_cols, rows = execute({"date": str(day)[:10]})
		self.assertEqual(next(r for r in rows if r.name == booking).admission, ip)

	def test_booking_of_another_patient_is_refused(self):
		ip, _bed = self.admitted()
		booking = self.booking(ip, day=401)
		frappe.db.set_value(
			"Theatre Booking",
			booking,
			"patient",
			frappe.db.get_value("Patient", {"name": ["!=", self.patient]}, "name"),
		)
		with self.assertRaisesRegex(frappe.ValidationError, "another patient"):
			inpatient.workspace(ip, booking)
