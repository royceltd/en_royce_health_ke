# Copyright (c) 2026, Royce Technologies LTD and Contributors
# See license.txt

import os
import tempfile

import frappe
from frappe.core.doctype.data_import.importer import build_fields_dict_for_column_matching
from frappe.tests import IntegrationTestCase

from royce_health_ke.migration import pharmacy_templates as templates


class IntegrationTestPharmacyTemplates(IntegrationTestCase):
	def test_every_header_is_one_data_import_matches(self):
		for upload in templates.UPLOADS:
			known = build_fields_dict_for_column_matching(upload["doctype"])
			for header in templates.headers(upload):
				self.assertIn(header, known, f"{upload['file']}: {header}")

	def test_workbooks_and_opening_csv(self):
		from openpyxl import load_workbook

		with tempfile.TemporaryDirectory() as out:
			paths = templates.build(out)
			self.assertEqual(len(paths), len(templates.UPLOADS) + 2)
			for upload in templates.UPLOADS:
				wb = load_workbook(os.path.join(out, f"{upload['file']}.xlsx"))
				self.assertEqual(wb.active.title, "Upload")  # the sheet Data Import reads
				self.assertEqual(wb.sheetnames, ["Upload", "Example", "Notes", "Lists"])
				self.assertEqual(wb["Upload"].max_row, 1)  # headers only
				width = len(upload["columns"])
				for row in wb["Example"].iter_rows(min_row=2, values_only=True):
					self.assertEqual(len(row), width)

			self.assertEqual(templates.read_opening_csv(os.path.join(out, "6 Opening Stock.csv")), [])
			rows = templates.read_opening_csv(os.path.join(out, "6 Opening Stock - Example.csv"))
			self.assertEqual(len(rows), 4)
			fields = {f.fieldname for f in frappe.get_meta("Stock Reconciliation Item").fields}
			for row in rows:
				self.assertLessEqual(set(row), fields)
				self.assertEqual(row["use_serial_batch_fields"], "1")
