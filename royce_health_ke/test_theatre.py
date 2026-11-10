# Copyright (c) 2026, Royce Technologies LTD and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase

from royce_health_ke.theatre import (
	DEFAULT_COUNTS,
	POST_OP,
	SIGN_IN,
	SIGN_OUT,
	SYSTEMS_REVIEW,
	TIME_OUT,
	WARD_PREP,
	lab_field,
	validate_anaesthesia,
	validate_checklist,
)

ANSWERS = {
	"si_site_marked": "Yes",
	"si_known_allergy": "No",
	"si_difficult_airway": "No",
	"si_blood_loss_risk": "No",
	"to_antibiotic": "Yes",
	"to_imaging": "Not applicable",
	"so_specimen_labelled": "Yes",
	"wp_dentures": "None",
	"wp_fasting": "Yes",
	"po_consciousness": "Alert",
	"po_pulse": 80,
	"po_bp_systolic": 120,
}


def answered(fields):
	return {f: ANSWERS.get(f, 1 if not f.endswith("_by") else "Someone") for f in fields}


class IntegrationTestTheatre(IntegrationTestCase):
	def test_phases_done_in_order_with_times(self):
		checklist = frappe.new_doc("Surgical Safety Checklist")
		checklist.update(answered(SIGN_IN))
		validate_checklist(checklist)
		self.assertEqual((checklist.sign_in_status, checklist.time_out_status), ("Done", "Pending"))
		self.assertTrue(checklist.sign_in_time)
		checklist.update(answered(TIME_OUT))
		validate_checklist(checklist)
		self.assertEqual(checklist.time_out_status, "Done")

	def test_unanswered_item_keeps_phase_pending(self):
		checklist = frappe.new_doc("Surgical Safety Checklist")
		checklist.update({**answered(SIGN_IN), "si_pulse_oximeter": 0})
		validate_checklist(checklist)
		self.assertEqual(checklist.sign_in_status, "Pending")

	def test_time_out_before_sign_in_is_refused(self):
		checklist = frappe.new_doc("Surgical Safety Checklist")
		checklist.update(answered(TIME_OUT))
		with self.assertRaises(frappe.ValidationError):
			validate_checklist(checklist)

	def test_ward_preparation_done_when_answered(self):
		checklist = frappe.new_doc("Surgical Safety Checklist")
		prep = answered(WARD_PREP)
		checklist.update({k: v for k, v in prep.items() if k != "wp_received_by"})
		validate_checklist(checklist)
		self.assertEqual(checklist.ward_prep_status, "Pending")
		checklist.wp_received_by = "Theatre nurse"
		validate_checklist(checklist)
		self.assertEqual(checklist.ward_prep_status, "Done")
		self.assertTrue(checklist.wp_handed_over_time and checklist.wp_received_time)

	def test_new_checklist_gets_the_count_lines(self):
		checklist = frappe.new_doc("Surgical Safety Checklist")
		validate_checklist(checklist)
		self.assertEqual([r.item for r in checklist.counts], [item for _c, item in DEFAULT_COUNTS])

	def _counted(self, end):
		checklist = frappe.new_doc("Surgical Safety Checklist")
		checklist.update({**answered(SIGN_IN), **answered(TIME_OUT), **answered(SIGN_OUT)})
		checklist.append(
			"counts", {"category": "Gauze", "item": "Swabs", "start_count": 10, "added": 5, "end_count": end}
		)
		checklist.update({"count_scrub_nurse": "A", "count_circulating_nurse": "B"})
		return checklist

	def test_sign_out_refuses_counts_that_dont_balance(self):
		checklist = self._counted(14)
		with self.assertRaises(frappe.ValidationError):
			validate_checklist(checklist)
		self.assertIn("1", checklist.counts[0].result)

	def test_balanced_counts_sign_out(self):
		checklist = self._counted(15)
		validate_checklist(checklist)
		self.assertEqual(checklist.counts[0].result, "Correct")
		self.assertEqual(checklist.sign_out_status, "Done")

	def test_counts_need_both_nurses(self):
		checklist = self._counted(15)
		checklist.count_circulating_nurse = None
		with self.assertRaises(frappe.ValidationError):
			validate_checklist(checklist)

	def test_post_op_only_after_sign_out(self):
		checklist = frappe.new_doc("Surgical Safety Checklist")
		checklist.update({**answered(SIGN_IN), **answered(POST_OP)})
		with self.assertRaises(frappe.ValidationError):
			validate_checklist(checklist)
		checklist.update({**answered(TIME_OUT), **answered(SIGN_OUT)})
		validate_checklist(checklist)
		self.assertEqual(checklist.post_op_status, "Done")

	def test_lab_names_map_to_the_assessment_fields(self):
		for name, field in (
			("Haemoglobin (Hb)", "lab_hb"),
			("HB", "lab_hb"),
			("Glycated haemoglobin (HbA1c)", None),
			("Mean cell haemoglobin (MCH)", None),
			("Haematocrit (PCV)", "lab_hct"),
			("Platelet count", "lab_plt"),
			("Mean platelet volume", None),
			("White Cell Count (WBC)", "lab_wbc"),
			("Prothrombin time (PT)", "lab_pt"),
			("INR", "lab_inr"),
			("APTT", "lab_aptt"),
			("Malaria Blood Slide (BS for MPS)", None),
		):
			self.assertEqual(lab_field(name), field, name)

	def test_anaesthesia_review_rows_gcs_and_times(self):
		record = frappe.new_doc("Anaesthesia Record")
		record.update({"gcs_e": 4, "gcs_m": 6, "gcs_v": 5})
		validate_anaesthesia(record)
		self.assertEqual(len(record.systems_review), sum(len(f) for _s, f in SYSTEMS_REVIEW))
		self.assertEqual(record.gcs_total, 15)
		record.gcs_m = 7
		with self.assertRaises(frappe.ValidationError):
			validate_anaesthesia(record)
		record.update(
			{"gcs_m": 6, "surgery_start": "2026-11-10 10:00:00", "surgery_end": "2026-11-10 09:00:00"}
		)
		with self.assertRaises(frappe.ValidationError):
			validate_anaesthesia(record)
