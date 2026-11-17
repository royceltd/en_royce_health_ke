# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""v0.44.1 (IT demo, 18 Nov 2026): saving the consultation sends its
requests; a diagnosis before prescribing and completing; no completing with
lab or imaging results pending; Cancel Request; the visit closes by itself
when finished, and Complete / Cancel Visit follow the rules; the Cashier
Queue opens the bill; the patient file; drugs only at the counter; eTIMS on
the receipt; the screen lock survives a reload."""

import frappe
from frappe.utils import add_to_date, today

from royce_health_ke import (
	cashier,
	consultation,
	pharmacy,
	printing,
	security,
	visit_bill,
	visit_close,
	visits,
)
from royce_health_ke.demo.journey import _pay
from royce_health_ke.test_consultation import ConsultationCase

OBSERVED = {"ke_chief_complaint": "Fever 3 days", "ke_hpi": "Evening fevers", "ke_examination": "Temp 38.4"}


def _settings(**values):
	for field, value in values.items():
		frappe.db.set_single_value("Kenya Health Settings", field, value)


def _diagnosis():
	return frappe.db.get_value("Diagnosis", {}, "name") or (
		frappe.get_doc({"doctype": "Diagnosis", "diagnosis": "Rules Test Fever"})
		.insert(ignore_permissions=True)
		.name
	)


class RulesCase(ConsultationCase):
	def setUp(self):
		super().setUp()
		frappe.flags.ke_test_observation_gate = True
		_settings(
			observation_before_requests=1,
			obs_need_complaint=1,
			obs_need_hpi=1,
			obs_need_ros=0,
			obs_need_examination=1,
			diagnosis_required=1,
			save_sends_requests=1,
		)

	def tearDown(self):
		frappe.flags.ke_test_observation_gate = False
		super().tearDown()

	def consult(self, lab=True, drug=False, observed=True, diagnosed=False):
		doc = frappe.get_doc(
			{
				"doctype": "Patient Encounter",
				"patient": self.patient,
				"practitioner": self.practitioner,
				"encounter_date": today(),
				"company": self.company,
				**(OBSERVED if observed else {}),
				"diagnosis": [{"diagnosis": _diagnosis()}] if diagnosed else [],
				"lab_test_prescription": [{"lab_test_code": self.template}] if lab else [],
				"drug_prescription": [
					{
						"medication": self.medication,
						"drug_code": "DRG-PCM500",
						"dosage": self.dosage,
						"period": self.period,
						"dosage_form": frappe.db.get_value("Dosage Form", {}, "name"),
					}
				]
				if drug
				else [],
			}
		)
		return doc.insert(ignore_permissions=True)

	def requests(self, enc, closed=False):
		filters = {"order_group": enc.name, "docstatus": 1}
		return frappe.get_all("Service Request", filters=filters, fields=["name", "status"])

	def result_lab(self, request):
		"""The lab's result for a request: a submitted Lab Test."""
		frappe.db.set_value("Patient Visit", self.visit.name, "allow_credit", 1)
		from royce_health_ke.marley import make_lab_test

		test = make_lab_test(request)
		test.flags.ignore_permissions = True
		test.flags.ignore_mandatory = True
		test.insert(ignore_permissions=True)
		frappe.db.set_value("Lab Test", test.name, "docstatus", 1)
		return test


class TestSavingSends(RulesCase):
	def test_first_save_sends_the_requests(self):
		enc = self.consult()
		self.assertEqual(len(self.requests(enc)), 1)
		self.assertEqual(frappe.db.get_value("Patient Encounter", enc.name, "docstatus"), 0)

	def test_without_the_observation_saved_but_not_sent(self):
		enc = self.consult(observed=False)
		self.assertEqual(self.requests(enc), [])
		enc.reload()
		enc.update(OBSERVED)
		enc.save(ignore_permissions=True)
		self.assertEqual(len(self.requests(enc)), 1)

	def test_a_second_round_of_tests(self):
		enc = self.consult()
		enc.reload()
		other = frappe.db.get_value(
			"Lab Test Template",
			{
				"is_billable": 1,
				"disabled": 0,
				"name": ["!=", self.template],
				"lab_test_template_type": "Single",
			},
			"name",
		)
		enc.append("lab_test_prescription", {"lab_test_code": other})
		enc.save(ignore_permissions=True)
		self.assertEqual(len(self.requests(enc)), 2)

	def test_deleting_a_row_cancels_its_request(self):
		enc = self.consult()
		request = self.requests(enc)[0].name
		enc.reload()
		enc.lab_test_prescription = []
		enc.save(ignore_permissions=True)
		self.assertEqual(frappe.db.get_value("Service Request", request, "status"), "revoked-Request Status")

	def test_switched_off_saving_keeps_them(self):
		_settings(save_sends_requests=0)
		enc = self.consult()
		self.assertEqual(self.requests(enc), [])


