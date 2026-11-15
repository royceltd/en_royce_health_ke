# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Child growth against the WHO Child Growth Standards (birth to 5 years).

- Tables: WHO's LMS tables, downloaded from WHO's own repository
  (github.com/WorldHealthOrganization/anthro, data-raw/growthstandards) into
  the site's private folder by an explicit action (Kenya Health Settings >
  Load WHO Growth Standards, or `bench execute royce_health_ke.growth.sync`).
  Like ICD-11, they are used as published and never copied into this
  repository; a migrate never depends on the internet.
- Z-scores: the LMS method, with WHO's restricted computation beyond +/-3 SD
  for the weight-based indicators (weight-for-age, weight-for-length/height,
  BMI-for-age), exactly as WHO Anthro computes them.
- Length vs height: under 2 years (731 days) the child is measured lying down
  (length), from 2 years standing (height), as the standards assume.
- Classification (WHO): weight-for-length/height < -3 severe wasting (SAM),
  < -2 moderate wasting (MAM), > +2 overweight, > +3 obese; length/height-for-
  age < -2 stunted (< -3 severely); weight-for-age < -2 underweight (< -3
  severely). The clinician decides; the system only shows where the child is.

Every Vital Signs record of a child under 5 with a weight and/or height gets
its z-scores and nutrition status, and the patient's Growth Chart plots every
measurement against the WHO curves."""

import json
import math
import os

import frappe
import requests
from frappe import _
from frappe.utils import flt, getdate

SOURCE = "https://raw.githubusercontent.com/WorldHealthOrganization/anthro/master/data-raw/growthstandards/{name}.txt"
TABLES = {
	# indicator: (WHO file, x column)
	"wfa": ("weianthro", "age"),
	"lhfa": ("lenanthro", "age"),
	"wfl": ("wflanthro", "length"),
	"wfh": ("wfhanthro", "height"),
	"bmi": ("bmianthro", "age"),
}
WEIGHT_BASED = {"wfa", "wfl", "wfh", "bmi"}
MAX_DAYS = 1856  # 5 years 1 month: the end of the 0-5 standards
LENGTH_UNTIL_DAYS = 731
FILE = "who_growth_standards.json"
SEX = {"Male": 1, "Female": 2}

_tables = None


# Tables -------------------------------------------------------------------------


def _path():
	return frappe.get_site_path("private", "files", FILE)


def loaded() -> bool:
	return os.path.exists(_path())


@frappe.whitelist()
def sync():
	"""Download WHO's LMS tables into the site's private folder."""
	frappe.only_for(("System Manager", "Healthcare Administrator"))
	data = {}
	for indicator, (name, x_column) in TABLES.items():
		response = requests.get(SOURCE.format(name=name), timeout=60)
		response.raise_for_status()
		data[indicator] = parse(response.text, x_column)
	os.makedirs(os.path.dirname(_path()), exist_ok=True)
	with open(_path(), "w") as f:
		json.dump(data, f)
	global _tables
	_tables = None
	return {indicator: sum(len(v) for v in rows.values()) for indicator, rows in data.items()}


def parse(text, x_column):
	"""{"1"|"2": {x: [L, M, S]}} from a WHO tab-separated LMS table."""
	lines = [line.split("\t") for line in text.strip().splitlines()]
	head = [h.strip().lower() for h in lines[0]]
	at = {h: i for i, h in enumerate(head)}
	out = {"1": {}, "2": {}}
	for row in lines[1:]:
		sex = row[at["sex"]].strip()
		x = row[at[x_column]].strip()
		out[sex][_key(x, x_column)] = [float(row[at["l"]]), float(row[at["m"]]), float(row[at["s"]])]
	return out


def _key(x, x_column):
	"""Table keys: whole days for age tables, always one decimal for length /
	height (74 cm -> "74.0"), matching the lookup in `lms`."""
	value = float(x)
	return str(int(value)) if x_column == "age" else f"{value:.1f}"


def tables():
	global _tables
	if _tables is None:
		if not loaded():
			return None
		with open(_path()) as f:
			_tables = json.load(f)
	return _tables


def lms(indicator, sex, x):
	"""(L, M, S) for this sex at age x (days) or length/height x (cm), or None
	outside the standards. Length/height is rounded to the nearest 0.1 cm and
	interpolation is not needed: the tables are per day / per millimetre."""
	t = tables()
	if not t or sex not in (1, 2):
		return None
	key = str(round(x)) if indicator in ("wfa", "lhfa", "bmi") else f"{round(x, 1):.1f}"
	row = t[indicator][str(sex)].get(key)
	return tuple(row) if row else None


# Z-scores -----------------------------------------------------------------------


def _value_at(L, M, S, z):
	return M * (1 + L * S * z) ** (1 / L) if L else M * math.exp(S * z)


def zscore(indicator, sex, x, value):
	"""The WHO z-score of `value` (kg, cm or BMI), or None."""
	params = lms(indicator, sex, x)
	if not params or not value:
		return None
	L, M, S = params
	z = ((value / M) ** L - 1) / (L * S) if L else math.log(value / M) / S
	if indicator in WEIGHT_BASED and abs(z) > 3:
		# WHO's restricted application of the LMS method beyond +/-3 SD.
		if z > 3:
			sd3, sd23 = _value_at(L, M, S, 3), _value_at(L, M, S, 3) - _value_at(L, M, S, 2)
			z = 3 + (value - sd3) / sd23
		else:
			sd3, sd23 = _value_at(L, M, S, -3), _value_at(L, M, S, -2) - _value_at(L, M, S, -3)
			z = -3 + (value - sd3) / sd23
	return round(z, 2)


def age_days(dob, on):
	return (getdate(on) - getdate(dob)).days


def assess(sex, dob, on, weight=None, height_cm=None):
	"""{"wfa", "lhfa", "wflh", "bmi": z or None, "status": text} for a child
	under 5, or None (older, no date of birth/sex, or tables not loaded)."""
	sex = SEX.get(sex)
	if not sex or not dob or not tables():
		return None
	days = age_days(dob, on)
	if days < 0 or days > MAX_DAYS:
		return None
	weight, height_cm = flt(weight) or None, flt(height_cm) or None
	lying = days < LENGTH_UNTIL_DAYS
	out = {
		"wfa": zscore("wfa", sex, days, weight),
		"lhfa": zscore("lhfa", sex, days, height_cm),
		"wflh": zscore("wfl" if lying else "wfh", sex, height_cm, weight) if height_cm else None,
		"bmi": zscore("bmi", sex, days, weight / (height_cm / 100) ** 2) if weight and height_cm else None,
	}
	out["status"] = status(out)
	return out


def status(z):
	notes = []
	w = z.get("wflh")
	if w is not None:
		if w < -3:
			notes.append(_("Severe wasting (SAM)"))
		elif w < -2:
			notes.append(_("Moderate wasting (MAM)"))
		elif w > 3:
			notes.append(_("Obese"))
		elif w > 2:
			notes.append(_("Overweight"))
	h = z.get("lhfa")
	if h is not None and h < -2:
		notes.append(_("Severely stunted") if h < -3 else _("Stunted"))
	a = z.get("wfa")
	if a is not None and a < -2:
		notes.append(_("Severely underweight") if a < -3 else _("Underweight"))
	if not notes and any(v is not None for k, v in z.items() if k != "status"):
		notes.append(_("Normal growth"))
	return ", ".join(notes)


# Vital Signs ----------------------------------------------------------------------


def apply_to_vital_signs(doc):
	"""Called from Vital Signs validate: z-scores and nutrition status for
	children under 5 (cleared for anyone else)."""
	fields = ("ke_wfa_z", "ke_lhfa_z", "ke_wflh_z", "ke_bmi_z", "ke_nutrition_status")
	result = None
	if doc.get("patient") and (doc.get("weight") or doc.get("height")):
		p = frappe.db.get_value("Patient", doc.patient, ["sex", "dob"], as_dict=True)
		if p:
			height_cm = flt(doc.get("height")) * 100 if doc.get("height") else None
			result = assess(p.sex, p.dob, doc.get("signs_date") or getdate(), doc.get("weight"), height_cm)
	for field in fields:
		doc.set(field, None)
	if result:
		doc.ke_wfa_z, doc.ke_lhfa_z, doc.ke_wflh_z, doc.ke_bmi_z = (
			result["wfa"],
			result["lhfa"],
			result["wflh"],
			result["bmi"],
		)
		doc.ke_nutrition_status = result["status"]


# Growth chart -------------------------------------------------------------------------

CHARTS = {
	"wfa": (_("Weight-for-age (kg)"), "weight"),
	"lhfa": (_("Length/height-for-age (cm)"), "height"),
}
CURVES = (-3, -2, 0, 2, 3)


@frappe.whitelist()
def chart(patient: str, indicator: str = "wfa"):
	"""WHO curves (-3, -2, median, +2, +3 SD) by month from birth to 5 years,
	and the patient's own measurements, for a Frappe line chart."""
	frappe.has_permission("Patient", "read", patient, throw=True)
	if indicator not in CHARTS:
		frappe.throw(_("Unknown growth chart"))
	if not tables():
		frappe.throw(_("Load the WHO growth standards first (Kenya Health Settings)."))
	p = frappe.db.get_value("Patient", patient, ["sex", "dob", "patient_name"], as_dict=True)
	sex = SEX.get(p.sex)
	if not sex or not p.dob:
		frappe.throw(_("The patient's sex and date of birth are needed for a growth chart."))
	title, field = CHARTS[indicator]
	months = list(range(0, 61))
	curves = {z: [] for z in CURVES}
	for m in months:
		L, M, S = lms(indicator, sex, round(m * 30.4375))
		for z in CURVES:
			curves[z].append(round(_value_at(L, M, S, z), 2))
	measurements = []
	for v in frappe.get_all(
		"Vital Signs",
		filters={"patient": patient, "docstatus": ["!=", 2], field: [">", 0]},
		fields=["signs_date", "weight", "height"],
		order_by="signs_date asc",
	):
		days = age_days(p.dob, v.signs_date)
		if 0 <= days <= MAX_DAYS:
			value = flt(v.weight) if field == "weight" else round(flt(v.height) * 100, 1)
			measurements.append(
				{
					"date": str(v.signs_date),
					"months": round(days / 30.4375, 1),
					"value": value,
					"z": zscore(indicator, sex, days, value),
				}
			)
	return {
		"title": title,
		"patient_name": p.patient_name,
		"months": months,
		"curves": [{"z": z, "values": curves[z]} for z in CURVES],
		"measurements": measurements,
	}
