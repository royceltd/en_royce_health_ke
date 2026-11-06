# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Maternity rules shared by Pregnancy Record, ANC Visit, Delivery Record and
PNC Visit. Fields follow the MOH ANC, maternity and PNC registers (as in
KenyaEMR's register reports) and the WHO Labour Care Guide alert thresholds;
adjust to the hospital's own forms where they differ."""

import frappe
from frappe import _
from frappe.utils import add_days, date_diff, get_datetime, getdate, now_datetime

GESTATION_DAYS = 280


def edd_from_lmp(lmp):
	return add_days(getdate(lmp), GESTATION_DAYS) if lmp else None


def gestation_weeks(lmp, on_date):
	if not lmp or not on_date:
		return None
	return date_diff(getdate(on_date), getdate(lmp)) // 7


def pnc_timing(delivery_datetime, visit_date):
	"""MOH PNC register buckets: within 48 hours, 3 days to under 6 weeks, after."""
	days = date_diff(getdate(visit_date), getdate(get_datetime(delivery_datetime)))
	if days <= 2:
		return "Within 48 hours"
	return "3 days to under 6 weeks" if days < 42 else "6 weeks and after"


def labour_alert(row):
	"""WHO Labour Care Guide thresholds that should prompt action."""
	alerts = []
	fhr = row.get("fetal_heart_rate")
	if fhr and (fhr < 110 or fhr >= 160):
		alerts.append(_("FHR {0}").format(fhr))
	pulse = row.get("maternal_pulse")
	if pulse and (pulse < 60 or pulse >= 120):
		alerts.append(_("Pulse {0}").format(pulse))
	if (row.get("bp_systolic") or 0) >= 140 or (row.get("bp_diastolic") or 0) >= 90:
		alerts.append(_("BP {0}/{1}").format(row.get("bp_systolic") or "-", row.get("bp_diastolic") or "-"))
	if (row.get("temperature") or 0) >= 37.5:
		alerts.append(_("Temp {0}").format(row.get("temperature")))
	contractions = row.get("contractions_per_10min")
	if contractions is not None and contractions != 0 and (contractions <= 2 or contractions > 5):
		alerts.append(_("Contractions {0}/10 min").format(contractions))
	if row.get("liquor") in ("Meconium", "Blood-stained"):
		alerts.append(_("Liquor {0}").format(row.get("liquor")))
	return ", ".join(alerts)


def validate_pregnancy(doc):
	sex = frappe.db.get_value("Patient", doc.patient, "sex")
	if sex and sex != "Female":
		frappe.throw(
			_("{0} is recorded as {1}; a pregnancy needs a female patient.").format(doc.patient_name, sex)
		)
	doc.edd = edd_from_lmp(doc.lmp)
	if doc.status == "Active":
		other = frappe.db.get_value(
			"Pregnancy Record", {"patient": doc.patient, "status": "Active", "name": ["!=", doc.name]}
		)
		if other:
			frappe.throw(_("{0} already has an active pregnancy record {1}.").format(doc.patient_name, other))


def active_pregnancy(name):
	pregnancy = frappe.get_doc("Pregnancy Record", name)
	if pregnancy.status not in ("Active", "Delivered"):
		frappe.throw(_("Pregnancy Record {0} is {1}.").format(name, pregnancy.status))
	return pregnancy


def validate_anc_visit(doc):
	pregnancy = active_pregnancy(doc.pregnancy_record)
	doc.gestation_weeks = gestation_weeks(pregnancy.lmp, doc.visit_date)
	doc.contact_number = (
		frappe.db.count(
			"ANC Visit",
			{
				"pregnancy_record": doc.pregnancy_record,
				"docstatus": 1,
				"name": ["!=", doc.name],
				"visit_date": ["<=", doc.visit_date],
			},
		)
		+ 1
	)


def validate_delivery(doc):
	pregnancy = active_pregnancy(doc.pregnancy_record)
	if get_datetime(doc.delivery_datetime) > now_datetime():
		frappe.throw(_("Delivery date and time can't be in the future."))
	doc.gestation_weeks = gestation_weeks(pregnancy.lmp, get_datetime(doc.delivery_datetime).date())
	doc.number_of_babies = len(doc.babies)
	from royce_health_ke.packages import choose_package

	choose_package(doc)
	for row in doc.labour_observations:
		row.alert = labour_alert(row)


def on_submit_delivery(doc):
	frappe.db.set_value(
		"Pregnancy Record", doc.pregnancy_record, {"status": "Delivered", "delivery_record": doc.name}
	)
	mother = frappe.get_doc("Patient", doc.patient)
	for row in doc.babies:
		if row.outcome != "Live birth" or row.baby_patient:
			continue
		baby = frappe.get_doc(
			{
				"doctype": "Patient",
				"first_name": _("Baby of {0}").format(mother.first_name),
				"last_name": mother.last_name,
				"sex": row.sex if frappe.db.exists("Gender", row.sex) else "Other",
				"dob": get_datetime(doc.delivery_datetime).date(),
				"patient_relation": [{"relation": "Mother", "patient": mother.name}],
				"ke_county": mother.get("ke_county"),
				"ke_sub_county": mother.get("ke_sub_county"),
				"ke_nok_name": mother.patient_name,
				"ke_nok_relationship": "Parent",
				"ke_nok_phone": mother.mobile,
				"patient_details": _("Born {0} at {1} g, {2}. Mother: {3} ({4}).").format(
					frappe.format(doc.delivery_datetime, "Datetime"),
					row.birth_weight_g,
					doc.mode_of_delivery,
					mother.patient_name,
					mother.name,
				),
			}
		).insert(ignore_permissions=True)
		row.db_set("baby_patient", baby.name)


def on_cancel_delivery(doc):
	"""The pregnancy is active again; babies' patient records stay (they may
	already have visits) and keep their link to the mother."""
	frappe.db.set_value(
		"Pregnancy Record", doc.pregnancy_record, {"status": "Active", "delivery_record": None}
	)


def validate_pnc_visit(doc):
	delivery = frappe.db.get_value(
		"Delivery Record", doc.delivery_record, ["delivery_datetime", "docstatus"], as_dict=True
	)
	if delivery.docstatus != 1:
		frappe.throw(_("Submit Delivery Record {0} first.").format(doc.delivery_record))
	if getdate(doc.visit_date) < getdate(get_datetime(delivery.delivery_datetime)):
		frappe.throw(_("A postnatal visit can't be before the delivery."))
	doc.timing = pnc_timing(delivery.delivery_datetime, doc.visit_date)
	doc.visit_number = (
		frappe.db.count(
			"PNC Visit",
			{
				"delivery_record": doc.delivery_record,
				"docstatus": 1,
				"name": ["!=", doc.name],
				"visit_date": ["<=", doc.visit_date],
			},
		)
		+ 1
	)
