# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""v0.45 (Bethesda proposals, 18 Nov 2026): prescribing in dispensing units,
ICD-11 diagnosis rows, the clerking order, vital signs history, the Visit
Summary, Request Types routed to their service point with a Nursing
Worklist, and counter prescriptions."""

import json

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt, today

from royce_health_ke import consultation, diagnosis, dispensing, pharmacy, printing, routing
from royce_health_ke.codes import ICD11, upsert_codes
from royce_health_ke.test_consultation import ConsultationCase


def _uom(name):
	if not frappe.db.exists("UOM", name):
		frappe.get_doc({"doctype": "UOM", "uom_name": name}).insert(ignore_permissions=True)
	return name


def _dosage(name, times):
	if not frappe.db.exists("Prescription Dosage", name):
		frappe.get_doc(
			{
				"doctype": "Prescription Dosage",
				"dosage": name,
				"dosage_strength": [{"strength": 1} for _ in range(times)],
			}
		).insert(ignore_permissions=True)
	return name


def _duration(number, period="Day"):
	name = f"{number} {period}"
	if not frappe.db.exists("Prescription Duration", name):
		frappe.get_doc({"doctype": "Prescription Duration", "number": number, "period": period}).insert(
			ignore_permissions=True
		)
	return name


class TestDispensingUnits(IntegrationTestCase):
	def setUp(self):
		self.tid = _dosage("KE Test TID", 3)
		self.ten_days = _duration(10)

	def test_times_a_day_from_strengths_and_names(self):
		self.assertEqual(dispensing.times_a_day(self.tid), 3)
		doc = frappe.get_doc(
			{"doctype": "Prescription Dosage", "dosage": f"1-0-1 KE {frappe.generate_hash(length=4)}"}
		).insert(ignore_permissions=True)
		self.assertEqual(dispensing.times_a_day(doc.name), 2)

	def test_bottle_example(self):
		"""5 ml TID for 10 days = 150 ml; 100 ml bottles -> 2 bottles."""
		ml, bottle = _uom("ml"), _uom("Bottle")
		code = f"_KE-AMOX-SUSP-{frappe.generate_hash(length=4)}"
		group = frappe.db.get_value("Item Group", {"is_group": 0}, "name")
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": code,
				"item_group": group,
				"stock_uom": bottle,
				"is_stock_item": 1,
			}
		).insert(ignore_permissions=True)
		original = dispensing.pack_size
		dispensing.pack_size = lambda medication, dose_uom, item_code=None: 100.0 if dose_uom == ml else 1.0
		self.addCleanup(setattr, dispensing, "pack_size", original)
		result = dispensing.compute(
			item_code=code, dose=5, dose_uom=ml, dosage=self.tid, period=self.ten_days
		)
		self.assertEqual(result.total, 150)
		self.assertEqual(result.quantity, 2)
		self.assertEqual(result.unit, bottle)

	def test_pack_size_rules(self):
		ml, tab = _uom("ml"), _uom("Tablet")
		code = f"_KE-PACK-{frappe.generate_hash(length=4)}"
		group = frappe.db.get_value("Item Group", {"is_group": 0}, "name")
		frappe.get_doc(
			{"doctype": "Item", "item_code": code, "item_group": group, "stock_uom": tab, "is_stock_item": 1}
		).insert(ignore_permissions=True)
		# a dose in the stock unit needs no pack size
		self.assertEqual(dispensing.pack_size(None, tab, code), 1.0)
		# unknown: no pack size, no strength in that unit
		self.assertIsNone(dispensing.pack_size(None, ml, code))

	def test_without_a_dose_marley_units(self):
		code = frappe.db.get_value("Item", {"is_stock_item": 1}, "name")
		result = dispensing.compute(item_code=code, dosage=self.tid, period=self.ten_days)
		self.assertEqual(result.quantity, 30)

	def test_missing_frequency_gives_none(self):
		self.assertIsNone(dispensing.compute(dose=5, period=self.ten_days))

	def test_instructions_text(self):
		self.assertEqual(
			dispensing.instructions_text(5, "ml", "TID", "5 Day", "Oral", "After food"),
			"5 ml TID for 5 Day, Oral. After food",
		)


class TestDispensingOnTheConsultation(ConsultationCase):
	def test_medication_request_carries_dose_and_quantity(self):
		doc = self.encounter(lab=False, drug=True)
		row = doc.drug_prescription[0]
		row.ke_dose = 1
		row.ke_route = "Oral"
		row.ke_start_date = today()
		row.ke_quantity = 0
		doc.save()
		row = doc.drug_prescription[0]
		expected = dispensing.compute_row(row)
		if expected:
			self.assertEqual(row.ke_quantity, expected.quantity)
		self.assertTrue(row.ke_dispensing_unit)
		doc.make_medication_request()
		mr = frappe.get_doc("Medication Request", doc.drug_prescription[0].medication_request)
		self.assertEqual(mr.ke_route, "Oral")
		self.assertEqual(mr.ke_dose, 1)
		self.assertEqual(mr.quantity, int(row.ke_quantity))
		self.assertIn("Oral", pharmacy.instructions(mr))

	def test_doctor_quantity_wins(self):
		doc = self.encounter(lab=False, drug=True)
		doc.drug_prescription[0].ke_quantity = 7
		doc.save()
		doc.make_medication_request()
		self.assertEqual(
			frappe.db.get_value(
				"Medication Request", doc.drug_prescription[0].medication_request, "quantity"
			),
			7,
		)


class TestICD11Diagnosis(IntegrationTestCase):
	def setUp(self):
		self.code = f"ZZ{frappe.generate_hash(length=3).upper()}"
		self.title = f"Test condition {self.code}"
		upsert_codes(ICD11, [(self.code, self.title, None, 0)])
		self.cv = frappe.db.get_value("Code Value", {"code_system": ICD11, "code_value": self.code}, "name")

	def test_search_by_code_and_by_name(self):
		by_code = diagnosis.icd11_query("Code Value", self.code, "name", 0, 10, {})
		self.assertEqual(by_code[0][0], self.cv)
		by_name = diagnosis.diagnosis_query("Diagnosis", self.title, "name", 0, 10, {})
		self.assertIn(self.title, [r[0] for r in by_name])

	def test_code_makes_the_diagnosis_with_its_coding(self):
		out = diagnosis.resolve(code_value=self.cv)
		self.assertEqual(out["diagnosis"], self.title)
		self.assertEqual(out["code"], self.code)
		self.assertEqual(diagnosis.icd11_of(self.title), (self.cv, self.code))
		# once: picking it again finds the same record
		self.assertEqual(diagnosis.ensure_diagnosis(self.cv), self.title)

	def test_name_fills_the_code(self):
		out = diagnosis.resolve(diagnosis=self.title)
		self.assertEqual(out["code_value"], self.cv)

	def test_hospital_diagnosis_with_another_code_kept_apart(self):
		other = f"ZY{frappe.generate_hash(length=3).upper()}"
		dx = frappe.new_doc("Diagnosis")
		dx.diagnosis = self.title
		from royce_health_ke.codes import set_coding

		set_coding(dx, ICD11, other, "Other")
		dx.insert(ignore_permissions=True)
		name = diagnosis.ensure_diagnosis(self.cv)
		self.assertNotEqual(name, self.title)
		self.assertIn(self.code, name)

	def test_sync_rows_fills_both_and_the_encounter_codes(self):
		doc = frappe.new_doc("Patient Encounter")
		doc.append("diagnosis", {"ke_icd11_code": self.cv})
		diagnosis.sync_rows(doc)
		self.assertEqual(doc.diagnosis[0].diagnosis, self.title)
		self.assertEqual([r.code for r in doc.codification_table], [self.code])
		diagnosis.sync_rows(doc)  # idempotent
		self.assertEqual(len(doc.codification_table), 1)

	def test_empty_row_has_no_codes(self):
		# Add Row on the diagnosis table asks Marley for the codes of an empty row
		self.assertEqual(diagnosis.get_medical_codes("Diagnosis"), [])
		self.assertEqual(diagnosis.get_medical_codes("Diagnosis", ""), [])
		name = diagnosis.ensure_diagnosis(self.cv)
		codes = diagnosis.get_medical_codes("Diagnosis", name)
		self.assertEqual([c.code for c in codes], [self.code])
		hooks = frappe.get_hooks("override_whitelisted_methods")
		self.assertEqual(
			hooks["healthcare.healthcare.utils.get_medical_codes"][-1],
			"royce_health_ke.diagnosis.get_medical_codes",
		)


class TestClerkingOrder(IntegrationTestCase):
	def test_examination_last_on_the_observation_tab(self):
		meta = frappe.get_meta("Patient Encounter")
		names = [f.fieldname for f in meta.fields]
		pos = names.index
		self.assertTrue(
			pos("ke_chief_complaint")
			< pos("ke_hpi")
			< pos("ke_review_of_systems")
			< pos("ke_hx_medical")
			< pos("ke_hx_surgical")
			< pos("ke_hx_family")
			< pos("ke_hx_social")
			< pos("ke_obs_gynae")
			< pos("ke_examination")
			< pos("ke_tab_requests")
		)
		self.assertEqual(int(frappe.db.get_default(consultation.LAYOUT_KEY)), consultation.LAYOUT_VERSION)

	def _set_layout(self, value):
		frappe.db.set_value(
			"Property Setter", {"doc_type": "Patient Encounter", "property": "field_order"}, "value", value
		)

	def test_our_old_default_is_replaced(self):
		ps = frappe.db.get_value(
			"Property Setter", {"doc_type": "Patient Encounter", "property": "field_order"}, "value"
		)
		order = json.loads(ps)
		# the v1 default: examination inside the presenting complaint section
		order.remove("ke_examination")
		order.remove("ke_exam_section")
		order.insert(order.index("ke_review_of_systems") + 1, "ke_examination")
		self._set_layout(json.dumps(order))
		self.assertTrue(consultation.on_our_default(json.dumps(order)))
		frappe.db.set_default(consultation.LAYOUT_KEY, 1)
		consultation.apply_layout()
		new = json.loads(
			frappe.db.get_value(
				"Property Setter", {"doc_type": "Patient Encounter", "property": "field_order"}, "value"
			)
		)
		self.assertGreater(new.index("ke_examination"), new.index("ke_obs_gynae"))
		frappe.db.rollback()

	def test_hospital_order_is_kept(self):
		self._set_layout('["kept"]')
		frappe.db.set_default(consultation.LAYOUT_KEY, 1)
		self.assertFalse(consultation.on_our_default('["kept"]'))
		consultation.apply_layout()
		self.assertEqual(
			frappe.db.get_value(
				"Property Setter", {"doc_type": "Patient Encounter", "property": "field_order"}, "value"
			),
			'["kept"]',
		)
		frappe.db.rollback()


class TestRouting(IntegrationTestCase):
	def setUp(self):
		routing.seed()
		routing.clear_cache()

	def test_defaults_seeded(self):
		points = {c.name: c.service_point for c in routing.categories()}
		self.assertEqual(points.get("Laboratory"), "Laboratory")
		self.assertEqual(points.get("Nursing"), "Nursing")

	def test_specific_group_beats_catch_all(self):
		template = frappe.db.get_value(
			"Clinical Procedure Template", {}, ["name", "item_group"], as_dict=True
		)
		if not template:
			self.skipTest("needs a procedure template")
		original = template.item_group
		frappe.db.set_value("Clinical Procedure Template", template.name, "item_group", routing.NURSING_GROUP)
		self.assertEqual(
			routing.category_for("Clinical Procedure Template", template.name), ("Nursing", "Nursing")
		)
		frappe.db.set_value("Clinical Procedure Template", template.name, "item_group", original)
		_category, point = routing.category_for("Clinical Procedure Template", template.name)
		if original == routing.SURGICAL_GROUP:
			self.assertEqual(point, routing.THEATRE)
		elif original != routing.NURSING_GROUP:
			self.assertEqual(point, "Procedure Room")

	def test_lab_template_routes_to_laboratory(self):
		template = frappe.db.get_value("Lab Test Template", {}, "name")
		if not template:
			self.skipTest("needs a lab test template")
		self.assertEqual(routing.category_for("Lab Test Template", template)[1], "Laboratory")

	def test_template_query_filters_by_type(self):
		template = frappe.db.get_value("Lab Test Template", {"disabled": 0}, "name")
		if not template:
			self.skipTest("needs a lab test template")
		rows = routing.template_query(
			"Lab Test Template", template[:4], "name", 0, 50, {"category": "Laboratory"}
		)
		self.assertIn(template, [r[0] for r in rows])
		# an Imaging type offers no lab test templates
		self.assertEqual(
			routing.template_query("Lab Test Template", "", "name", 0, 50, {"category": "Imaging"}), []
		)


class TestNursingWorklist(ConsultationCase):
	def test_nursing_request_done(self):
		routing.seed()
		template = frappe.db.get_value("Clinical Procedure Template", {}, "name")
		if not template:
			self.skipTest("needs a procedure template")
		frappe.db.set_value("Clinical Procedure Template", template, "item_group", routing.NURSING_GROUP)
		routing.clear_cache()
		doc = self.encounter(lab=False)
		doc.append("procedure_prescription", {"procedure": template})
		doc.submit_orders_on_save = 1
		doc.save()
		request = doc.procedure_prescription[0].service_request
		self.assertEqual(frappe.db.get_value("Service Request", request, "ke_service_point"), "Nursing")
		self.assertIn("Nursing", consultation.next_stations(doc)["stations"])
		frappe.db.set_single_value("Kenya Health Settings", "cashier_before_service", 0)
		self.assertIn(request, [r.name for r in routing.nursing_worklist()])
		routing.mark_done(request, "Given IM")
		done = frappe.db.get_value("Service Request", request, ["status", "ke_done_note"], as_dict=True)
		self.assertEqual(done.status, "completed-Request Status")
		self.assertEqual(done.ke_done_note, "Given IM")
		self.assertEqual(routing.open_nursing_items([request]), [])
		with self.assertRaises(frappe.ValidationError):
			routing.mark_done(request)


class TestVitalsHistoryAndSummary(ConsultationCase):
	def test_history_oldest_first(self):
		for temp in (37.0, 38.5):
			frappe.get_doc(
				{
					"doctype": "Vital Signs",
					"patient": self.patient,
					"signs_date": today(),
					"temperature": temp,
				}
			).insert(ignore_permissions=True)
		rows = consultation.vitals_history(self.patient)
		self.assertEqual([flt(r.temperature) for r in rows][-2:], [37.0, 38.5])

	def test_visit_summary(self):
		doc = self.encounter(lab=False, drug=True)
		doc.ke_chief_complaint = "Cough"
		doc.save()
		summary = printing.visit_summary(frappe.get_doc("Patient Visit", self.visit.name))
		self.assertTrue(summary.allowed)
		self.assertEqual(summary.record.encounters[0].doc.name, doc.name)
		self.assertTrue(summary.record.encounters[0].medicines)
		html = frappe.get_print("Patient Visit", self.visit.name, "Visit Summary")
		self.assertIn("Cough", html)


class TestCounterPrescription(IntegrationTestCase):
	def test_quantity_worked_out_and_pom_needs_prescriber(self):
		item = "DRG-PCM500"
		medication = frappe.db.get_value("Medication Linked Item", {"item": item}, "parent")
		if not medication:
			self.skipTest("needs the demo's paracetamol")
		tid, five = _dosage("KE Test TID", 3), _duration(5)
		items = pharmacy.counter_quantities([{"item_code": item, "dosage": tid, "period": five}])
		self.assertEqual(items[0]["qty"], 15)
		self.assertIn(tid, items[0]["instructions"])
		frappe.db.set_value("Medication", medication, "ke_prescription_only", 1)
		self.assertEqual(pharmacy.prescription_only(items), [item])
		with self.assertRaises(frappe.ValidationError):
			pharmacy.counter_sale(items, walk_in_name="POM Test")
		out = pharmacy.counter_sale(
			items,
			walk_in_name="POM Test",
			prescriber_name="Dr A Test",
			prescriber_reg="A1234",
			prescription_date=today(),
		)
		si = frappe.get_doc("Sales Invoice", out["invoice"])
		self.assertEqual(si.ke_prescriber_reg, "A1234")
		self.assertEqual(si.items[0].qty, 15)
		frappe.db.rollback()


class TestDiagnosisIsATable(IntegrationTestCase):
	def test_consultation_diagnosis_has_columns(self):
		"""v0.45.1: on Marley's pill picker (Table MultiSelect) the ICD-11 setup
		threw and the consultation opened blank; it is a table with columns."""
		meta = frappe.get_meta("Patient Encounter")
		self.assertEqual(meta.get_field("diagnosis").fieldtype, "Table")
		row = frappe.get_meta("Patient Encounter Diagnosis")
		self.assertTrue(row.get_field("ke_icd11_code").in_list_view)