class TestDiagnosisAndPending(RulesCase):
	def test_prescribing_needs_a_diagnosis(self):
		with self.assertRaisesRegex(frappe.ValidationError, "diagnosis"):
			self.consult(lab=False, drug=True)
		self.consult(lab=False, drug=True, diagnosed=True)

	def test_completing_needs_a_diagnosis(self):
		enc = self.consult(lab=False)
		with self.assertRaisesRegex(frappe.ValidationError, "before completing"):
			consultation.complete(enc.name)
		enc.reload()
		enc.append("diagnosis", {"diagnosis": _diagnosis()})
		enc.save(ignore_permissions=True)
		consultation.complete(enc.name)
		self.assertEqual(frappe.db.get_value("Patient Encounter", enc.name, "docstatus"), 1)

	def test_pending_results_block_completing_until_in_or_cancelled(self):
		enc = self.consult(diagnosed=True)
		request = self.requests(enc)[0].name
		with self.assertRaisesRegex(frappe.ValidationError, "no result yet"):
			consultation.complete(enc.name)
		# the panel offers Cancel Request for a request not started
		row = next(r for r in consultation.panel(enc.name)["results"] if r.get("request") == request)
		self.assertEqual(row["cancellable"], 1)
		consultation.cancel_request(request, "Patient left")
		self.assertEqual(frappe.db.get_value("Service Request", request, "ke_cancel_reason"), "Patient left")
		consultation.complete(enc.name)
		self.assertEqual(frappe.db.get_value("Patient Encounter", enc.name, "docstatus"), 1)

	def test_a_result_in_lets_it_complete(self):
		enc = self.consult(diagnosed=True)
		self.result_lab(self.requests(enc)[0].name)
		consultation.complete(enc.name)
		self.assertEqual(frappe.db.get_value("Patient Encounter", enc.name, "docstatus"), 1)

	def test_a_started_request_cant_be_cancelled(self):
		enc = self.consult(diagnosed=True)
		request = self.requests(enc)[0].name
		self.result_lab(request)
		with self.assertRaisesRegex(frappe.ValidationError, "already started"):
			consultation.cancel_request(request, "Changed my mind")

	def test_casualty_needs_no_diagnosis_to_prescribe(self):
		frappe.db.set_value("Patient Visit", self.visit.name, "visit_type", "Casualty")
		self.consult(lab=False, drug=True, observed=False)


class TestVisitClosing(RulesCase):
	def setUp(self):
		super().setUp()
		frappe.flags.ke_test_visit_rules = True
		frappe.flags.ke_test_auto_close = True
		_settings(auto_close_visits=1)

	def tearDown(self):
		frappe.flags.ke_test_visit_rules = False
		frappe.flags.ke_test_auto_close = False
		super().tearDown()

	def test_open_items_then_closes_by_itself_once_paid(self):
		self.assertIn("No consultation completed yet", visit_close.open_items(self.visit.name))
		enc = self.consult(lab=False, diagnosed=True)
		consultation.complete(enc.name)
		items = visit_close.open_items(self.visit.name)
		self.assertEqual(frappe.db.get_value("Patient Visit", self.visit.name, "status"), "Open")
		self.assertTrue(any("not billed" in i for i in items), items)
		si = frappe.get_doc(visit_bill.make_bill(self.visit.name))
		si.insert(ignore_permissions=True)
		si.submit()
		_pay(si, f"TEST-{frappe.generate_hash(length=6)}")
		self.assertEqual(visit_close.open_items(self.visit.name), [])
		self.assertEqual(frappe.db.get_value("Patient Visit", self.visit.name, "status"), "Completed")

	def test_complete_visit_needs_a_managers_reason_while_open(self):
		with self.assertRaisesRegex(frappe.ValidationError, "reason"):
			visits.complete(self.visit.name)
		visits.complete(self.visit.name, "Patient absconded")
		v = frappe.get_doc("Patient Visit", self.visit.name)
		self.assertEqual(v.status, "Completed")
		self.assertIn("Patient absconded", v.status_reason)

	def test_non_manager_cant_close_with_open_items(self):
		user = "rules.reception@roleaccess.test"
		if not frappe.db.exists("User", user):
			frappe.get_doc(
				{
					"doctype": "User",
					"email": user,
					"first_name": "Rules Reception",
					"send_welcome_email": 0,
					"roles": [{"role": "Receptionist"}],
				}
			).insert(ignore_permissions=True)
		frappe.set_user(user)
		try:
			with self.assertRaisesRegex(frappe.ValidationError, "open items"):
				visits.complete(self.visit.name, "trying")
		finally:
			frappe.set_user("Administrator")

	def test_cancel_only_before_anything_happens(self):
		visits.cancel(self.visit.name, "Wrong patient")
		self.assertEqual(frappe.db.get_value("Patient Visit", self.visit.name, "status"), "Cancelled")
		visit = frappe.get_doc(
			{
				"doctype": "Patient Visit",
				"patient": self.patient,
				"company": self.company,
				"visit_type": "Outpatient",
				"appointment_type": self.appointment_type,
				"practitioner": self.practitioner,
			}
		).insert(ignore_permissions=True)
		frappe.get_doc(
			{
				"doctype": "Patient Encounter",
				"patient": self.patient,
				"practitioner": self.practitioner,
				"encounter_date": today(),
				"company": self.company,
				"ke_patient_visit": visit.name,
			}
		).insert(ignore_permissions=True)
		with self.assertRaisesRegex(frappe.ValidationError, "can't be cancelled"):
			visits.cancel(visit.name, "Wrong patient")


