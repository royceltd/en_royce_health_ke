# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Casualty (Bethesda, PDF (12) points 6-7): sent from triage, a casualty bed,
the Casualty tabs, admission to a ward, and not counted as an admission."""

import frappe

from royce_health_ke import casualty, dashboards, flow, inpatient
from royce_health_ke.test_inpatient import InpatientCase


def _casualty_unit(company):
	name = frappe.db.get_value("Healthcare Service Unit", {"ke_casualty": 1, "is_group": 1})
	if not name:
		parent = frappe.db.get_value(
			"Healthcare Service Unit", {"is_group": 1, "company": company}, "name", order_by="lft"
		)
		name = (
			frappe.get_doc(
				{
					"doctype": "Healthcare Service Unit",
					"healthcare_service_unit_name": f"_Test Casualty {frappe.generate_hash(length=4)}",
					"is_group": 1,
					"parent_healthcare_service_unit": parent,
					"company": company,
					"ke_casualty": 1,
				}
			)
			.insert(ignore_permissions=True)
			.name
		)
	return name


def _casualty_bed(unit, unit_type, company):
	beds = inpatient.vacant_beds(unit)
	if beds:
		return beds[0].name
	return (
		frappe.get_doc(
			{
				"doctype": "Healthcare Service Unit",
				"healthcare_service_unit_name": f"_Test CAS Bed {frappe.generate_hash(length=6)}",
				"parent_healthcare_service_unit": unit,
				"is_group": 0,
				"inpatient_occupancy": 1,
				"service_unit_type": unit_type,
				"company": company,
				"occupancy_status": "Vacant",
			}
		)
		.insert(ignore_permissions=True)
		.name
	)


class TestCasualty(InpatientCase):
	def setUp(self):
		super().setUp()
		casualty.seed()
		self.unit = _casualty_unit(self.company)
		self.bed = _casualty_bed(self.unit, inpatient._bed_type(self.ward), self.company)

	def sent(self, note="Road traffic accident"):
		visit = frappe.get_doc("Patient Visit", self.visit.name)
		flow.send(visit, "Casualty", note=note)
		ip = frappe.db.get_value(
			"Inpatient Record", {"patient": visit.patient, "status": "Admission Scheduled"}, "name"
		)
		self.assertTrue(ip, "sent to casualty: the patient waits on the Casualty list")
		return ip

	def test_triage_to_casualty_bed_and_tabs(self):
		self.assertIn(self.unit, casualty.units())
		self.assertNotIn(self.unit, inpatient.wards())
		ip = self.sent()
		doc = frappe.get_doc("Inpatient Record", ip)
		self.assertEqual(
			(doc.ke_casualty, doc.ke_ward, doc.ke_patient_visit), (1, self.unit, self.visit.name)
		)
		self.assertIn("Road traffic accident", doc.ke_admission_reason)
		listed = inpatient.admission_list(casualty=1)
		self.assertIn(ip, [r.name for r in listed["waiting"]])
		self.assertNotIn(ip, [r.name for r in inpatient.admission_list()["waiting"]])

		inpatient.admit(ip, self.bed)
		ws = inpatient.workspace(ip)
		self.assertEqual(ws["casualty"], 1)
		self.assertIn("Casualty Drugs", [t["label"] for t in ws["tabs"]])
		self.assertIn(ip, [r.name for r in inpatient.admission_list(casualty=1)["on_ward"]])
		self.assertNotIn(ip, [r.name for r in inpatient.admission_list()["on_ward"]])
		# the patient is already in casualty: sending again keeps the one stay
		self.assertEqual(casualty.open_stay(frappe.get_doc("Patient Visit", self.visit.name)), ip)

	def test_admitted_to_a_ward_is_an_admission(self):
		ip = self.sent()
		inpatient.admit(ip, self.bed)
		inpatient.request_transfer(ip, self.ward, "Needs IV antibiotics", "Urgent")
		from royce_health_ke.test_inpatient import _free_bed

		inpatient.receive_transfer(ip, _free_bed(self.ward))
		self.assertEqual(frappe.db.get_value("Inpatient Record", ip, "ke_casualty"), 0)
		self.assertEqual(inpatient.workspace(ip)["casualty"], 0)

	def test_not_counted_as_admissions(self):
		self.assertEqual(casualty.not_casualty_filter({})["ke_casualty"], 0)
		self.assertNotIn(self.bed, [b.name for b in dashboards.beds(self.company)])

	def test_casualty_bed_by_the_hour_on_the_bill(self):
		unit_type = frappe.db.get_value("Healthcare Service Unit", self.bed, "service_unit_type")
		hours, billable = frappe.db.get_value(
			"Healthcare Service Unit Type", unit_type, ["no_of_hours", "is_billable"]
		)
		# charged by the hour for this test (casualty beds are free by default)
		frappe.db.set_value("Healthcare Service Unit Type", unit_type, {"no_of_hours": 1, "is_billable": 1})
		try:
			ip = self.sent()
			inpatient.admit(ip, self.bed)
			doc = frappe.get_doc("Inpatient Record", ip)
			from frappe.utils import add_to_date, now_datetime

			doc.inpatient_occupancies[-1].db_set(
				"check_in", add_to_date(now_datetime(), hours=-3, minutes=-10)
			)
			doc.reload()
			bed = next(
				line for line in inpatient.money(doc, detail=True)["lines"] if line["what"].startswith("Bed")
			)
			self.assertEqual(bed["qty"], 4)
		finally:
			frappe.db.set_value(
				"Healthcare Service Unit Type", unit_type, {"no_of_hours": hours, "is_billable": billable}
			)
