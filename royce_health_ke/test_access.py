# Copyright (c) 2026, Royce Technologies LTD and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase

from royce_health_ke import access


class IntegrationTestAccess(IntegrationTestCase):
	def setUp(self):
		frappe.db.set_single_value("Kenya Health Settings", "track_record_access", 1)
		frappe.db.value_cache.pop("Kenya Health Settings", None)
		self.patient = (
			frappe.get_doc(
				{
					"doctype": "Patient",
					"first_name": "Akinyi",
					"last_name": f"AccessTest {frappe.generate_hash(length=6)}",
					"sex": "Female",
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

	def entries(self, **filters):
		return frappe.get_all(
			"Patient Record Access",
			filters={"patient": self.patient, **filters},
			fields=["reference_doctype", "action", "user", "patient_name"],
		)

	def test_opening_and_printing_are_logged_once_per_look(self):
		doc = frappe.get_doc("Patient", self.patient)
		frappe.cache.delete_keys(
			f"royce_health_ke:record_access:{frappe.session.user}:Patient:{self.patient}"
		)
		doc.run_method("onload")
		doc.run_method("onload")  # a refresh moments later
		views = self.entries(action="View")
		self.assertEqual(len(views), 1)
		self.assertEqual((views[0].reference_doctype, views[0].user), ("Patient", frappe.session.user))
		self.assertEqual(views[0].patient_name, doc.patient_name)
		doc.run_method("before_print")
		doc.run_method("before_print")
		self.assertEqual(len(self.entries(action="Print")), 2)  # every print counts

	def test_untracked_and_disabled(self):
		access._log(
			frappe._dict(doctype="Sales Invoice", name="X", patient=self.patient, is_new=lambda: False),
			"View",
		)
		self.assertEqual(self.entries(), [])
		frappe.db.set_single_value("Kenya Health Settings", "track_record_access", 0)
		frappe.db.value_cache.pop("Kenya Health Settings", None)  # per-request cache
		frappe.get_doc("Patient", self.patient).run_method("before_print")
		self.assertEqual(self.entries(), [])

	def test_entries_cannot_be_changed_or_deleted(self):
		frappe.get_doc("Patient", self.patient).run_method("before_print")
		entry = frappe.get_doc("Patient Record Access", {"patient": self.patient})
		entry.action = "View"
		with self.assertRaises(frappe.ValidationError):
			entry.save(ignore_permissions=True)
		with self.assertRaises(frappe.ValidationError):
			frappe.delete_doc("Patient Record Access", entry.name, ignore_permissions=True)

	def test_patient_can_still_be_deleted_and_trail_stays(self):
		frappe.get_doc("Patient", self.patient).run_method("before_print")
		frappe.delete_doc("Patient", self.patient, ignore_permissions=True, force=True)
		self.assertEqual(len(self.entries()), 1)
