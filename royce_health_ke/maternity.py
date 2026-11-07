# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Maternity rules shared by Pregnancy Record, ANC Visit, Delivery Record and
PNC Visit. Fields follow the MOH ANC, maternity and PNC registers (as in
KenyaEMR's register reports) and the WHO Labour Care Guide alert thresholds;
adjust to the hospital's own forms where they differ."""

import frappe
from frappe import _
from frappe.utils import (
	add_days,
	cint,
	date_diff,
	flt,
	get_datetime,
	getdate,
	now_datetime,
	time_diff_in_hours,
)

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


LAG_HOURS = {5: 6, 6: 5, 7: 3, 8: 2.5, 9: 2}  # MOH Labour Care Guide: hours at a dilatation before an alert
DEFAULT_FHR_LOW = 110


def fhr_low():
	return cint(frappe.db.get_single_value("Kenya Health Settings", "lcg_fhr_low")) or DEFAULT_FHR_LOW


def observation_alerts(row, fhr_floor=None):
	"""[(field, message)] for each reading that meets the guide's Alert column.
	A message of None marks a further field of the same alert (the BP)."""
	g = row.get
	fhr_floor = fhr_floor or fhr_low()
	out = []
	for field, label in (
		("companion", _("No companion")),
		("pain_relief", _("No pain relief")),
		("oral_fluid", _("No oral fluid")),
	):
		if g(field) == "No":
			out.append((field, label))
	if g("posture") == "Supine":
		out.append(("posture", _("Supine")))
	fhr = g("fetal_heart_rate")
	if fhr and (fhr < fhr_floor or fhr >= 160):
		out.append(("fetal_heart_rate", _("FHR {0}").format(fhr)))
	if g("fhr_deceleration") == "Late":
		out.append(("fhr_deceleration", _("Late decelerations")))
	if g("liquor") in ("Meconium +++", "Meconium", "Blood-stained"):
		out.append(("liquor", _("Liquor {0}").format(g("liquor"))))
	if g("fetal_position") in ("Posterior", "Transverse"):
		out.append(("fetal_position", _("{0} position").format(g("fetal_position"))))
	for field, label in (("caput", _("Caput")), ("moulding", _("Moulding"))):
		if g(field) == "+++":
			out.append((field, f"{label} +++"))
	pulse = g("maternal_pulse")
	if pulse and (pulse < 60 or pulse >= 120):
		out.append(("maternal_pulse", _("Pulse {0}").format(pulse)))
	systolic, diastolic = g("bp_systolic"), g("bp_diastolic")
	bp = []
	if systolic and (systolic < 80 or systolic >= 140):
		bp.append("bp_systolic")
	if diastolic and diastolic >= 90:
		bp.append("bp_diastolic")
	for i, field in enumerate(bp):
		out.append((field, _("BP {0}/{1}").format(systolic or "-", diastolic or "-") if i == 0 else None))
	temp = g("temperature")
	if temp and (temp < 35.0 or temp >= 37.5):
		out.append(("temperature", _("Temp {0}").format(temp)))
	for field, label in (("urine_protein", _("Protein")), ("urine_acetone", _("Acetone"))):
		if g(field) in ("++", "+++"):
			out.append((field, f"{label} {g(field)}"))
	contractions = g("contractions_per_10min")
	if contractions and (contractions <= 2 or contractions > 5):
		out.append(("contractions_per_10min", _("Contractions {0}/10 min").format(contractions)))
	duration = g("contraction_duration_sec")
	if duration and (duration < 20 or duration > 60):
		out.append(("contraction_duration_sec", _("Contractions last {0} s").format(duration)))
	return out


def labour_alert(row, fhr_floor=None):
	"""The guide's alerts for one observation, as one line."""
	return ", ".join(m for _f, m in observation_alerts(row, fhr_floor) if m)


def progress_alerts(rows):
	"""Rows whose cervix hasn't moved for the guide's lag time at that
	dilatation: {row: message}. Dilatation is taken in whole cm, from the time
	it was first reached."""
	reached, last, out = {}, None, {}
	timed = [r for r in rows if r.get("time") and r.get("cervical_dilatation_cm")]
	for r in sorted(timed, key=lambda r: get_datetime(r.get("time"))):
		cm = int(r.get("cervical_dilatation_cm"))
		if last is None or cm > last:
			reached[cm], last = get_datetime(r.get("time")), cm
		if cm != last or cm not in LAG_HOURS:
			continue
		hours = time_diff_in_hours(get_datetime(r.get("time")), reached[cm])
		if hours >= LAG_HOURS[cm]:
			out[id(r)] = _("Cervix {0} cm for {1} h").format(cm, flt(hours, 1))
	return out


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
	floor = fhr_low()
	slow = progress_alerts(doc.labour_observations)
	for row in doc.labour_observations:
		alerts = [m for _f, m in observation_alerts(row, floor) if m]
		if id(row) in slow:
			alerts.append(slow[id(row)])
		row.alert = ", ".join(alerts)
		row.recorded_by = row.recorded_by or frappe.session.user


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
