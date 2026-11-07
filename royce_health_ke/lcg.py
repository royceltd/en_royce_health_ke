# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""The MOH Modified WHO Labour Care Guide as a chart: the Delivery Record's
labour observations laid out like the paper form (one column per
observation, rows grouped Supportive care / Baby / Woman / Labour progress /
Shared decision-making / Medications), alert values circled in red. The
same HTML is shown on the Delivery Record and printed by the "Labour Care
Guide" print format."""

import frappe
from frappe import _
from frappe.utils import cint, flt, get_datetime, getdate, time_diff_in_hours

from royce_health_ke.maternity import fhr_low, observation_alerts, progress_alerts

COLUMNS_PER_PAGE = 12
SHORT = {
	"Yes": "Y",
	"No": "N",
	"Declined": "D",
	"Unknown": "U",
	"Supine": "SP",
	"Mobile": "MO",
	"Early": "E",
	"Late": "L",
	"Variable": "V",
	"Intact": "I",
	"Clear": "C",
	"Meconium +": "M+",
	"Meconium ++": "M++",
	"Meconium +++": "M+++",
	"Meconium": "M",
	"Blood-stained": "B",
	"Absent": "Abs",
	"Anterior": "A",
	"Posterior": "P",
	"Transverse": "T",
	"Nil": "0",
	"Trace": "Tr",
}


def short(value):
	if value in (None, ""):
		return ""
	return SHORT.get(value, value if isinstance(value, str) else frappe.format(value))


def number(value, decimals=0):
	if not value:
		return ""
	return f"{flt(value, decimals):g}"


def grid_rows(fhr_floor):
	"""(section, label, alert column, fields that circle the cell, value)."""
	return [
		("Supportive care", _("Companion"), "N", ["companion"], lambda r: short(r.companion)),
		("Supportive care", _("Pain relief"), "N", ["pain_relief"], lambda r: short(r.pain_relief)),
		("Supportive care", _("Oral fluid"), "N", ["oral_fluid"], lambda r: short(r.oral_fluid)),
		("Supportive care", _("Posture"), "SP", ["posture"], lambda r: short(r.posture)),
		(
			"Baby",
			_("Baseline FHR"),
			f"<{fhr_floor}, ≥160",
			["fetal_heart_rate"],
			lambda r: number(r.fetal_heart_rate),
		),
		("Baby", _("FHR decelerations"), "L", ["fhr_deceleration"], lambda r: short(r.fhr_deceleration)),
		("Baby", _("Amniotic fluid"), "M+++, B", ["liquor"], lambda r: short(r.liquor)),
		("Baby", _("Fetal position"), "P, T", ["fetal_position"], lambda r: short(r.fetal_position)),
		("Baby", _("Caput"), "+++", ["caput"], lambda r: short(r.caput)),
		("Baby", _("Moulding"), "+++", ["moulding"], lambda r: short(r.moulding)),
		("Woman", _("Pulse"), "<60, ≥120", ["maternal_pulse"], lambda r: number(r.maternal_pulse)),
		("Woman", _("Systolic BP"), "<80, ≥140", ["bp_systolic"], lambda r: number(r.bp_systolic)),
		("Woman", _("Diastolic BP"), "≥90", ["bp_diastolic"], lambda r: number(r.bp_diastolic)),
		("Woman", _("Temperature °C"), "<35.0, ≥37.5", ["temperature"], lambda r: number(r.temperature, 1)),
		(
			"Woman",
			_("Urine"),
			"P++, A++",
			["urine_protein", "urine_acetone"],
			lambda r: " ".join(
				x
				for x in (
					f"P{short(r.urine_protein)}" if r.urine_protein else "",
					f"A{short(r.urine_acetone)}" if r.urine_acetone else "",
				)
				if x
			),
		),
		(
			"Labour progress",
			_("Contractions per 10 min"),
			"≤2, >5",
			["contractions_per_10min"],
			lambda r: number(r.contractions_per_10min),
		),
		(
			"Labour progress",
			_("Duration of contractions"),
			"<20, >60",
			["contraction_duration_sec"],
			lambda r: number(r.contraction_duration_sec),
		),
		(
			"Labour progress",
			_("Cervix (cm)"),
			_("lag time"),
			["cervix"],
			lambda r: number(r.cervical_dilatation_cm, 1) + (" P" if r.pushing else ""),
		),
		("Labour progress", _("Descent (fifths)"), "", [], lambda r: r.descent or ""),
		("Shared decision-making", _("Impression / assessment"), "", [], lambda r: r.assessment or ""),
		("Shared decision-making", _("Action plan"), "", [], lambda r: r.action_plan or ""),
		("Medications", _("Oxytocin (IU in 500 ml)"), "", [], lambda r: number(r.oxytocin_dose_iu, 1)),
		("Medications", _("Oxytocin (drops/min)"), "", [], lambda r: number(r.oxytocin_rate)),
		("Medications", _("IV fluids: type"), "", [], lambda r: r.iv_fluid_type or ""),
		("Medications", _("IV fluids: volume (ml)"), "", [], lambda r: number(r.iv_fluid_volume_ml)),
		("", _("Initials"), "", [], lambda r: r.initials or ""),
	]


