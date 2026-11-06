# Copyright (c) 2026, Royce Technologies LTD and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase

from royce_health_ke.codes import ICD11, code_value_name, parse_icd11_tabulation, set_coding, upsert_codes

# Trimmed from WHO's SimpleTabulation-ICD-11-MMS-en.txt (2026-01): a chapter
# (no code), a block (no code) and two coded categories.
TABULATION = (
	"Foundation URI\tLinearization URI\tCode\tBlockId\tTitle\tClassKind\tDepthInKind\n"
	"http://id.who.int/icd/entity/1435254666\thttp://id.who.int/icd/release/11/mms/1435254666\t\t\t"
	"Certain infectious or parasitic diseases\tchapter\t1\n"
	"http://id.who.int/icd/entity/588616678\thttp://id.who.int/icd/release/11/mms/588616678\t\tBlockL1-1A0\t"
	"- Gastroenteritis or colitis of infectious origin\tblock\t1\n"
	"x\thttp://id.who.int/icd/release/11/mms/1\t1F40\t\t- - - Malaria due to Plasmodium falciparum\tcategory\t1\n"
	"x\thttp://id.who.int/icd/release/11/mms/2\t1F40.Z\t\t- - - - Malaria due to Plasmodium falciparum, unspecified\tcategory\t2\n"
)


class IntegrationTestCodes(IntegrationTestCase):
	def test_tabulation_keeps_only_coded_categories(self):
		rows = list(parse_icd11_tabulation(TABULATION))
		self.assertEqual([r[0] for r in rows], ["1F40", "1F40.Z"])
		self.assertEqual(rows[1][1], "Malaria due to Plasmodium falciparum, unspecified")
		self.assertEqual(rows[1][3], 2)

	def test_upsert_creates_then_updates(self):
		rows = [("ZZ99.9", "Test condition", None, 1)]
		self.assertEqual(upsert_codes(ICD11, rows), {"created": 1, "updated": 0})
		self.assertEqual(upsert_codes(ICD11, rows), {"created": 0, "updated": 0})
		self.assertEqual(upsert_codes(ICD11, [("ZZ99.9", "Renamed", None, 1)]), {"created": 0, "updated": 1})
		cv = frappe.get_doc("Code Value", code_value_name(ICD11, "ZZ99.9"))
		self.assertEqual((cv.display, cv.system_uri), ("Renamed", "http://id.who.int/icd/release/11/mms"))

	def test_set_coding_replaces_the_systems_earlier_code(self):
		diagnosis = frappe.get_doc({"doctype": "Diagnosis", "diagnosis": "Test coding diagnosis"})
		set_coding(diagnosis, ICD11, "ZZ98.1", "First")
		set_coding(diagnosis, ICD11, "ZZ98.2", "Second")
		self.assertEqual([r.code for r in diagnosis.codification_table], ["ZZ98.2"])
		self.assertEqual(diagnosis.codification_table[0].system, "http://id.who.int/icd/release/11/mms")
