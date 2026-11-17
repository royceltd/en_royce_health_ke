# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Outpatient flow feedback (v0.34): height in centimetres, one contact
number, sub-counties by county, fields hidden on the consultation, and the
insurance member number typed at check-in."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, add_to_date, today

from royce_health_ke import forms, growth, identity, visits
from royce_health_ke.kenya import COUNTIES, SUB_COUNTIES
from royce_health_ke.test_growth import synthetic_tables
from royce_health_ke.test_visits import make_patient


class TestHeightInCentimetres(IntegrationTestCase):
	def setUp(self):
		self.patient = make_patient()

	def vitals(self, **values):
		return frappe.get_doc(
			{"doctype": "Vital Signs", "patient": self.patient, "signs_date": today(), **values}
		).insert(ignore_permissions=True)

	def test_cm_fills_metres_and_bmi(self):
		vs = self.vitals(ke_height_cm=170, weight=72.25)
		self.assertAlmostEqual(vs.height, 1.7)
		self.assertEqual(vs.bmi, 25.0)

	def test_metres_only_gets_cm(self):
		vs = self.vitals(height=1.65, weight=60)
		self.assertEqual(vs.ke_height_cm, 165.0)

	def test_metres_typed_as_cm_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			self.vitals(ke_height_cm=1.7)

	def test_child_growth_uses_cm(self):
		growth._tables = synthetic_tables()
		self.addCleanup(setattr, growth, "_tables", None)
		child = frappe.get_doc(
			{
				"doctype": "Patient",
				"first_name": "Growth",
				"last_name": f"Cm {frappe.generate_hash(length=6)}",
				"sex": "Male",
				"dob": add_to_date(today(), days=-300),
			}
		).insert(ignore_permissions=True)
		by_cm = frappe.get_doc(
			{
				"doctype": "Vital Signs",
				"patient": child.name,
				"signs_date": today(),
				"weight": 6.5,
				"ke_height_cm": 75,
			}
		).insert(ignore_permissions=True)
		self.assertEqual(by_cm.ke_wflh_z, -3.5)


class TestRegistrationAndForms(IntegrationTestCase):
	def test_every_county_has_its_sub_counties(self):
		self.assertEqual(set(SUB_COUNTIES), set(COUNTIES))
		self.assertEqual(sum(len(s) for s in SUB_COUNTIES.values()), 290)
		self.assertIn("Njoro", identity.sub_counties("Nakuru"))
		self.assertEqual(identity.sub_counties("Nowhere"), [])

	def test_fields_hidden_once(self):
		forms.apply()
		meta = frappe.get_meta("Patient Encounter")
		for fieldname in ("symptoms", "appointment_type", "source"):
			self.assertTrue(meta.get_field(fieldname).hidden, fieldname)
		self.assertFalse(meta.get_field("appointment_type").reqd)
		self.assertTrue(frappe.get_meta("Patient").get_field("phone").hidden)
		self.assertTrue(frappe.get_meta("Vital Signs").get_field("height").hidden)
		# a field the hospital shows again stays shown
		frappe.db.set_value(
			"Property Setter",
			{"doc_type": "Patient", "field_name": "phone", "property": "hidden"},
			"value",
			"0",
		)
		forms.apply()
		frappe.clear_cache(doctype="Patient")
		self.assertFalse(frappe.get_meta("Patient").get_field("phone").hidden)


class TestMemberNumberTyped(IntegrationTestCase):
	def setUp(self):
		self.company = frappe.db.get_single_value(
			"Global Defaults", "default_company"
		) or frappe.db.get_value("Company", {}, "name")
		self.payor = frappe.db.get_value("Insurance Payor", {}, "name")
		if not self.payor:
			self.skipTest("needs an Insurance Payor (load the demo)")
		self.patient = make_patient()

	def insured(self, **values):
		return frappe.get_doc(
			{
				"doctype": "Patient Visit",
				"patient": self.patient,
				"company": self.company,
				"visit_type": "Lab only",
				"payment_method": "Insurance",
				"insurance_payor": self.payor,
				**values,
			}
		).insert(ignore_permissions=True)

	def test_returning_member_with_a_renewed_card(self):
		v = self.insured(member_number="R-100", policy_expiry=add_days(today(), 10))
		policy = v.insurance_policy
		visits.complete(v.name)
		# the card was renewed: the typed date extends the same policy
		renewed = add_days(today(), 400)
		v2 = self.insured(member_number="R-100", policy_expiry=renewed, visit_date=add_days(today(), 1))
		self.assertEqual(v2.insurance_policy, policy)
		self.assertEqual(
			str(frappe.db.get_value("Patient Insurance Policy", policy, "policy_expiry_date")), str(renewed)
		)
		self.assertIn("ke_relation", visits.patient_policies(self.patient)[0])

	def test_earlier_date_does_not_shorten_cover(self):
		v = self.insured(member_number="R-200", policy_expiry=add_days(today(), 300))
		visits.complete(v.name)
		self.insured(
			member_number="R-200", policy_expiry=add_days(today(), 30), visit_date=add_days(today(), 1)
		)
		self.assertEqual(
			str(frappe.db.get_value("Patient Insurance Policy", v.insurance_policy, "policy_expiry_date")),
			str(add_days(today(), 300)),
		)


class TestFormsOnAFreshSite(IntegrationTestCase):
	def test_hidden_field_made_optional_first(self):
		"""A fresh site has none of our property setters: applying them must not
		hide a field that is still mandatory (install failed on a new site)."""
		frappe.db.delete(
			"Property Setter",
			{
				"doc_type": "Patient Encounter",
				"field_name": "appointment_type",
				"property": ["in", ("hidden", "reqd")],
			},
		)
		frappe.clear_cache(doctype="Patient Encounter")
		forms.apply()
		field = frappe.get_meta("Patient Encounter").get_field("appointment_type")
		self.assertEqual((field.hidden, field.reqd), (1, 0))