def header(doc):
	pregnancy = (
		frappe.db.get_value(
			"Pregnancy Record",
			doc.pregnancy_record,
			[
				"gravida",
				"parity",
				"lmp",
				"risk_factors",
				"hiv_status",
				"syphilis",
				"hepatitis_b",
				"health_facility",
			],
			as_dict=True,
		)
		or frappe._dict()
	)
	patient = (
		frappe.db.get_value("Patient", doc.patient, ["dob", "ke_id_number"], as_dict=True) or frappe._dict()
	)
	facility = (
		frappe.db.get_value("Health Facility", pregnancy.health_facility, "facility_name")
		if pregnancy.health_facility
		else None
	)
	on = getdate(doc.delivery_datetime or doc.admission_datetime or None)
	age = None
	if patient.dob:
		dob = getdate(patient.dob)
		age = on.year - dob.year - ((on.month, on.day) < (dob.month, dob.day))
	return frappe._dict(
		facility=facility or doc.company,
		ip_no=doc.inpatient_record or "",
		name=doc.patient_name,
		age=age,
		nin=patient.ke_id_number or "",
		parity=f"G{pregnancy.gravida or '-'} P{pregnancy.parity or '-'}",
		lmp=frappe.format(pregnancy.lmp, "Date") if pregnancy.lmp else "",
		weeks=doc.gestation_weeks or "",
		onset=", ".join(
			x
			for x in (
				doc.onset_of_labour or "",
				frappe.format(doc.admission_datetime, "Datetime") if doc.admission_datetime else "",
			)
			if x
		),
		active=frappe.format(doc.active_labour_datetime, "Datetime")
		if doc.get("active_labour_datetime")
		else "",
		ruptured=frappe.format(doc.membranes_ruptured_datetime, "Datetime")
		if doc.get("membranes_ruptured_datetime")
		else "",
		risk=pregnancy.risk_factors or "",
		pmtct=pregnancy.hiv_status or "",
		syphilis=pregnancy.syphilis or "",
		hepatitis_b=pregnancy.hepatitis_b or "",
	)


def columns(doc, fhr_floor):
	rows = sorted((r for r in doc.labour_observations if r.time), key=lambda r: get_datetime(r.time))
	slow = progress_alerts(rows)
	start = get_datetime(doc.active_labour_datetime) if doc.get("active_labour_datetime") else None
	out = []
	for r in rows:
		flagged = {f for f, _m in observation_alerts(r, fhr_floor)}
		if id(r) in slow:
			flagged.add("cervix")
		second = flt(r.cervical_dilatation_cm) >= 10 or cint(r.pushing)
		out.append(
			frappe._dict(
				row=r,
				time=get_datetime(r.time).strftime("%H:%M"),
				date=frappe.format(getdate(r.time), "Date"),
				hours=f"{time_diff_in_hours(get_datetime(r.time), start):.1f}" if start else "",
				stage=_("2nd") if second else _("1st"),
				flagged=flagged,
			)
		)
	return out


@frappe.whitelist()
def labour_care_guide_html(delivery):
	doc = frappe.get_doc("Delivery Record", delivery) if isinstance(delivery, str) else delivery
	doc.check_permission("read")
	fhr_floor = fhr_low()
	cols = columns(doc, fhr_floor)
	rows = grid_rows(fhr_floor)
	pages = [cols[i : i + COLUMNS_PER_PAGE] for i in range(0, len(cols), COLUMNS_PER_PAGE)] or [[]]
	body = []
	for page in pages:
		cells = []
		for section, label, alert, fields, value in rows:
			cells.append(
				frappe._dict(
					section=section,
					label=label,
					alert=alert,
					cells=[
						frappe._dict(text=value(c.row), flagged=bool(set(fields) & c.flagged)) for c in page
					],
				)
			)
		body.append(frappe._dict(columns=page, rows=cells, pad=COLUMNS_PER_PAGE - len(page)))
	return frappe.render_template(
		"royce_health_ke/templates/includes/labour_care_guide.html",
		{"h": header(doc), "pages": body, "_": _},
	)
