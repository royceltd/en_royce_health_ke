# Copyright (c) 2026, Royce Technologies LTD and Contributors
# See license.txt

import json

from frappe.tests import IntegrationTestCase

from royce_health_ke.setup.marley_fixes import corrected_selected_fields

SHIPPED_LAB_TEST = json.dumps(
	[
		{"label": "Test Template", "fieldname": "template", "fieldtype": "Link"},
		{"label": "Normal Test Result", "fieldname": "normal_test_items", "fieldtype": "Table"},
		{"label": "Comments", "fieldname": "lab_test_comment", "fieldtype": "Table"},
	]
)


class IntegrationTestMarleyFixes(IntegrationTestCase):
	def test_lab_test_comment_gets_its_real_fieldtype(self):
		entries = json.loads(corrected_selected_fields("Lab Test", SHIPPED_LAB_TEST))
		by_name = {e["fieldname"]: e for e in entries}
		self.assertEqual(by_name["lab_test_comment"]["fieldtype"], "Text")
		self.assertEqual(by_name["normal_test_items"]["fieldtype"], "Table")
		self.assertEqual(len(entries), 3)  # the hospital's selection is kept

	def test_correct_settings_are_left_alone(self):
		fixed = corrected_selected_fields("Lab Test", SHIPPED_LAB_TEST)
		self.assertIsNone(corrected_selected_fields("Lab Test", fixed))

	def test_unknown_or_empty_input_is_ignored(self):
		self.assertIsNone(corrected_selected_fields("No Such DocType", SHIPPED_LAB_TEST))
		self.assertIsNone(corrected_selected_fields("Lab Test", ""))
		self.assertIsNone(corrected_selected_fields("Lab Test", "not json"))
