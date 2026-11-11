# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Demo maternity: Faith books for ANC, attends three contacts, delivers a
baby girl normally in the early hours of yesterday (one labour observation
raises a fetal heart rate alert), is seen for PNC today and has an implant
inserted before she goes home (immediate postpartum family planning)."""

import frappe
from frappe.utils import add_days, getdate, today

from royce_health_ke.demo import journey

MOTHER = {
	"first_name": "Faith",
	"middle_name": "Njeri",
	"last_name": "Wambui",
	"sex": "Female",
	"mobile": "0712 000 005",
	"occupation": "Trader",
	"marital_status": "Married",
	"ke_id_type": "National ID",
	"ke_id_number": "0009012",
	"ke_sha_number": "DEMO-SHA-003",
	"ke_county": "Nakuru",
	"ke_nationality": "Kenya",
	"ke_residence": "Nakuru town (demo)",
	"ke_sub_county": "Nakuru West",
	"ke_nok_name": "James Kariuki",
	"ke_nok_relationship": "Spouse",
	"ke_nok_phone": "0712 000 006",
	"patient_details": "DEMO PATIENT - fictional person and identifiers.",
}


def run(company):
	setup_packages(company)
	existing = frappe.db.get_value("Patient", {"first_name": "Faith", "last_name": "Wambui"})
	if existing:
		return {
			"patient": existing,
			"created": False,
			"family_planning": family_planning(company, existing),
			"labour_care_guide": labour_care_guide(existing),
			"discharge_bill": discharge_bill(company, existing),
		}
	amina = frappe.db.get_value("Healthcare Practitioner", {"first_name": "Amina"})
	mother = journey._insert({"doctype": "Patient", **MOTHER, "dob": f"{getdate().year - 27}-02-10"}).name
	lmp = add_days(today(), -276)  # 39 weeks 3 days today
	pregnancy = journey._insert(
		{
			"doctype": "Pregnancy Record",
			"patient": mother,
			"company": company,
			"health_facility": frappe.db.get_value("Health Facility", {"company": company}),
			"anc_number": "DEMO-ANC-0001",
			"booking_date": add_days(lmp, 84),
			"gravida": 2,
			"parity": "1+0",
			"lmp": lmp,
			"blood_group": "O+",
			"haemoglobin": 11.8,
			"hepatitis_b": "Negative",
			"hiv_status": "Negative",
			"syphilis": "Non-reactive",
		}
	)
	for weeks, weight, bp, fh, fhr, extras in (
		(
			12,
			61.0,
			(110, 70),
			None,
			None,
			{"td_dose": "Td1", "iron_folate": 1, "itn_given": 1, "breast_exam": 1},
		),
		(
			28,
			66.5,
			(115, 72),
			28,
			144,
			{"ipt_dose": "IPTp-SP 2", "td_dose": "Td2", "iron_folate": 1, "deworming": 1},
		),
		(
			38,
			70.0,
			(118, 76),
			37,
			140,
			{"ipt_dose": "IPTp-SP 4", "presentation": "Cephalic", "ppfp_counselling": 1},
		),
	):
		journey._insert(
			{
				"doctype": "ANC Visit",
				"pregnancy_record": pregnancy.name,
				"visit_date": add_days(lmp, weeks * 7),
				"practitioner": amina,
				"weight": weight,
				"bp_systolic": bp[0],
				"bp_diastolic": bp[1],
				"fundal_height": fh,
				"fetal_heart_rate": fhr,
				"tb_screening": "No signs",
				**extras,
			},
			submit=True,
		)

	day = add_days(today(), -1)
	delivery = journey._insert(
		{
			"doctype": "Delivery Record",
			"pregnancy_record": pregnancy.name,
			"delivered_by": amina,
			"admission_datetime": f"{add_days(day, -1)} 21:30:00",
			"onset_of_labour": "Spontaneous",
			"duration_of_labour_hours": 7,
			"lcg_used": 1,
			"labour_observations": [
				{
					"time": f"{add_days(day, -1)} 22:00:00",
					"cervical_dilatation_cm": 5,
					"fetal_heart_rate": 138,
					"contractions_per_10min": 3,
					"maternal_pulse": 88,
					"bp_systolic": 118,
					"bp_diastolic": 76,
					"temperature": 36.8,
					"liquor": "Intact",
					"moulding": "0",
				},
				{
					"time": f"{day} 01:00:00",
					"cervical_dilatation_cm": 7,
					"fetal_heart_rate": 165,
					"contractions_per_10min": 4,
					"maternal_pulse": 92,
					"liquor": "Clear",
					"moulding": "0",
					"remarks": "Left lateral position, FHR rechecked",
				},
				{
					"time": f"{day} 03:30:00",
					"cervical_dilatation_cm": 10,
					"fetal_heart_rate": 142,
					"contractions_per_10min": 5,
					"maternal_pulse": 90,
					"liquor": "Clear",
					"moulding": "0",
				},
			],
			"delivery_datetime": f"{day} 04:30:00",
			"mode_of_delivery": "Spontaneous vaginal delivery",
			"placenta_complete": 1,
			"uterotonic": "Oxytocin",
			"blood_loss_ml": 250,
			"perineum": "1st degree tear",
			"maternal_condition": "Alive",
			"babies": [
				{
					"sex": "Female",
					"birth_weight_g": 3200,
					"outcome": "Live birth",
					"apgar_1": 8,
					"apgar_5": 9,
					"breastfeeding_1hr": 1,
					"vitamin_k": 1,
					"teo": 1,
					"chlorhexidine": 1,
					"condition_at_discharge": "Alive",
					"birth_notification_number": "DEMO-BN-0001",
				}
			],
		},
		submit=True,
	)
	journey._insert(
		{
			"doctype": "PNC Visit",
			"delivery_record": delivery.name,
			"visit_date": today(),
			"practitioner": amina,
			"temperature": 36.7,
			"pulse": 84,
			"bp_systolic": 116,
			"bp_diastolic": 74,
			"breasts": "Normal",
			"uterus": "Well contracted",
			"lochia": "Normal",
			"wound": "Healing well",
			"fp_counselled": 1,
			"baby_reviewed": 1,
			"baby_feeding": "Exclusive breastfeeding",
			"cord": "Clean and dry",
		},
		submit=True,
	)
	delivery.reload()
	labour_care_guide(mother)
	fp = family_planning(company, mother)
	bill = discharge_bill(company, mother)
	return {
		"patient": mother,
		"created": True,
		"pregnancy": pregnancy.name,
		"delivery": delivery.name,
		"baby": delivery.babies[0].baby_patient,
		"labour_alerts": [r.alert for r in delivery.labour_observations if r.alert],
		"family_planning": fp,
		"discharge_bill": bill,
	}


def family_planning(company, mother):
	"""Faith's postpartum implant (added in v0.9.0, so it is also created for
	demo sites that already have her)."""
	existing = frappe.db.get_value("Family Planning Visit", {"patient": mother, "docstatus": 1})
	if existing:
		return existing
	return journey._insert(
		{
			"doctype": "Family Planning Visit",
			"patient": mother,
			"company": company,
			"visit_date": today(),
			"practitioner": frappe.db.get_value("Healthcare Practitioner", {"first_name": "Amina"}),
			"method": "Implant (1 rod)",
			"procedure": "Insertion",
			"timing": "Immediate postpartum (within 48 hours)",
			"quantity": 1,
			"batch_no": "DEMO-IMP-001",
			"next_visit_date": add_days(today(), 42),
		},
		submit=True,
	).name


# Demo prices, not SHA's tariff: a hospital enters its own and SHA's current rates.
PACKAGES = (
	("Normal Delivery (Cash)", "Vaginal delivery", "MAT-PKG-NVD", "Normal Delivery Package", 25000, 2),
	("Caesarean Section (Cash)", "Caesarean section", "MAT-PKG-CS", "Caesarean Section Package", 85000, 4),
)


def setup_packages(company):
	from royce_health_ke.demo import masters

	for name, kind, code, item_name, rate, nights in PACKAGES:
		masters.item(company, code, item_name, "Services", rate)
		if frappe.db.exists("Maternity Package", name):
			continue
		frappe.get_doc(
			{
				"doctype": "Maternity Package",
				"package_name": name,
				"delivery_type": kind,
				"item": code,
				"rate": rate,
				"included_nights": nights,
				"covered": [
					{"item_group": "Drug"},
					{"item_code": "NURS-IP"},
					{"item_code": "KIT-ADM"},
				],
				"notes": "DEMO PRICE - not an SHA tariff.",
			}
		).insert(ignore_permissions=True)


def discharge_bill(company, mother):
	"""Faith's discharge bill: the normal delivery package, with her nursing
	care and paracetamol included at zero. Her demo delivery has no
	admission (no ward nights), so the bill names the delivery itself, as
	staff do when they add the package line by hand."""
	from royce_health_ke.packages import choose_package

	delivery = frappe.get_doc("Delivery Record", {"patient": mother, "docstatus": 1})
	if delivery.invoiced:
		name = frappe.db.get_value(
			"Sales Invoice Item",
			{"reference_dt": "Delivery Record", "reference_dn": delivery.name, "docstatus": 1},
			"parent",
		)
		if (
			journey._etims_active(company)
			and frappe.db.get_value("Sales Invoice", name, "royce_etims_status") != "Sent"
		):
			journey._register_items(company)
			journey._sign(frappe.get_doc("Sales Invoice", name))
		return name
	if not delivery.maternity_package:
		choose_package(delivery)
		delivery.db_set("maternity_package", delivery.maternity_package)
	bill = journey._bill(
		company,
		mother,
		frappe.db.get_value("Patient", mother, "customer"),
		today(),
		"Discharge: normal delivery",
		[],
		extra=(("NURS-IP", 1), ("DRG-PCM500", 10)),
		rows=(
			{
				"item_code": frappe.db.get_value("Maternity Package", delivery.maternity_package, "item"),
				"qty": 1,
				"reference_dt": "Delivery Record",
				"reference_dn": delivery.name,
			},
		),
	)
	journey._pay(bill, "TKF7DEMO06")
	if journey._etims_active(company):
		journey._register_items(company)
		journey._sign(bill)
	return bill.name


# Faith's labour on the full MOH Labour Care Guide (added in v0.13.0; filled on
# existing demo sites too). One entry per labour observation, in time order.
LCG = (
	{
		"companion": "Yes",
		"pain_relief": "Declined",
		"oral_fluid": "Yes",
		"posture": "Mobile",
		"fhr_deceleration": "No",
		"fetal_position": "Anterior",
		"caput": "0",
		"urine_protein": "Nil",
		"urine_acetone": "Nil",
		"contraction_duration_sec": 35,
		"descent": "4",
		"initials": "AA",
	},
	{
		"companion": "Yes",
		"pain_relief": "Yes",
		"oral_fluid": "Yes",
		"posture": "Mobile",
		"fhr_deceleration": "Early",
		"fetal_position": "Anterior",
		"caput": "0",
		"contraction_duration_sec": 45,
		"descent": "3",
		"initials": "AA",
		"assessment": "Baseline FHR 165 after membranes ruptured; liquor clear.",
		"action_plan": "Left lateral, oral fluids, recheck FHR in 15 min; inform doctor if it persists.",
		"iv_fluid_type": "Ringer's lactate",
		"iv_fluid_volume_ml": 500,
	},
	{
		"companion": "Yes",
		"pain_relief": "Yes",
		"oral_fluid": "Yes",
		"posture": "Mobile",
		"fhr_deceleration": "No",
		"fetal_position": "Anterior",
		"caput": "+",
		"contraction_duration_sec": 50,
		"descent": "1",
		"pushing": 1,
		"initials": "AA",
	},
)


def labour_care_guide(mother):
	name = frappe.db.get_value("Delivery Record", {"patient": mother, "docstatus": 1})
	if not name:
		return None
	delivery = frappe.get_doc("Delivery Record", name)
	rows = sorted(delivery.labour_observations, key=lambda r: r.time)
	if not rows or rows[0].companion:
		return name
	for row, values in zip(rows, LCG, strict=False):
		frappe.db.set_value("Labour Observation", row.name, values, update_modified=False)
	frappe.db.set_value(
		"Delivery Record",
		name,
		{
			"active_labour_datetime": rows[0].time,
			"membranes_ruptured_datetime": rows[1].time if len(rows) > 1 else None,
		},
		update_modified=False,
	)
	return name
