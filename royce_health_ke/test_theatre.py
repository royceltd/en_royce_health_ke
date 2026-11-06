# Copyright (c) 2026, Royce Technologies LTD and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase

from royce_health_ke.theatre import SIGN_IN, TIME_OUT, validate_checklist

ANSWERS = {
	"si_site_marked": "Yes",
	"si_known_allergy": "No",
	"si_difficult_airway": "No",
	"si_blood_loss_risk": "No",
	"to_antibiotic": "Yes",
	"to_imaging": "Not applicable",
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
