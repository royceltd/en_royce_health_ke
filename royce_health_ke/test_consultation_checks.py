# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""v0.43.1 (IT demo, 17 Nov 2026): lab tests ordered as Observations are
refused, the Observation tab is filled before requests, requests without a
price are named, the residence no longer blanks the county, Marley's
registration SMS without a gateway is switched off, and the lab grid shows the
Lab Test column."""

import frappe
from frappe.tests import IntegrationTestCase

from royce_health_ke import consultation, forms, identity
from royce_health_ke.setup import marley_fixes
from royce_health_ke.test_consultation import ConsultationCase

OBSERVED = {
	"ke_chief_complaint": "Fever for 3 days",
	"ke_hpi": "Evening fevers, no cough",
	"ke_examination": "Temp 38.4, no rash",
}


def _settings(**values):
	for field, value in values.items():
		frappe.db.set_single_value("Kenya Health Settings", field, value)


class TestLabRows(ConsultationCase):
	def test_lab_test_as_observation_is_refused(self):
		name = f"Haemogram Obs {frappe.generate_hash(length=5)}"
		frappe.get_doc(
			{
				"doctype": "Observation Template",
				"observation": name,
				"observation_category": "Laboratory",
				"permitted_data_type": "Quantity",
			}
		).insert(ignore_permissions=True)
		enc = self.encounter(lab=False)
		enc.append("lab_test_prescription", {"observation_template": name})
		with self.assertRaisesRegex(frappe.ValidationError, "not an imaging exam"):
			enc.save(ignore_permissions=True)

	def test_imaging_exam_is_allowed(self):
		imaging = frappe.db.get_value("Observation Template", {"observation_category": "Imaging"}, "name")
		if not imaging:
			self.skipTest("needs the demo's imaging exams")
		enc = self.encounter(lab=False)
		enc.append("lab_test_prescription", {"observation_template": imaging})
		enc.save(ignore_permissions=True)


class TestObservationFirst(ConsultationCase):
	def setUp(self):
		super().setUp()
		frappe.flags.ke_test_observation_gate = True
		_settings(
			observation_before_requests=1,
			obs_need_complaint=1,
			obs_need_hpi=1,
			obs_need_ros=0,
			obs_need_examination=1,
		)

	def tearDown(self):
		frappe.flags.ke_test_observation_gate = False
		super().tearDown()

	def test_requests_wait_for_the_observation(self):
		enc = self.encounter()
		with self.assertRaisesRegex(frappe.ValidationError, "Record the observation"):
			consultation.send_requests(enc.name)
		self.assertFalse(frappe.db.exists("Service Request", {"order_group": enc.name}))
		# saving without placing orders is fine: the doctor can come back to it
		enc.reload()
		enc.ke_obs_gynae = "G1P0"
		enc.save(ignore_permissions=True)

		enc.update({**OBSERVED, "ke_hpi": ""})
		enc.save(ignore_permissions=True)
		with self.assertRaisesRegex(frappe.ValidationError, "History of Presenting Illness"):
			consultation.send_requests(enc.name)

		enc.reload()
		enc.update(OBSERVED)
		enc.save(ignore_permissions=True)
		consultation.send_requests(enc.name)
		self.assertTrue(frappe.db.exists("Service Request", {"order_group": enc.name, "docstatus": 1}))

	def test_complete_also_waits(self):
		enc = self.encounter(lab=False, drug=True)
		with self.assertRaisesRegex(frappe.ValidationError, "Record the observation"):
			consultation.complete(enc.name)
		self.assertEqual(frappe.db.get_value("Patient Encounter", enc.name, "docstatus"), 0)

	def test_no_orders_needs_no_observation(self):
		enc = self.encounter(lab=False)
		consultation.complete(enc.name)
		self.assertEqual(frappe.db.get_value("Patient Encounter", enc.name, "docstatus"), 1)

	def test_casualty_is_exempt(self):
		frappe.db.set_value("Patient Visit", self.visit.name, "visit_type", "Casualty")
		enc = self.encounter()
		consultation.send_requests(enc.name)
		self.assertTrue(frappe.db.exists("Service Request", {"order_group": enc.name, "docstatus": 1}))

	def test_switched_off(self):
		_settings(observation_before_requests=0)
		enc = self.encounter()
		consultation.send_requests(enc.name)
		self.assertTrue(frappe.db.exists("Service Request", {"order_group": enc.name, "docstatus": 1}))


class TestUnpriced(ConsultationCase):
	def test_request_without_a_price_is_named(self):
		name = f"Unpriced Test {frappe.generate_hash(length=5)}"
		frappe.get_doc(
			{
				"doctype": "Lab Test Template",
				"lab_test_name": name,
				"lab_test_code": name,
				"lab_test_group": "Laboratory",
				"department": frappe.db.get_value("Medical Department", {}, "name"),
				"lab_test_template_type": "Single",
				"is_billable": 1,
				"lab_test_rate": 300,
			}
		).insert(ignore_permissions=True)
		# no price on the price list the patient is billed from
		frappe.db.delete("Item Price", {"item_code": frappe.db.get_value("Lab Test Template", name, "item")})
		enc = self.encounter()
		enc.append("lab_test_prescription", {"lab_test_code": name})
		enc.save(ignore_permissions=True)
		info = consultation.send_requests(enc.name)
		self.assertEqual(info["unpriced"], [name])


class TestRegistration(IntegrationTestCase):
	def test_residence_fills_only_empty_county(self):
		place = frappe.get_doc(
			{"doctype": "Residence", "residence_name": f"Estate {frappe.generate_hash(length=5)}"}
		).insert(ignore_permissions=True)
		doc = frappe._dict(ke_residence=place.name, ke_county="Nakuru", ke_sub_county="Naivasha")
		identity.fill_from_residence(doc)
		self.assertEqual((doc.ke_county, doc.ke_sub_county), ("Nakuru", "Naivasha"))

		place.county, place.sub_county = "Kisumu", "Kisumu Central"
		place.save(ignore_permissions=True)
		doc = frappe._dict(ke_residence=place.name)
		identity.fill_from_residence(doc)
		self.assertEqual((doc.ke_county, doc.ke_sub_county), ("Kisumu", "Kisumu Central"))

	def test_county_no_longer_fetched_by_the_form(self):
		meta = frappe.get_meta("Patient")
		self.assertFalse(meta.get_field("ke_county").fetch_from)
		self.assertFalse(meta.get_field("ke_sub_county").fetch_from)

	def test_registration_sms_off_without_a_gateway(self):
		frappe.db.set_single_value("SMS Settings", "sms_gateway_url", "")
		frappe.db.set_single_value("Healthcare Settings", "send_registration_msg", 1)
		self.assertTrue(marley_fixes.fix_registration_sms())
		self.assertFalse(frappe.db.get_single_value("Healthcare Settings", "send_registration_msg"))
		# with a gateway, the hospital's choice stands
		frappe.db.set_single_value("SMS Settings", "sms_gateway_url", "https://sms.example.test/send")
		frappe.db.set_single_value("Healthcare Settings", "send_registration_msg", 1)
		self.assertFalse(marley_fixes.fix_registration_sms())
		self.assertTrue(frappe.db.get_single_value("Healthcare Settings", "send_registration_msg"))
		frappe.db.rollback()


class TestForms(IntegrationTestCase):
	def test_lab_grid_and_invite_default(self):
		forms.apply()
		lab = frappe.get_meta("Lab Prescription")
		self.assertEqual(lab.get_field("lab_test_code").label, "Lab Test")
		self.assertTrue(lab.get_field("lab_test_code").in_list_view)
		self.assertEqual(lab.get_field("observation_template").label, "Imaging")
		self.assertEqual(frappe.get_meta("Patient").get_field("invite_user").default, "0")
