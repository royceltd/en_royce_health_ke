# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""v0.36 (outpatient feedback, 16 Nov 2026): the consultation in tabs with
Send Requests, Results and Complete Consultation; the pharmacist can't swap a
prescribed medicine; the patient receipt with the M-Pesa code."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_to_date, today

from royce_health_ke import cashier, consultation, pharmacy, printing, visit_bill
from royce_health_ke.demo.journey import _pay

TAB_ORDER = [tab for tab, _sections in consultation.TABS]


class TestConsultationLayout(IntegrationTestCase):
	def test_layout_order_puts_sections_under_their_tabs(self):
		fields = [
			("naming_series", "Select"),
			("patient", "Link"),
			("ke_tab_requests", "Tab Break"),
			("ke_clerking_section", "Section Break"),
			("ke_chief_complaint", "Small Text"),
			("sb_symptoms", "Section Break"),
			("diagnosis", "Table MultiSelect"),
			("someone_elses_section", "Section Break"),
			("their_field", "Data"),
			("sb_drug_prescription", "Section Break"),
			("drug_prescription", "Table"),
			("sb_test_prescription", "Section Break"),
			("lab_test_prescription", "Table"),
			("encounter_details_tab", "Tab Break"),
			("encounter_details", "HTML"),
			("notes_tab", "Tab Break"),
			("clinical_notes", "HTML"),
			("ke_complete_section", "Section Break"),
			("ke_complete_consultation", "Button"),
		]
		order = consultation.layout_order(fields)
		self.assertEqual(sorted(order), sorted([f for f, _t in fields if f != "ke_tab_requests"] + TAB_ORDER))
		pos = order.index
		# tabs in the hospital's order, before Marley's own tabs
		self.assertEqual([t for t in order if t in TAB_ORDER], TAB_ORDER)
		self.assertLess(pos("ke_tab_complete"), pos("encounter_details_tab"))
		self.assertEqual(order[0], "ke_tab_patient")
		self.assertTrue(pos("ke_tab_observation") < pos("ke_clerking_section") < pos("ke_tab_requests"))
		self.assertTrue(pos("ke_tab_requests") < pos("sb_test_prescription") < pos("ke_tab_results"))
		self.assertTrue(pos("ke_tab_diagnosis") < pos("sb_symptoms") < pos("ke_tab_prescription"))
		self.assertTrue(pos("ke_tab_prescription") < pos("sb_drug_prescription") < pos("ke_tab_complete"))
		# a section we don't know stays after the one it followed
		self.assertEqual(pos("someone_elses_section"), pos("diagnosis") + 1)
		# our section Frappe put after Marley's Notes tab is under Complete
		self.assertTrue(pos("ke_tab_complete") < pos("ke_complete_section") < pos("encounter_details_tab"))
		self.assertEqual(order[-2:], ["notes_tab", "clinical_notes"])

	def test_site_form_has_the_tabs(self):
		meta = frappe.get_meta("Patient Encounter")
		names = [f.fieldname for f in meta.fields]
		tabs = [f.fieldname for f in meta.fields if f.fieldtype == "Tab Break"]
		self.assertEqual(tabs[: len(TAB_ORDER)], TAB_ORDER)

		def tab_of(fieldname):
			return [t for t in tabs if names.index(t) < names.index(fieldname)][-1]

		self.assertEqual(tab_of("ke_obs_gynae"), "ke_tab_observation")
		self.assertEqual(tab_of("lab_test_prescription"), "ke_tab_requests")
		self.assertEqual(tab_of("ke_results_html"), "ke_tab_results")
		self.assertEqual(tab_of("diagnosis"), "ke_tab_diagnosis")
		self.assertEqual(tab_of("drug_prescription"), "ke_tab_prescription")
		self.assertEqual(tab_of("ke_complete_consultation"), "ke_tab_complete")
		# the referral is no longer inside Marley's hidden Source section
		section = [
			f for f in meta.fields[: names.index("ke_referred_out")] if f.fieldtype == "Section Break"
		][-1]
		self.assertEqual(section.fieldname, "ke_referral_section")
		self.assertFalse(section.hidden)

	def test_layout_is_set_once(self):
		frappe.db.set_value(
			"Property Setter",
			{"doc_type": "Patient Encounter", "property": "field_order"},
			"value",
			'["kept"]',
		)
		consultation.apply_layout()
		self.assertEqual(
			frappe.db.get_value(
				"Property Setter", {"doc_type": "Patient Encounter", "property": "field_order"}, "value"
			),
			'["kept"]',
		)
		frappe.db.rollback()


