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

		# Not paid: off the worklist (the patient is at the Cashier), and the sample isn't taken.
		self.assertIsNone(self.row("requests", key))
		self.assertGreaterEqual(
			lab.worklist("requests", today(), today(), self.company)["awaiting_payment"], 1
		)
		result = lab.collect(requests=[request])
		self.assertEqual((result["done"], len(result["refused"])), ([], 1))

		visit_bill.approve_credit(visit.name, "Staff member")
		row = self.row("requests", key)
		self.assertTrue(row, "the order is on the Requests tab, grouped by visit")
		self.assertEqual((row.count, row.unpaid), (1, 0))
		test = lab.order(key, today(), today())["tests"][0]
		self.assertEqual((test["stage"], test["pay"], test["blocked"]), (lab.REQUESTED, "approved", False))
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
		# A cash walk-in waits off the worklist until paid at the Cashier.
		self.assertIsNone(self.row("requests", made["key"]))
		visit_bill.approve_credit(visit.name, "Paying at month end")
		row = self.row("requests", made["key"])
		self.assertEqual((row.priority, row.count, row.unpaid), ("Urgent", 1, 0))
		# The cashier's bill for the visit picks the request up.
		self.assertIn(request.name, [c["reference_dn"] for c in visit_bill.visit_bill(visit.name)["charges"]])

		# A second walk-in the same day goes on the same visit.
		again = lab.walk_in(self.patient, [self.template], company=self.company)
		self.assertEqual(again["visit"], visit.name)

	# Lab pack (v0.49): standard tests, per-visit reports, reception walk-ins

	def validated_test(self):
		"""A validated lab test on today's visit: (visit, lab test name)."""
		from royce_health_ke.visits import open_visit_for

		open_visit = open_visit_for(self.patient)
		visit = frappe.get_doc("Patient Visit", open_visit) if open_visit else self.check_in()
		frappe.db.set_single_value("Kenya Health Settings", "pay_before_lab", 0)
		name = lab.collect(requests=[self.order()])["done"][0]
		sheet = lab.results_sheet([name])[0]
		values = {r["name"]: "5.5" for r in sheet["normal"] if not r["heading"]}
		lab.save_results([{"lab_test": name, "normal": values}], validate=1)
		return visit, name

	def test_full_haemogram_from_the_library(self):
		rows = lab.LIBRARY["Full Haemogram"]["rows"]
		self.assertEqual(len(rows), 19)
		self.assertEqual([r[0] for r in rows][:4], ["WBC", "Lymph#", "Mid#", "Gran#"])
		self.assertEqual(rows[-1], ("PCT", "%", "0.108 - 0.282"))

		# Added under a name of its own, so the test doesn't depend on the site.
		suffix = frappe.generate_hash(length=5)
		name = f"Full Haemogram {suffix}"
		original = lab.LIBRARY
		lab.LIBRARY = {name: {**original["Full Haemogram"], "code": f"LAB-FHG-{suffix}"}}
		try:
			self.assertFalse(lab.lab_library()[0]["exists"])
			made = lab.add_from_library(name, 1200)
			self.assertTrue(lab.lab_library()[0]["exists"])
			with self.assertRaises(frappe.ValidationError):
				lab.add_from_library(name, 1200)  # already set up
		finally:
			lab.LIBRARY = original
		template = frappe.get_doc("Lab Test Template", made["name"])
		self.assertEqual(template.lab_test_template_type, "Compound")
		self.assertEqual(
			[
				(r.lab_test_event, r.lab_test_uom or "", r.normal_range)
				for r in template.normal_test_templates
			],
			[(e, u, n) for e, u, n in rows],
			"the analyser's print order, units and ranges",
		)
		self.assertTrue(made["priced"] and template.item)

		# Ordered, collected and typed in: 19 result lines, in that order, flagged.
		self.template = made["name"]
		self.check_in()
		frappe.db.set_single_value("Kenya Health Settings", "pay_before_lab", 0)
		test = lab.collect(requests=[self.order()])["done"][0]
		sheet = lab.results_sheet([test])[0]
		self.assertEqual([r["label"] for r in sheet["normal"]], [r[0] for r in rows])
		self.assertFalse(any(r["heading"] for r in sheet["normal"]))
		self.assertEqual(lab.flag("17.0", "12.0 - 16.0"), "H")

	def test_one_report_for_the_visits_tests(self):
		visit, first = self.validated_test()
		_v, second = self.validated_test()  # the same day: the same open visit
		row = self.row("completed", f"visit:{visit.name}")
		self.assertEqual(sorted(row.validated), sorted([first, second]))

		other_patient = self.patient
		self.patient = self.new_patient()
		_v, foreign = self.validated_test()
		self.patient = other_patient

		frappe.flags.ke_lab_tests = [first, second, foreign]
		try:
			report = lab.lab_report(frappe.get_doc("Lab Test", first))
			html = frappe.get_print("Lab Test", first, "Laboratory Report")
			request = lab.lab_request(frappe.get_doc("Lab Test", first))
		finally:
			frappe.flags.ke_lab_tests = None
		self.assertEqual(
			[t.doc.name for t in report.tests], [first, second], "another patient's test is left out"
		)
		self.assertTrue(report.many)
		self.assertIn(first, html)
		self.assertIn(second, html)
		self.assertNotIn(foreign, html)
		self.assertEqual([x.lab_test for x in request.lines], [first, second])
		self.assertEqual(request.visit, visit.name)

		# Alone, the report is the one test, as before.
		single = lab.lab_report(frappe.get_doc("Lab Test", first))
		self.assertEqual((len(single.tests), single.many), (1, False))

	def test_results_emailed_and_logged(self):
		_visit, name = self.validated_test()
		from unittest.mock import patch

		frappe.db.set_single_value("Kenya Health Settings", "track_record_access", 1)
		# The PDF itself needs a running web server for wkhtmltopdf; the report's
		# HTML is tested above.
		with (
			patch("frappe.get_print", return_value=b"%PDF-1.4 test"),
			patch(
				"frappe.email.doctype.email_account.email_account.EmailAccount.find_outgoing",
				return_value=frappe._dict(name="test"),
			),
			patch("frappe.sendmail") as sendmail,
		):
			sent = lab.email_results([name], "patient@example.com")
		self.assertEqual(sendmail.call_args.kwargs["recipients"], ["patient@example.com"])
		self.assertTrue(sendmail.call_args.kwargs["attachments"][0]["fname"].endswith(".pdf"))
		self.assertEqual(sent, {"sent": 1, "to": "patient@example.com"})
		self.assertTrue(
			frappe.db.exists(
				"Patient Record Access",
				{"reference_name": name, "action": "Email", "detail": "patient@example.com"},
			)
		)
		with self.assertRaises(frappe.ValidationError):
			lab.email_results([name], "not an email")

		# Results not validated yet are not sent.
		frappe.db.set_single_value("Kenya Health Settings", "pay_before_lab", 0)
		draft = lab.collect(requests=[self.order()])["done"][0]
		with self.assertRaises(frappe.ValidationError):
			lab.email_results([draft], "patient@example.com")

	def test_reception_makes_walk_in_requests(self):
		from royce_health_ke.test_cashier import user

		frappe.db.set_single_value("Kenya Health Settings", "walk_in_lab_practitioner", self.practitioner)
		reception = user("ke.reception@example.com", ["Receptionist"])
		cashier = user("ke.cashier@example.com", ["Cashier"])
		frappe.set_user(reception)
		try:
			tests = lab.walk_in_tests(self.template[:4])
			self.assertIn(self.template, [t["value"] for t in tests])
			made = lab.walk_in(self.patient, [self.template], company=self.company)
		finally:
			frappe.set_user("Administrator")
		visit = frappe.get_doc("Patient Visit", made["visit"])
		self.assertEqual((visit.visit_type, visit.payment_method), ("Lab only", "Cash"))
		# paid first, then on the lab's list
		self.assertIsNone(self.row("requests", made["key"]))

		frappe.set_user(cashier)
		try:
			with self.assertRaises(frappe.PermissionError):
				lab.walk_in(self.patient, [self.template], company=self.company)
		finally:
			frappe.set_user("Administrator")
