# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Bethesda's feedback of 20 Nov 2026 (v0.51): triage fields, the
Observation tab side by side, OPD patients by payment mode."""

import json

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import today

from royce_health_ke.kenya_health.report.opd_patients_by_payment_mode import (
	opd_patients_by_payment_mode as report,
)


class TestTriageFields(IntegrationTestCase):
	def test_examination_findings_off_triage(self):
		meta = frappe.get_meta("Vital Signs")
		for field in ("tongue", "abdomen", "reflexes"):
			self.assertTrue(meta.get_field(field).hidden, field)
		self.assertFalse(meta.get_field("temperature").hidden)


class TestObservationTab(IntegrationTestCase):
	def test_side_by_side_in_their_order(self):
		meta = frappe.get_meta("Patient Encounter")
		names = [f.fieldname for f in meta.fields]
		start = names.index("ke_tab_observation")
		end = next(i for i in range(start + 1, len(names)) if meta.fields[i].fieldtype == "Tab Break")
		tab = [f for f in meta.fields[start:end] if not f.hidden]
		# one row per section: left | right
		rows, row = [], None
		for f in tab:
			if f.fieldtype == "Section Break":
				row = [[]]
				rows.append(row)
				self.assertFalse(f.label, f"{f.fieldname} has a heading")
			elif f.fieldtype == "Column Break":
				row.append([])
			elif row is not None:
				row[-1].append(f.fieldname)
		layout = [[col for col in r if col] for r in rows]
		self.assertEqual(
			layout,
			[
				[["ke_chief_complaint"], ["ke_hpi"]],
				[["ke_review_of_systems"], ["ke_hx_medical", "ke_hx_surgical"]],
				[["ke_hx_family"], ["ke_hx_social"]],
				[["ke_obs_gynae"]],
				[["ke_examination"]],
			],
		)
		self.assertFalse(meta.get_field("ke_history_section").description)
		self.assertTrue(meta.get_field("ke_hx_allergies").hidden)


class TestPaymentModeReport(IntegrationTestCase):
	def test_counts_per_mode(self):
		company = frappe.db.get_value("Company", {}, "name")
		visits = [
			frappe._dict(patient="A", payment_method="Cash"),
			frappe._dict(patient="B", payment_method="Cash"),
			frappe._dict(patient="A", payment_method="Cash"),
			frappe._dict(
				patient="C", payment_method="Insurance", insurance_payor="SHA", insurance_plan="SHA - PHC"
			),
			frappe._dict(
				patient="D", payment_method="Insurance", insurance_payor="Mlima", insurance_plan=None
			),
		]
		original = frappe.get_all
		frappe.get_all = lambda *a, **k: visits if a and a[0] == "Patient Visit" else original(*a, **k)
		try:
			_columns, data, _msg, chart = report.execute({"company": company, "from_date": today()})
		finally:
			frappe.get_all = original
		self.assertEqual(
			[(r["payment_mode"], r["visits"], r["patients"]) for r in data],
			[("Cash", 3, 2), ("Mlima", 1, 1), ("SHA - PHC", 1, 1)],
		)
		self.assertEqual(data[0]["share"], 60.0)
		self.assertEqual(chart["data"]["labels"][0], "Cash")

	def test_runs_on_the_site(self):
		_columns, data, _msg, _chart = report.execute({"from_date": "2026-01-01", "to_date": today()})
		self.assertIsInstance(data, list)
		json.dumps(data)