class ConsultationCase(IntegrationTestCase):
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
		self.medication = frappe.db.get_value("Medication Linked Item", {"item": "DRG-PCM500"}, "parent")
		self.dosage = frappe.db.exists("Prescription Dosage", "1-1-1 (three times daily)")
		self.period = frappe.db.exists("Prescription Duration", "3 Day")
		self.store = frappe.db.get_value(
			"Bin", {"item_code": "DRG-PCM500", "actual_qty": [">", 50]}, "warehouse"
		)
		if not all(
			(
				self.template,
				self.practitioner,
				self.appointment_type,
				self.medication,
				self.dosage,
				self.period,
				self.store,
			)
		):
			self.skipTest("needs the demo's lab tests, paracetamol with stock and a practitioner")
		frappe.flags.ke_test_payment_gate = True
		for field in ("pay_before_lab", "pay_before_radiology", "pay_before_pharmacy"):
			frappe.db.set_single_value("Kenya Health Settings", field, 1)
		frappe.db.set_single_value("Kenya Health Settings", "pay_before_triage", 0)
		self.patient = (
			frappe.get_doc(
				{
					"doctype": "Patient",
					"first_name": "Consult",
					"last_name": f"Test {frappe.generate_hash(length=6)}",
					"sex": "Female",
					"dob": add_to_date(today(), years=-35),
					"mobile": "0712345678",
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

	def encounter(self, lab=True, drug=False):
		return frappe.get_doc(
			{
				"doctype": "Patient Encounter",
				"patient": self.patient,
				"practitioner": self.practitioner,
				"encounter_date": today(),
				"company": self.company,
				"ke_obs_gynae": "LMP 2 weeks ago, G2P1",
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
		).insert(ignore_permissions=True)


class TestConsultationFlow(ConsultationCase):
	def test_send_requests_keeps_the_consultation_open(self):
		enc = self.encounter()
		self.assertEqual(enc.ke_patient_visit, self.visit.name)
		self.assertEqual(enc.ke_obs_gynae, "LMP 2 weeks ago, G2P1")
		info = consultation.send_requests(enc.name)
		enc.reload()
		self.assertEqual(enc.docstatus, 0)
		request = frappe.db.get_value("Service Request", {"order_group": enc.name, "docstatus": 1}, "name")
		self.assertTrue(request)
		# cash and not paid: the Cashier first, then the lab
		self.assertEqual(info["stations"][:2], ["Cashier", "Laboratory"])
		self.assertEqual((info["unpaid"], info["visit"], info["completed"]), (1, self.visit.name, False))
		results = consultation.panel(enc.name)["results"]
		self.assertEqual(len(results), 1)
		self.assertEqual(results[0]["request"], request)
		self.assertTrue(results[0].get("awaiting_payment"))

		# Paid: no Cashier stop; the request waits at the lab.
		si = frappe.get_doc(visit_bill.make_bill(self.visit.name))
		si.insert(ignore_permissions=True)
		si.submit()
		_pay(si, f"TEST-{frappe.generate_hash(length=6)}")
		info = consultation.next_stations(enc)
		self.assertEqual((info["stations"][0], info["unpaid"]), ("Laboratory", 0))
		row = consultation.panel(enc.name)["results"][0]
		self.assertFalse(row.get("awaiting_payment"))

		# A second send places nothing twice.
		consultation.send_requests(enc.name)
		self.assertEqual(frappe.db.count("Service Request", {"order_group": enc.name, "docstatus": 1}), 1)

	def test_send_requests_needs_a_request(self):
		enc = self.encounter(lab=False)
		with self.assertRaisesRegex(frappe.ValidationError, "Add a lab test"):
			consultation.send_requests(enc.name)

	def test_complete_submits_and_suggests_pharmacy(self):
		enc = self.encounter(lab=False, drug=True)
		info = consultation.complete(enc.name)
		self.assertEqual(frappe.db.get_value("Patient Encounter", enc.name, "docstatus"), 1)
		# a cash patient's drugs are paid first (v0.37): the Cashier, then the Pharmacy
		self.assertEqual(
			(info["stations"], info["unpaid"], info["completed"]), (["Cashier", "Pharmacy"], 1, True)
		)
		with self.assertRaisesRegex(frappe.ValidationError, "already completed"):
			consultation.send_requests(enc.name)

	def test_panel_shows_validated_results_and_sent_back_drugs(self):
		frappe.flags.ke_test_payment_gate = False
		enc = self.encounter(drug=True)
		enc.submit()
		request = frappe.db.get_value("Service Request", {"order_group": enc.name}, "name")
		row = consultation.panel(enc.name)["results"][0]
		self.assertEqual(row["status"], "Waiting at the lab")

		test = frappe.get_doc(
			{
				"doctype": "Lab Test",
				"patient": self.patient,
				"patient_sex": "Female",
				"template": self.template,
				"practitioner": self.practitioner,
				"company": self.company,
				"service_request": request,
			}
		).insert(ignore_permissions=True)
		self.assertEqual(consultation.panel(enc.name)["results"][0]["status"], "At the lab")
		for item in test.normal_test_items:
			item.result_value = item.result_value or "5"
		for item in test.descriptive_test_items:
			item.result_value = item.result_value or "Seen"
		test.save(ignore_permissions=True)
		test.submit()
		row = consultation.panel(enc.name)["results"][0]
		self.assertEqual((row["status"], row["doctype"], row["name"]), ("Validated", "Lab Test", test.name))
		self.assertTrue(row["rows"])
		self.assertFalse(row["seen"])

		mr = frappe.db.get_value("Medication Request", {"order_group": enc.name}, "name")
		pharmacy.send_back([mr], "Out of stock: please prescribe another")
		sent = consultation.panel(enc.name)["sent_back"]
		self.assertEqual([m.name for m in sent], [mr])
		self.assertIn("Out of stock", sent[0].note)


class TestSubstitutionLock(ConsultationCase):
	def other_item(self):
		item = frappe.db.get_value(
			"Item", {"is_stock_item": 1, "disabled": 0, "name": ["!=", "DRG-PCM500"]}, "name"
		)
		if not item:
			self.skipTest("needs a second stock item")
		return item

	def prescription(self):
		enc = self.encounter(lab=False, drug=True)
		enc.submit()
		mr = frappe.db.get_value("Medication Request", {"order_group": enc.name}, "name")
		frappe.db.set_value("Medication Request", mr, {"quantity": 9, "total_dispensable_quantity": 9})
		return mr

	def test_bill_cannot_swap_the_prescribed_drug(self):
		mr = self.prescription()
		other = self.other_item()
		si = frappe.get_doc("Sales Invoice", pharmacy.bill_drugs(self.visit.name))
		row = next(r for r in si.items if r.reference_dn == mr)
		row.item_code = other
		with self.assertRaisesRegex(frappe.ValidationError, "Send back to the doctor"):
			si.save(ignore_permissions=True)
		si.reload()
		si.save(ignore_permissions=True)  # unchanged: fine

	def test_delivery_cannot_swap_the_prescribed_drug(self):
		mr = self.prescription()
		other = self.other_item()
		customer = frappe.db.get_value("Patient", self.patient, "customer")
		dn = frappe.get_doc(
			{
				"doctype": "Delivery Note",
				"company": self.company,
				"customer": customer,
				"set_warehouse": self.store,
				"items": [
					{"item_code": other, "qty": 1, "warehouse": self.store, "ke_medication_request": mr}
				],
			}
		)
		with self.assertRaisesRegex(frappe.ValidationError, "can't be substituted|not changed"):
			dn.insert(ignore_permissions=True)
		dn.items[0].item_code = "DRG-PCM500"
		pharmacy.lock_substitution(dn)  # the prescribed drug passes

	def test_rows_without_a_prescription_are_free(self):
		dn = frappe.get_doc(
			{"doctype": "Delivery Note", "items": [{"item_code": self.other_item(), "qty": 1}]}
		)
		self.assertEqual(pharmacy._prescribed(dn.items), [])
		pharmacy.lock_substitution(dn)


class TestReceipt(ConsultationCase):
	def non_cash_mode(self):
		mode = frappe.db.get_value("Mode of Payment", {"type": ["!=", "Cash"], "enabled": 1}, "name")
		if not mode:
			self.skipTest("needs a non-cash mode of payment")
		return mode

	def test_transaction_code_required_for_non_cash(self):
		mode = self.non_cash_mode()
		cash = frappe.db.get_value("Mode of Payment", {"type": "Cash", "enabled": 1}, "name")
		si = frappe.get_doc(
			{
				"doctype": "Sales Invoice",
				"is_pos": 1,
				"payments": [
					{"mode_of_payment": mode, "amount": 200},
					{"mode_of_payment": cash, "amount": 50},
				],
			}
		)
		self.assertEqual(cashier.missing_references(si), [mode])
		si.payments[0].reference_no = "UKF8I2ECFD"
		self.assertEqual(cashier.missing_references(si), [])
		pe = frappe.get_doc({"doctype": "Payment Entry", "payment_type": "Receive", "mode_of_payment": mode})
		self.assertEqual(cashier.missing_references(pe), [mode])
		pe.reference_no = "UKF8I2ECFD"
		self.assertEqual(cashier.missing_references(pe), [])

	def test_patient_receipt(self):
		consultation.send_requests(self.encounter().name)
		si = frappe.get_doc(visit_bill.make_bill(self.visit.name))
		si.insert(ignore_permissions=True)
		si.submit()
		_pay(si, "UKF8I2ECFD")
		si.reload()
		r = printing.health_patient_receipt(si)
		named = self.patient == frappe.db.get_value("Patient", self.patient, "patient_name")
		self.assertEqual(r.patient_no, "" if named else self.patient)
		self.assertTrue(r.phone.endswith("712345678"))
		self.assertTrue(r.payments)
		html = frappe.get_print("Sales Invoice", si.name, "Patient Receipt", doc=si)
		self.assertIn("RECEIPT", html)
		self.assertIn(si.name, html)
		self.assertIn(frappe.db.get_value("Patient", self.patient, "patient_name"), html)
