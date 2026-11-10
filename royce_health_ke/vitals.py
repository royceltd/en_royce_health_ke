# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Triage vital signs flagged Normal / Abnormal, each reading against the
range for the patient's age, so an abnormal row stands out in the triage list.

Ranges (confirm with the hospital's clinicians before go-live):
- Temperature 35.5-37.5 °C; SpO2 94 % and above (WHO/ETAT).
- Pulse and respiratory rate by age band (paediatric ETAT / APLS bands):
  under 1, 1-4, 5-12, 13 and over.
- Blood pressure from 13 years: systolic 90-139, diastolic 60-89 (children
  under 13 need centile tables, so they are not flagged).
- BMI for adults (18 and over): 18.5-24.9.
Marley stores temperature, pulse, rate and BP as text, so unreadable values
are skipped rather than flagged."""

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

# (lowest age in years, (low, high)) - first band whose age the patient has reached, from the top.
PULSE = ((13, (60, 100)), (5, (70, 120)), (1, (80, 140)), (0, (100, 160)))
RESPIRATION = ((13, (12, 20)), (5, (18, 30)), (1, (24, 40)), (0, (30, 60)))

READINGS = (
	# fieldname, label, unit
	("temperature", "Temperature", "°C"),
	("pulse", "Pulse", "/min"),
	("respiratory_rate", "Respiratory rate", "/min"),
	("ke_spo2", "SpO2", "%"),
	("bp_systolic", "BP systolic", "mmHg"),
	("bp_diastolic", "BP diastolic", "mmHg"),
	("bmi", "BMI", ""),
)


def _number(value):
	try:
		return float(str(value).strip()) if value not in (None, "") else None
	except ValueError:
		return None


def _band(bands, age):
	for lowest, limits in bands:
		if age is None or age >= lowest:
			return limits
	return bands[-1][1]


def ranges_for(age):
	"""{fieldname: (low, high)} for a patient of this age in years (None if
	unknown: adult ranges). None for a limit means no limit on that side."""
	ranges = {
		"temperature": (35.5, 37.5),
		"ke_spo2": (94, None),
		"pulse": _band(PULSE, age),
		"respiratory_rate": _band(RESPIRATION, age),
	}
	if age is None or age >= 13:
		ranges["bp_systolic"] = (90, 139)
		ranges["bp_diastolic"] = (60, 89)
	if age is None or age >= 18:
		ranges["bmi"] = (18.5, 24.9)
	return ranges


def age_in_years(dob, on=None):
	if not dob:
		return None
	dob, on = getdate(dob), getdate(on or nowdate())
	return on.year - dob.year - ((on.month, on.day) < (dob.month, dob.day))


def abnormal_readings(values, age):
	"""[(fieldname, text)] for each reading outside its range, e.g.
	("temperature", "Temperature 38.6 °C (high)")."""
	out = []
	ranges = ranges_for(age)
	for fieldname, label, unit in READINGS:
		if fieldname not in ranges:
			continue
		value = _number(values.get(fieldname))
		if value is None or (fieldname == "bmi" and not value):
			continue
		low, high = ranges[fieldname]
		direction = (
			_("low")
			if low is not None and value < low
			else _("high")
			if high is not None and value > high
			else None
		)
		if direction:
			shown = f"{value:g}"
			out.append((fieldname, f"{_(label)} {shown}{(' ' + unit) if unit else ''} ({direction})"))
	return out


def validate_vital_signs(doc, method=None):
	"""Vital Signs validate: set the Normal/Abnormal status and list what is out of range."""
	if not doc.get("bmi") and flt(doc.get("height")) and flt(doc.get("weight")):
		# Marley works BMI out in the browser; fill it for records saved another way (height in metres).
		doc.bmi = round(flt(doc.weight) / (flt(doc.height) ** 2), 2)
	dob = frappe.db.get_value("Patient", doc.patient, "dob") if doc.get("patient") else None
	flags = abnormal_readings(doc.as_dict(), age_in_years(dob, doc.get("signs_date")))
	measured = any(_number(doc.get(f)) for f, _l, _u in READINGS)
	doc.ke_vitals_status = ("Abnormal" if flags else "Normal") if measured else ""
	doc.ke_vitals_flags = "\n".join(text for _f, text in flags)
	doc.ke_abnormal_fields = ",".join(f for f, _t in flags)
