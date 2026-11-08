# Copyright (c) 2026, Royce Technologies LTD and Contributors
# See license.txt

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from royce_health_ke.printing import DEFAULT_PRINT_FORMATS, age, flag, set_default_print_formats


class IntegrationTestPrinting(IntegrationTestCase):
	def test_flags_only_numbers_outside_numeric_ranges(self):
		self.assertEqual(flag("12.5", "4.0 - 11.0"), "H")
		self.assertEqual(flag("3.1", "4.0 - 11.0"), "L")
		self.assertEqual(flag("6.2", "4.0 - 11.0"), "")
		self.assertEqual(flag("1,200", "150 to 400"), "H")
		self.assertEqual(flag("9", "<5"), "H")
		self.assertEqual(flag("60", "> 90"), "L")
		self.assertEqual(flag("11.4", "Male: 13.0 - 17.0<br>Female: 12.0 - 15.5"), "L")
		# never guess: text results, text ranges, empty values
		self.assertEqual(flag("P. falciparum ++", "No parasites seen"), "")
		self.assertEqual(flag("Positive", "Negative"), "")
		self.assertEqual(flag("", "4 - 11"), "")
		self.assertEqual(flag("7", ""), "")

	def test_age_reads_like_a_clinician_writes_it(self):
		self.assertEqual(age("1990-06-15", "2026-11-08"), "36 years")
		self.assertEqual(age("2026-03-01", "2026-11-08"), "8 months")
		self.assertEqual(age("2025-11-20", "2026-11-08"), "11 months")
		self.assertEqual(age("2026-11-01", "2026-11-08"), "7 days")
		self.assertEqual(age(None), "")

	def test_defaults_set_but_a_clients_choice_is_kept(self):
		frappe.make_property_setter(
			{
				"doctype": "Lab Test",
				"doctype_or_field": "DocType",
				"property": "default_print_format",
				"value": "Lab Test Print",  # Marley's own: ours replaces it
				"property_type": "Data",
			},
			is_system_generated=False,
		)
		frappe.make_property_setter(
			{
				"doctype": "Patient Encounter",
				"doctype_or_field": "DocType",
				"property": "default_print_format",
				"value": "Prescription",  # a client's choice: kept
				"property_type": "Data",
			},
			is_system_generated=False,
		)
		set_default_print_formats()

		def default(doctype):
			return frappe.db.get_value(
				"Property Setter",
				{"doc_type": doctype, "doctype_or_field": "DocType", "property": "default_print_format"},
				"value",
			)

		self.assertEqual(default("Lab Test"), DEFAULT_PRINT_FORMATS["Lab Test"])
		self.assertEqual(default("Patient Encounter"), "Prescription")

	def test_every_format_renders_on_a_real_record(self):
		cases = [
			("Lab Test", "Laboratory Report"),
			("Patient Encounter", "Consultation Summary"),
			("Patient Encounter", "Prescription"),
			("Discharge Summary", "Patient Discharge Summary"),
			("Observation", "Radiology Report"),
			("Clinical Procedure", "Operation Note"),
			("Patient", "Patient Card"),
			("Diagnostic Report", "Diagnostic Results"),
		]
		rendered = 0
		for doctype, print_format in cases:
			name = frappe.db.get_value(doctype, {}, "name")
			if not name:
				continue
			html = frappe.get_print(doctype, name, print_format)
			self.assertIn("hx-doc", html, print_format)
			self.assertNotIn("Traceback", html)
			rendered += 1
		if not rendered:
			self.skipTest("no clinical records on this site")

	def test_diagnostic_rows_panels_flags_and_text(self):
		from royce_health_ke.printing import diagnostic_rows

		data = [
			{
				"has_component": True,
				"observation": "OBS-FBC",
				"display_name": "Full Blood Count",
				"OBS-FBC": [
					{
						"observation": {
							"observation_template": "Haemoglobin",
							"result": "9.1",
							"permitted_unit": "g/dL",
							"reference": "12.0 - 15.5",
						}
					},
					{"observation": {"observation_template": "WBC", "result": "6.0", "reference": "4 - 11"}},
					{
						"observation": {
							"observation_template": "Platelets",
							"result": "",
							"reference": "150 - 400",
						}
					},
				],
			},
			{
				"observation": {
					"observation_template": "Urine microscopy",
					"result": "<p>Pus cells 2-4/hpf, no casts seen.</p>",
				}
			},
		]
		doc = frappe._dict(name="DIA-TEST")
		with patch(
			"healthcare.healthcare.doctype.observation.observation.get_observation_details",
			return_value=(data, 4),
		):
			rows = diagnostic_rows(doc)
		self.assertEqual(
			[r.name for r in rows],
			["Full Blood Count", "Haemoglobin", "WBC", "Platelets", "Urine microscopy"],
		)
		self.assertTrue(rows[0].heading)
		hb, wbc, plt, urine = rows[1:]
		self.assertEqual((hb.flag, hb.indent), ("L", True))
		self.assertEqual(wbc.flag, "")
		self.assertTrue(plt.pending)
		self.assertTrue(urine.text)
		self.assertEqual(urine.flag, "")

	def test_patient_card_band_on_the_patient_itself(self):
		from royce_health_ke.printing import patient_band

		name = frappe.db.get_value("Patient", {}, "name")
		if not name:
			self.skipTest("no patients on this site")
		band = patient_band(frappe.get_doc("Patient", name))
		self.assertTrue(band.name)
