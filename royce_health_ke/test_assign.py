# Copyright (c) 2026, Royce Technologies LTD and Contributors
# See license.txt

"""The next consultant: doctors on duty share the patients evenly."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_to_date, today

from royce_health_ke import assign, visits

DAYS = ("Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday")


class IntegrationTestAssign(IntegrationTestCase):
	def setUp(self):
		self.company = frappe.db.get_value("Company", {}, "name")
		self.rooms = frappe.get_all(
			"Healthcare Service Unit",
			filters={"is_group": 0, "company": self.company},
			pluck="name",
			order_by="name",
			limit=2,
		)
		if len(self.rooms) < 2:
			self.skipTest("needs two service units (load the demo)")
		# a clinic of its own per test: the class rolls back only at the end
		tag = frappe.generate_hash(length=5)
		self.department = (
			frappe.get_doc({"doctype": "Medical Department", "department": f"Assign Test {tag}"})
			.insert(ignore_permissions=True)
			.name
		)
		self.doctors = [
			self.doctor(f"Assign {tag} {letter}", room) for letter, room in zip("AB", self.rooms, strict=True)
		]

	def doctor(self, name, room):
		schedule = f"{name} all week"
		if not frappe.db.exists("Practitioner Schedule", schedule):
			frappe.get_doc(
				{
					"doctype": "Practitioner Schedule",
					"schedule_name": schedule,
					"time_slots": [
						{"day": day, "from_time": "00:00:00", "to_time": "23:59:59", "duration": 15}
						for day in DAYS
					],
				}
			).insert(ignore_permissions=True)
		return (
			frappe.get_doc(
				{
					"doctype": "Healthcare Practitioner",
					"first_name": name,
					"status": "Active",
					"department": self.department,
					"practitioner_schedules": [{"schedule": schedule, "service_unit": room}],
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

	def visit(self, department=None, facility=None):
		patient = frappe.get_doc(
			{
				"doctype": "Patient",
				"first_name": "Queue",
				"last_name": f"Test {frappe.generate_hash(length=6)}",
				"sex": "Female",
				"dob": add_to_date(today(), years=-40),
			}
		).insert(ignore_permissions=True)
		return frappe.get_doc(
			{
				"doctype": "Patient Visit",
				"patient": patient.name,
				"company": self.company,
				"visit_type": "Lab only",  # no service type needed; starts at the lab
				"department": department or self.department,
				"facility": facility,
			}
		).insert(ignore_permissions=True)

	def send(self, v, practitioner=None):
		visits.send_to(v.name, "Consultation", practitioner=practitioner)
		return frappe.get_doc("Patient Visit", v.name)

	def test_patients_are_shared_evenly_with_the_room(self):
		first, second, third = (self.send(self.visit()) for _ in range(3))
		a, b = self.doctors
		self.assertEqual([first.practitioner, second.practitioner, third.practitioner], [a, b, a])
		self.assertEqual(first.consultation_room, self.rooms[0])
		self.assertEqual(second.consultation_room, self.rooms[1])
		self.assertEqual(first.movements[-1].service_unit, self.rooms[0])
		self.assertEqual(first.movements[-1].practitioner, a)

		# A finishes with the first patient: A has one waiting, B one, so B is next
		visits.complete(first.name)
		fourth = self.send(self.visit())
		self.assertEqual(fourth.practitioner, b)  # equal load now; B has been sent fewer today

	def test_a_doctor_chosen_by_hand_is_kept(self):
		b = self.doctors[1]
		v = self.send(self.visit(), practitioner=b)
		self.assertEqual(v.practitioner, b)
		self.assertEqual(v.consultation_room, self.rooms[1])

	def test_reassign_keeps_the_place_in_the_queue(self):
		v = self.send(self.visit())
		before, sent_at = v.practitioner, v.sent_at
		visits.reassign(v.name)
		v.reload()
		self.assertNotEqual(v.practitioner, before)
		self.assertEqual(v.sent_at, sent_at)
		self.assertIn("Reassigned", v.movements[-1].note)

	def test_another_department_when_none_of_its_doctors_is_on_duty(self):
		other = frappe.get_doc(
			{"doctype": "Medical Department", "department": f"Assign Empty {frappe.generate_hash(length=5)}"}
		).insert(ignore_permissions=True)
		v = self.send(self.visit(department=other.name))
		self.assertTrue(v.practitioner)  # any doctor on duty, with a message

	def test_only_rooms_of_the_visits_facility(self):
		def facility(unit):
			return (
				frappe.get_doc(
					{
						"doctype": "Health Facility",
						"facility_name": f"Assign Test {frappe.generate_hash(length=5)}",
						"company": self.company,
						"healthcare_service_unit": unit,
					}
				)
				.insert(ignore_permissions=True)
				.name
			)

		parent = frappe.db.get_value(
			"Healthcare Service Unit", self.rooms[0], "parent_healthcare_service_unit"
		)
		empty = frappe.get_doc(
			{
				"doctype": "Healthcare Service Unit",
				"healthcare_service_unit_name": f"Assign Test Wing {frappe.generate_hash(length=5)}",
				"is_group": 1,
				"company": self.company,
				"parent_healthcare_service_unit": parent,
			}
		).insert(ignore_permissions=True)
		self.assertEqual(assign.on_duty(self.company, facility(empty.name), self.department), [])
		with self.assertRaisesRegex(frappe.ValidationError, "Choose the doctor"):
			self.send(self.visit(facility=facility(empty.name)))

		on_duty = {c.practitioner for c in assign.on_duty(self.company, facility(parent), self.department)}
		self.assertIn(self.doctors[0], on_duty)  # its room is in the facility's group

	def test_queue_slip(self):
		first = self.send(self.visit())
		second = self.send(self.visit())
		third = self.send(self.visit())  # same doctor as the first, one patient ahead
		self.assertEqual(third.practitioner, first.practitioner)
		self.assertEqual(assign.ahead_of(third), 1)
		self.assertEqual(assign.ahead_of(second), 0)
		html = frappe.get_print("Patient Visit", third.name, "Queue Slip")
		self.assertIn(third.practitioner_name, html)
		self.assertIn("Patients ahead of you", html)

	def test_night_shift_past_midnight(self):
		self.assertTrue(
			assign._covers(frappe.utils.get_time("22:00:00"), frappe.utils.get_time("06:00:00"), 3600)
		)
		self.assertFalse(
			assign._covers(frappe.utils.get_time("22:00:00"), frappe.utils.get_time("06:00:00"), 12 * 3600)
		)
