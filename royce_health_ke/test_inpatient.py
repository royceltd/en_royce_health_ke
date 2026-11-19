# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Inpatient (Bethesda proposals, 18 Nov 2026): Admit to Ward from the
consultation, the ward's list and beds, the patient screen, ward-round
prescribing into the ward medication order, charging on issue, stopping a
drug, nursing charts, pre-authorisation and the record of the stay."""

import frappe
from frappe.utils import add_days, getdate, today

from royce_health_ke import charts, inpatient
from royce_health_ke.test_consultation import ConsultationCase


def _ward():
	wards = inpatient.wards()
	for ward in wards:
		if inpatient.vacant_beds(ward):
			return ward
	return None


class InpatientCase(ConsultationCase):
	def setUp(self):
		super().setUp()
		self.ward = _ward()
		if not self.ward:
			self.skipTest("needs a ward with a vacant bed (the demo's General Ward)")
		inpatient.seed()
		charts.seed()

	def admit_request(self, **values):
		enc = self.encounter(lab=False)
		return enc, inpatient.request_admission(
			encounter=enc.name,
			ward=self.ward,
			urgency=values.get("urgency", "Urgent"),
			admission_date=today(),
			reason=values.get("reason", "Severe malaria, needs IV artesunate"),
			notes="Start IV fluids",
			expected_days=3,
		)

	def admitted(self):
		_enc, ip = self.admit_request()
		bed = inpatient.vacant_beds(self.ward)[0].name
		inpatient.admit(ip, bed)
		return ip, bed


class TestAdmission(InpatientCase):
	def test_admit_to_ward_from_the_consultation(self):
		enc, ip = self.admit_request()
		doc = frappe.get_doc("Inpatient Record", ip)
		self.assertEqual(doc.status, "Admission Scheduled")
		self.assertEqual(doc.ke_ward, self.ward)
		self.assertEqual(doc.ke_urgency, "Urgent")
		self.assertEqual(doc.admission_encounter, enc.name)
		self.assertEqual(
			frappe.db.get_value("Patient Visit", self.visit.name, "current_station"), "Admission"
		)
		self.assertIn(ip, [r.name for r in inpatient.admission_list()["waiting"]])
		# one admission at a time
		with self.assertRaises(frappe.ValidationError):
			self.admit_request()

	def test_needs_reason_and_a_real_ward(self):
		enc = self.encounter(lab=False)
		with self.assertRaises(frappe.ValidationError):
			inpatient.request_admission(enc.name, self.ward, "Routine", today(), "")
		with self.assertRaises(frappe.ValidationError):
			inpatient.request_admission(enc.name, "Not A Ward", "Routine", today(), "Reason")

	def test_bed_given_then_on_the_ward(self):
		ip, bed = self.admitted()
		self.assertEqual(frappe.db.get_value("Inpatient Record", ip, "status"), "Admitted")
		self.assertEqual(frappe.db.get_value("Healthcare Service Unit", bed, "occupancy_status"), "Occupied")
		row = next(r for r in inpatient.admission_list(self.ward)["on_ward"] if r.name == ip)
		self.assertEqual(row.bed, bed)

	def test_patient_screen_and_every_panel(self):
		ip, bed = self.admitted()
		ws = inpatient.workspace(ip)
		self.assertEqual(ws["bed"], bed)
		self.assertEqual([t["panel"] for t in ws["tabs"]], list(inpatient.PANELS))
		for panel in inpatient.PANELS:
			self.assertIsInstance(inpatient.panel(ip, panel), dict, panel)
		self.assertTrue(ws["money"]["cash"])

	def test_admitted_consultation_completes_with_results_pending(self):
		from royce_health_ke import consultation

		enc, _ip = self.admit_request()
		enc.reload()
		enc.append("lab_test_prescription", {"lab_test_code": self.template})
		enc.save()
		frappe.flags.ke_test_observation_gate = True
		self.addCleanup(setattr, frappe.flags, "ke_test_observation_gate", False)
		enc._action = "submit"
		enc.docstatus = 1
		consultation.check_nothing_pending(enc)  # not refused


class TestWardDrugs(InpatientCase):
	def ward_round(self, ip, days="3 Day"):
		enc = frappe.get_doc(
			{
				"doctype": "Patient Encounter",
				"patient": self.patient,
				"practitioner": self.practitioner,
				"encounter_date": today(),
				"company": self.company,
				"inpatient_record": ip,
				"drug_prescription": [
					{
						"medication": self.medication,
						"drug_code": "DRG-PCM500",
						"dosage": self.dosage,
						"period": days,
						"dosage_form": frappe.db.get_value("Dosage Form", {}, "name"),
					}
				],
			}
		).insert(ignore_permissions=True)
		self.assertFalse(enc.get("ke_patient_visit"))  # billed with the admission, not the visit
		enc.submit()
		return enc

	def test_dose_times_spread_over_the_day(self):
		self.assertEqual(inpatient.dose_times(self.dosage), ["06:00:00", "14:00:00", "22:00:00"])

	def test_ward_round_makes_the_medication_order(self):
		ip, _bed = self.admitted()
		enc = self.ward_round(ip)
		order = frappe.get_doc("Inpatient Medication Order", {"patient_encounter": enc.name})
		self.assertEqual(order.docstatus, 1)
		self.assertEqual(len(order.medication_orders), 9)  # 3 a day x 3 days
		self.assertEqual({e.status for e in order.medication_orders}, {"Pending"})
		drugs = inpatient.panel(ip, "Drug Administration")
		self.assertEqual(drugs["active"][0]["counts"], {"Pending": 9})
		self.assertIn(self.patient, [r.patient for r in inpatient.ward_requests(hours=24 * 4)])
		# stopped on the ward round
		self.assertEqual(inpatient.stop_drug(order.name, "DRG-PCM500", "Fever settled"), 9)
		order.reload()
		self.assertEqual({e.status for e in order.medication_orders}, {"Stopped"})

	def test_issue_to_ward_charges_on_issue(self):
		frappe.db.set_single_value("Kenya Health Settings", "ward_drug_charge", inpatient.ON_ISSUE)
		inpatient.sync_drug_charge()
		self.assertEqual(
			frappe.db.get_single_value("Healthcare Settings", "manage_inpatient_medication_stock"), 0
		)
		ip, _bed = self.admitted()
		self.ward_round(ip, days="1 Day")
		try:
			entry = inpatient.issue_to_ward(self.patient, self.store, hours=24 * 2)
		except frappe.ValidationError as e:
			self.skipTest(f"stock or accounts not set up for ward issues here: {e}")
		self.assertEqual(frappe.db.get_value("Inpatient Medication Entry", entry, "docstatus"), 1)
		items = frappe.get_all(
			"Inpatient Record Item", filters={"parent": ip}, fields=["item_code", "quantity", "stock_entry"]
		)
		drugs = [i for i in items if i.item_code == "DRG-PCM500"]
		self.assertTrue(drugs and all(i.stock_entry for i in drugs))
		self.assertEqual(sum(i.quantity for i in drugs), 3)
		self.assertTrue(inpatient.money(frappe.get_doc("Inpatient Record", ip))["unbilled"] >= 0)

	def test_charge_setting_drives_marley(self):
		frappe.db.set_single_value("Kenya Health Settings", "ward_drug_charge", inpatient.ON_ADMINISTRATION)
		inpatient.sync_drug_charge()
		self.assertEqual(
			frappe.db.get_single_value("Healthcare Settings", "manage_inpatient_medication_stock"), 1
		)
		self.assertEqual(
			frappe.db.get_single_value("Healthcare Settings", "auto_schedule_medication_doses"), 1
		)
		frappe.db.set_single_value("Kenya Health Settings", "ward_drug_charge", inpatient.ON_ISSUE)
		inpatient.sync_drug_charge()


class TestChartsAndRecord(InpatientCase):
	def test_chart_entry_alerts_and_second_check(self):
		ip, _bed = self.admitted()
		name = charts.record(ip, "Feeding Chart", {"Route": "Oral", "Amount": 150, "Tolerated": "Yes"})
		entry = frappe.get_doc("Nursing Chart Entry", name)
		self.assertEqual(entry.inpatient_record, ip)
		self.assertTrue(entry.shift)
		with self.assertRaises(frappe.ValidationError):
			charts.record(ip, "Feeding Chart", {"Amount": 100})  # route required
		with self.assertRaises(frappe.ValidationError):
			charts.record(ip, "Feeding Chart", {"Route": "By drip"})  # not a choice
		values = {
			"Product": "Packed red cells",
			"Unit number": "BU-1",
			"Stage": "Start",
			"Temperature": 38.6,
			"Reaction": "No",
		}
		with self.assertRaises(frappe.ValidationError):
			charts.record(ip, "Blood Transfusion", values)  # needs the second nurse
		# a fresh site (CI) has no second user: make the checking nurse
		other = "ke.second.nurse@example.com"
		if not frappe.db.exists("User", other):
			frappe.get_doc(
				{
					"doctype": "User",
					"email": other,
					"first_name": "Second",
					"last_name": "Nurse",
					"send_welcome_email": 0,
				}
			).insert(ignore_permissions=True)
		t = frappe.get_doc(
			"Nursing Chart Entry", charts.record(ip, "Blood Transfusion", values, second_check_by=other)
		)
		self.assertIn("Temperature", t.alerts)
		care = inpatient.panel(ip, "Nursing Care")
		feeding = next(c for c in care["charts"] if c["name"] == "Feeding Chart")
		self.assertEqual(feeding["totals"].get("Amount"), 150)

	def test_shift_of(self):
		from datetime import datetime

		self.assertEqual(inpatient.shift_of(datetime(2026, 11, 19, 9, 0)), "Day")
		self.assertEqual(inpatient.shift_of(datetime(2026, 11, 19, 23, 0)), "Night")
		self.assertEqual(inpatient.shift_of(datetime(2026, 11, 19, 3, 0)), "Night")

	def test_admission_record_for_the_discharge_summary(self):
		ip, _bed = self.admitted()
		charts.record(ip, "Feeding Chart", {"Route": "Oral", "Amount": 100})
		rec = inpatient.admission_record(ip)
		self.assertEqual(rec.reason, "Severe malaria, needs IV artesunate")
		self.assertEqual(rec.charts[0].template, "Feeding Chart")


class TestPreauth(InpatientCase):
	def test_insured_admission_waits_for_the_code(self):
		payor = frappe.db.get_value("Insurance Payor", {}, "name")
		if not payor:
			self.skipTest("needs an insurance payor")
		frappe.db.set_value("Insurance Payor", payor, {"ke_admission_preauth": 1, "ke_preauth_hours": 12})
		enc = self.encounter(lab=False)
		frappe.db.set_value(
			"Patient Visit",
			self.visit.name,
			{
				"payment_method": "Insurance",
				"insurance_payor": payor,
				"member_number": "M-1",
				"policy_expiry": add_days(today(), 300),
			},
		)
		ip = inpatient.request_admission(enc.name, self.ward, "Emergency", today(), "Road traffic accident")
		doc = frappe.get_doc("Inpatient Record", ip)
		self.assertEqual(doc.ke_preauth_status, "Pending")
		claim = frappe._dict(inpatient_record=ip)
		claim.get = lambda k, d=None: claim[k] if k in claim else d
		with self.assertRaises(frappe.ValidationError):
			inpatient.hold_claim_without_preauth(claim)
		inpatient.record_preauth(ip, "PA-123")
		self.assertEqual(frappe.db.get_value("Inpatient Record", ip, "ke_preauth_code"), "PA-123")
		inpatient.hold_claim_without_preauth(claim)  # now goes through
		self.assertEqual(getdate(doc.ke_preauth_due) >= getdate(add_days(today(), 0)), True)


class TestDischargePrint(InpatientCase):
	def test_discharge_summary_prints_the_stay(self):
		from royce_health_ke.marley import make_discharge_summary

		ip, _bed = self.admitted()
		charts.record(ip, "Feeding Chart", {"Route": "Oral", "Amount": 120})
		# Plan Discharge names the discharging doctor on the admission
		frappe.db.set_value("Inpatient Record", ip, "discharge_practitioner", self.practitioner)
		summary = make_discharge_summary(ip)
		summary.insert(ignore_permissions=True)
		html = frappe.get_print("Discharge Summary", summary.name, "Patient Discharge Summary")
		self.assertIn("Severe malaria, needs IV artesunate", html)
		self.assertIn("Feeding Chart", html)


class TestSellingPriceList(InpatientCase):
	def test_admission_refuses_a_buying_price_list(self):
		buying = frappe.db.get_value("Price List", {"selling": 0, "buying": 1}, "name")
		if not buying:
			self.skipTest("needs a buying price list")
		_enc, ip = self.admit_request()
		doc = frappe.get_doc("Inpatient Record", ip)
		doc.price_list = buying
		with self.assertRaises(frappe.ValidationError):
			doc.save(ignore_permissions=True)
		frappe.db.set_value("Inpatient Record", ip, "price_list", buying)
		from royce_health_ke.patches.v0_47 import selling_price_list_on_admissions

		selling_price_list_on_admissions.execute()
		self.assertFalse(frappe.db.get_value("Inpatient Record", ip, "price_list"))