class TestCashierQueue(RulesCase):
	def test_cashier_queue_opens_the_bill(self):
		enc = self.consult(lab=False, diagnosed=True)
		consultation.complete(enc.name)
		si = frappe.get_doc(visit_bill.make_bill(self.visit.name))
		si.insert(ignore_permissions=True)
		frappe.db.set_value("Patient Visit", self.visit.name, "current_station", "Cashier")
		self.assertEqual(visits.open_station(self.visit.name), {"doctype": "Sales Invoice", "name": si.name})


class TestPatientFile(RulesCase):
	def test_clinicians_only(self):
		enc = self.consult(lab=False, diagnosed=True)
		doc = frappe.get_doc("Patient", self.patient)
		f = printing.patient_file(doc)
		self.assertTrue(f.allowed)
		self.assertIn(enc.name, [e.doc.name for v in f.visits for e in v.encounters])
		user = "rules.cashier@roleaccess.test"
		if not frappe.db.exists("User", user):
			frappe.get_doc(
				{
					"doctype": "User",
					"email": user,
					"first_name": "Rules Cashier",
					"send_welcome_email": 0,
					"roles": [{"role": "Cashier"}],
				}
			).insert(ignore_permissions=True)
		frappe.set_user(user)
		try:
			self.assertFalse(printing.patient_file(doc).allowed)
		finally:
			frappe.set_user("Administrator")


class TestSmallFixes(RulesCase):
	def test_counter_offers_drugs_only(self):
		groups = pharmacy.drug_groups()
		if not groups:
			self.skipTest("needs the pharmacy's drug item group")
		names = [r[0] for r in pharmacy.drug_query("Item", "", "name", 0, 500, {})]
		self.assertIn("DRG-PCM500", names)
		other = frappe.db.get_value(
			"Item", {"item_group": ["not in", groups], "is_stock_item": 1, "disabled": 0}, "name"
		)
		if other:
			self.assertNotIn(other, names)
			with self.assertRaisesRegex(frappe.ValidationError, "Only drugs"):
				pharmacy.counter_sale([{"item_code": other, "qty": 1}], walk_in_name="Test")

	def test_receipt_shows_etims_once_signed(self):
		doc = frappe._dict(doctype="Sales Invoice", company=self.company)
		self.assertIsNone(printing._etims_receipt(doc))
		doc.update(
			royce_etims_receipt_signature="ABCD1234",
			royce_etims_invoice_number="KRACU0100000001/12",
			royce_etims_current_receipt_number=12,
			royce_etims_total_receipt_number=40,
		)
		e = printing._etims_receipt(doc)
		self.assertEqual((e.signature, e.receipt_number), ("ABCD1234", "12/40"))

	def test_lock_survives_a_reload(self):
		_settings(idle_lock_minutes=10)
		security.lock()
		boot = frappe._dict()
		security.extend_bootinfo(boot)
		self.assertTrue(boot.ke_screen_locked)
		frappe.cache.delete_value(security._lock_key())
		boot = frappe._dict()
		security.extend_bootinfo(boot)
		self.assertFalse(boot.ke_screen_locked)

	def test_new_patient_contact_rule_unchanged(self):
		# children may give the next of kin's phone instead (identity.missing_registration_details)
		from royce_health_ke.identity import missing_registration_details

		child = frappe._dict(
			sex="Female", dob=add_to_date(today(), years=-5), ke_id_type="None", ke_nok_phone="+254700000001"
		)
		self.assertNotIn("Mobile number", " ".join(missing_registration_details(child)))
