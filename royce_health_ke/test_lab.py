# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""The lab worklist (one row per order), collection, results, validation,
walk-ins and the consultants' results inbox."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_to_date, today

from royce_health_ke import lab, visit_bill


class TestLab(IntegrationTestCase):
	def setUp(self):
		self.company = frappe.db.get_single_value(
			"Global Defaults", "default_company"
		) or frappe.db.get_value("Company", {}, "name")
		self.template = frappe.db.get_value(
			"Lab Test Template",
			{"is_billable": 1, "disabled": 0, "item": ["is", "set"], "lab_test_template_type": "Single"},
			"name",
		)
		self.practitioner = frappe.db.get_value(
			"Healthcare Practitioner",
			{"status": "Active", "op_consulting_charge_item": ["is", "set"]},
			"name",
		)
		self.appointment_type = frappe.db.get_value("Appointment Type", {}, "name")
		if not (self.template and self.practitioner and self.appointment_type):
			self.skipTest("needs a billable lab test, a practitioner and an appointment type (load the demo)")
		frappe.flags.ke_test_payment_gate = True
		frappe.db.set_single_value("Kenya Health Settings", "pay_before_lab", 1)
		frappe.db.set_single_value("Kenya Health Settings", "lab_second_validator", 0)
		frappe.db.set_single_value("Kenya Health Settings", "walk_in_lab_practitioner", None)
		self.patient = self.new_patient()

	def tearDown(self):
		frappe.flags.ke_test_payment_gate = False

	def new_patient(self):
		return (
			frappe.get_doc(
				{
					"doctype": "Patient",
					"first_name": "Lab",
					"last_name": f"Test {frappe.generate_hash(length=6)}",
					"sex": "Female",
					"dob": add_to_date(today(), years=-30),
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

	def check_in(self):
		return frappe.get_doc(
			{
				"doctype": "Patient Visit",
				"patient": self.patient,
				"company": self.company,
				"visit_type": "Outpatient",
				"appointment_type": self.appointment_type,
				"practitioner": self.practitioner,
			}
		).insert(ignore_permissions=True)

	def order(self):
		encounter = frappe.get_doc(
			{
				"doctype": "Patient Encounter",
				"patient": self.patient,
				"practitioner": self.practitioner,
				"encounter_date": today(),
				"company": self.company,
				"lab_test_prescription": [{"lab_test_code": self.template}],
			}
		).insert(ignore_permissions=True)
		encounter.submit()
		return frappe.db.get_value(
			"Service Request", {"order_group": encounter.name, "template_dt": "Lab Test Template"}, "name"
		)

	def row(self, tab, key):
		rows = lab.worklist(tab, today(), today(), self.company)["rows"]
		return next((r for r in rows if r.key == key), None)

	def test_order_through_the_lab(self):
		visit = self.check_in()
		request = self.order()
		key = f"visit:{visit.name}"
		self.assertEqual(frappe.db.get_value("Service Request", request, "ke_patient_visit"), visit.name)

		row = self.row("requests", key)
		self.assertTrue(row, "the order is on the Requests tab, grouped by visit")
		self.assertEqual((row.count, row.unpaid), (1, 1))
		test = lab.order(key, today(), today())["tests"][0]
		self.assertEqual((test["stage"], test["pay"], test["blocked"]), (lab.REQUESTED, "unpaid", True))

		# Not paid: the sample isn't taken.
		result = lab.collect(requests=[request])
		self.assertEqual((result["done"], len(result["refused"])), ([], 1))

		visit_bill.approve_credit(visit.name, "Staff member")
		result = lab.collect(requests=[request])
		self.assertEqual(len(result["done"]), 1)
		lab_test = frappe.get_doc("Lab Test", result["done"][0])
		self.assertTrue(lab_test.ke_sample_collected_at)
		self.assertEqual(lab_test.ke_sample_collected_by, frappe.session.user)
		self.assertEqual(lab_test.ke_patient_visit, visit.name)
		self.assertIsNone(self.row("requests", key))
		self.assertTrue(self.row("entry", key))

		# Results typed on the worklist, then validated.
		sheet = lab.results_sheet([lab_test.name])[0]
		values = {r["name"]: "5.5" for r in sheet["normal"] if not r["heading"]}
		self.assertTrue(values)
		saved = lab.save_results([{"lab_test": lab_test.name, "normal": values}])
		self.assertEqual(saved["saved"], [lab_test.name])
		self.assertEqual(frappe.db.get_value("Lab Test", lab_test.name, "ke_results_by"), frappe.session.user)
		self.assertTrue(self.row("validate", key))

		done = lab.save_results([{"lab_test": lab_test.name, "normal": values}], validate=1)
		self.assertEqual(done["validated"], [lab_test.name])
		lab_test.reload()
		self.assertEqual((lab_test.docstatus, lab_test.user), (1, frappe.session.user))
		self.assertTrue(lab_test.approved_date and lab_test.ke_result_at)
		self.assertTrue(self.row("completed", key))

		# The consultant's inbox: unread until opened.
		inbox = lab.results_inbox(self.practitioner, 1, today(), today())["rows"]
		self.assertIn(lab_test.name, [r.name for r in inbox])
		lab.mark_seen("Lab Test", lab_test.name)
		inbox = lab.results_inbox(self.practitioner, 1, today(), today())["rows"]
		self.assertNotIn(lab_test.name, [r.name for r in inbox])
		self.assertIn(lab_test.name, [r.name for r in lab.results_inbox(None, 0, today(), today())["rows"]])

	def test_missing_result_is_not_validated(self):
		self.check_in()
		frappe.db.set_single_value("Kenya Health Settings", "pay_before_lab", 0)
		request = self.order()
		name = lab.collect(requests=[request])["done"][0]
		result = lab.save_results([{"lab_test": name, "normal": {}}], validate=1)
		self.assertEqual((result["validated"], len(result["errors"])), ([], 1))
		self.assertEqual(frappe.db.get_value("Lab Test", name, "docstatus"), 0)

	def test_second_person_validates(self):
		self.check_in()
		frappe.db.set_single_value("Kenya Health Settings", "pay_before_lab", 0)
		frappe.db.set_single_value("Kenya Health Settings", "lab_second_validator", 1)
		name = lab.collect(requests=[self.order()])["done"][0]
		sheet = lab.results_sheet([name])[0]
		values = {r["name"]: "6" for r in sheet["normal"] if not r["heading"]}
		lab.save_results([{"lab_test": name, "normal": values}])
		result = lab.save_results([{"lab_test": name}], validate=1)
		self.assertEqual(len(result["errors"]), 1, "who entered the results may not validate them")

		frappe.db.set_value("Lab Test", name, "ke_results_by", "Guest")
		result = lab.save_results([{"lab_test": name}], validate=1)
		self.assertEqual(result["validated"], [name])

	def test_walk_in(self):
		with self.assertRaises(frappe.ValidationError):
			lab.walk_in(self.patient, [self.template], company=self.company)  # no requesting doctor

		frappe.db.set_single_value("Kenya Health Settings", "walk_in_lab_practitioner", self.practitioner)
		made = lab.walk_in(
			self.patient,
			[self.template],
			referred_by="Dr Outside, Town Clinic",
			priority="Urgent",
			company=self.company,
		)
		visit = frappe.get_doc("Patient Visit", made["visit"])
		self.assertEqual(
			(visit.visit_type, visit.current_station, visit.referred_from),
			(
				"Lab only",
				"Laboratory",
				"Dr Outside, Town Clinic",
			),
		)
		request = frappe.get_doc("Service Request", made["requests"][0])
		self.assertEqual(
			(request.docstatus, request.practitioner, request.ke_patient_visit, request.source),
			(1, self.practitioner, visit.name, "External Referral"),
		)
		row = self.row("requests", made["key"])
		self.assertEqual((row.priority, row.count, row.unpaid), ("Urgent", 1, 1))
		# The cashier's bill for the visit picks the request up.
		self.assertIn(request.name, [c["reference_dn"] for c in visit_bill.visit_bill(visit.name)["charges"]])

		# A second walk-in the same day goes on the same visit.
		again = lab.walk_in(self.patient, [self.template], company=self.company)
		self.assertEqual(again["visit"], visit.name)
