# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Clinical quality measures: capture, calculate, import and export.

- Capture: the data each measure needs is what the hospital already records
  (consultations and diagnoses, vital signs, lab results and their times,
  admissions and discharges, ANC and deliveries, clinical alerts). Measures
  the system can't calculate are typed in ("Entered or Imported").
- Calculate: each Quality Measure has a method; `calculate` gives the
  numerator, denominator and rate for a company and period. The Quality
  Measures report shows them and saves them as Quality Measure Results.
- Export: the period's results as CSV, or as HL7 FHIR R4 MeasureReport
  resources in a Bundle (the standard the Kenya HIE uses; measureScore is the
  proportion 0-1).
- Import: the same CSV, or a FHIR MeasureReport / Bundle, e.g. results
  calculated elsewhere; saved as Quality Measure Results (source Imported).

Seeded measures (moh/seed_quality.py) are a starting set; the hospital's
quality committee sets the measures and targets (ADR-023)."""

import csv
import io
import json

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, get_datetime, getdate, now_datetime

from royce_health_ke.moh.moh705 import codings
from royce_health_ke.vitals import _number, age_in_years

MEASURE_URI = "urn:ke:royce:quality-measure:"
POPULATION = "http://terminology.hl7.org/CodeSystem/measure-population"
CSV_COLUMNS = [
	"measure_code",
	"measure_name",
	"period_start",
	"period_end",
	"numerator",
	"denominator",
	"rate",
]


def _words(text):
	return [w.strip().lower() for w in (text or "").replace("\n", ",").split(",") if w.strip()]


def score(measure, numerator, denominator):
	"""(rate %, target %, "Yes"/"No"/"") for a result."""
	m = (
		frappe.db.get_value("Quality Measure", measure, ["target_percent", "higher_is_better"], as_dict=True)
		or {}
	)
	rate = round(100 * flt(numerator) / flt(denominator), 1) if cint(denominator) else 0
	target = m.get("target_percent")
	met = ""
	if target and cint(denominator):
		met = "Yes" if (rate >= target if cint(m.get("higher_is_better", 1)) else rate <= target) else "No"
	return rate, target, met


# Calculation -----------------------------------------------------------------------------


def _encounters(m, company, start, end):
	"""Submitted consultations in the period that match the measure's age band
	and diagnosis prefixes (all consultations when there are none)."""
	rows = frappe.get_all(
		"Patient Encounter",
		filters={"company": company, "docstatus": 1, "encounter_date": ["between", [start, end]]},
		fields=["name", "patient", "encounter_date"],
	)
	if not rows:
		return []
	dobs = dict(
		frappe.get_all(
			"Patient",
			filters={"name": ["in", list({r.patient for r in rows})]},
			fields=["name", "dob"],
			as_list=True,
		)
	)
	out = []
	for r in rows:
		age = age_in_years(dobs.get(r.patient), r.encounter_date) if dobs.get(r.patient) else None
		if m.min_age_years and (age is None or age < m.min_age_years):
			continue
		if m.max_age_years and (age is None or age >= m.max_age_years):
			continue
		out.append(r)
	prefixes = [p.upper() for p in _words(m.diagnosis_prefixes)]
	if not prefixes:
		return out
	dx = frappe.get_all(
		"Patient Encounter Diagnosis",
		filters={"parenttype": "Patient Encounter", "parent": ["in", [r.name for r in out] or [""]]},
		fields=["parent", "diagnosis"],
	)
	codes = codings("Diagnosis", {d.diagnosis for d in dx})
	matching = {
		d.parent
		for d in dx
		if any(
			(code or "").upper().startswith(p) for _s, code in codes.get(d.diagnosis, []) for p in prefixes
		)
	}
	return [r for r in out if r.name in matching]


def vital_recorded(m, company, start, end):
	"""Consultations (age band / diagnoses) with the vital sign recorded that day."""
	encounters = _encounters(m, company, start, end)
	field = m.vital_sign or "bp_systolic"
	recorded = {
		(v.patient, getdate(v.signs_date))
		for v in frappe.get_all(
			"Vital Signs",
			filters={
				"patient": ["in", list({e.patient for e in encounters}) or [""]],
				"docstatus": ["!=", 2],
				"signs_date": ["between", [start, end]],
			},
			fields=["patient", "signs_date", field],
		)
		if _number(v.get(field))
	}
	numerator = sum(1 for e in encounters if (e.patient, getdate(e.encounter_date)) in recorded)
	return numerator, len(encounters)


def lab_result_for_diagnosis(m, company, start, end):
	"""Patients seen with the diagnosis in the period who had a matching lab
	result within `look_back_days` before (or on) their last such consultation."""
	encounters = _encounters(m, company, start, end)
	last_seen = {}
	for e in encounters:
		last_seen[e.patient] = max(getdate(e.encounter_date), last_seen.get(e.patient, getdate(start)))
	names = _words(m.lab_result_names)
	days = cint(m.look_back_days) or 90
	numerator = 0
	for patient, seen in last_seen.items():
		window = [add_days(seen, -days), seen]
		tests = frappe.get_all(
			"Lab Test",
			filters={"patient": patient, "docstatus": ["!=", 2]},
			or_filters=[["date", "between", window], ["result_date", "between", window]],
			pluck="name",
		)
		rows = frappe.get_all(
			"Normal Test Result",
			filters={"parenttype": "Lab Test", "parent": ["in", tests or [""]]},
			fields=["lab_test_name", "lab_test_event", "result_value"],
		)
		template_names = frappe.get_all(
			"Lab Test", filters={"name": ["in", tests or [""]]}, pluck="lab_test_name"
		)
		labels = [f"{r.lab_test_name or ''} {r.lab_test_event or ''}".lower() for r in rows if r.result_value]
		labels += [(t or "").lower() for t in template_names]
		if any(n in label for n in names for label in labels):
			numerator += 1
	return numerator, len(last_seen)


def lab_turnaround(m, company, start, end):
	from royce_health_ke.tat import lab_rows, with_minutes

	rows = [with_minutes(r) for r in lab_rows(start, end, company)]
	rows = [r for r in rows if r["total_minutes"] is not None]
	target = cint(m.target_minutes) or 120
	return sum(1 for r in rows if r["total_minutes"] <= target), len(rows)


def alerts_answered(m, company, start, end):
	logs = frappe.get_all(
		"Clinical Alert Log",
		filters={"company": company, "shown_on": ["between", [f"{start} 00:00:00", f"{end} 23:59:59"]]},
		pluck="response",
	)
	return sum(1 for r in logs if r in ("Acted On", "Overridden")), len(logs)


def inpatient_deaths(m, company, start, end):
	discharges = frappe.get_all(
		"Inpatient Record",
		filters={
			"company": company,
			"discharge_datetime": ["between", [f"{start} 00:00:00", f"{end} 23:59:59"]],
		},
		pluck="ke_discharge_outcome",
	)
	return sum(1 for o in discharges if o == "Died"), len(discharges)


def anc_four_plus(m, company, start, end):
	deliveries = frappe.get_all(
		"Delivery Record",
		filters={
			"company": company,
			"docstatus": 1,
			"delivery_datetime": ["between", [f"{start} 00:00:00", f"{end} 23:59:59"]],
		},
		pluck="pregnancy_record",
	)
	numerator = 0
	for pregnancy in deliveries:
		if pregnancy and (frappe.db.count("ANC Visit", {"pregnancy_record": pregnancy, "docstatus": 1}) >= 4):
			numerator += 1
	return numerator, len(deliveries)


METHODS = {
	"Vital Recorded at Consultation": vital_recorded,
	"Lab Result for Diagnosis": lab_result_for_diagnosis,
	"Lab Turnaround Within Target": lab_turnaround,
	"Clinical Alerts Answered": alerts_answered,
	"Inpatient Deaths": inpatient_deaths,
	"Deliveries with 4+ ANC Contacts": anc_four_plus,
}


def calculate(company, from_date, to_date, measures=None):
	"""[{measure, measure_name, domain, numerator, denominator, rate, target,
	met, source}] for every enabled measure. Entered/imported measures show the
	saved result for exactly this period, if any."""
	start, end = getdate(from_date), getdate(to_date)
	out = []
	for m in frappe.get_all(
		"Quality Measure",
		filters={"enabled": 1, **({"name": ["in", measures]} if measures else {})},
		fields=["*"],
		order_by="domain asc, measure_code asc",
	):
		method = METHODS.get(m.method)
		source = "Calculated"
		if method:
			numerator, denominator = method(m, company, start, end)
		else:
			saved = frappe.db.get_value(
				"Quality Measure Result",
				{"measure": m.name, "company": company, "period_start": start, "period_end": end},
				["numerator", "denominator", "source"],
				as_dict=True,
			)
			numerator, denominator = (saved.numerator, saved.denominator) if saved else (None, None)
			source = saved.source if saved else _("Not entered")
		rate, target, met = (
			score(m.name, numerator, denominator) if denominator else (None, m.target_percent, "")
		)
		out.append(
			{
				"measure": m.name,
				"measure_name": m.measure_name,
				"domain": m.domain,
				"numerator": numerator,
				"denominator": denominator,
				"rate": rate,
				"target": target,
				"met": met,
				"source": source,
				"description": m.description,
			}
		)
	return out


def _save(measure, company, start, end, numerator, denominator, source, notes=None):
	name = frappe.db.get_value(
		"Quality Measure Result",
		{"measure": measure, "company": company, "period_start": start, "period_end": end},
	)
	doc = frappe.get_doc("Quality Measure Result", name) if name else frappe.new_doc("Quality Measure Result")
	doc.update(
		{
			"measure": measure,
			"company": company,
			"period_start": start,
			"period_end": end,
			"numerator": cint(numerator),
			"denominator": cint(denominator),
			"source": source,
		}
	)
	if notes:
		doc.notes = notes
	doc.save(ignore_permissions=True)
	return doc.name


@frappe.whitelist()
def save_results(company: str, from_date: str, to_date: str):
	"""Calculate and save the period's results (one per measure and period)."""
	frappe.only_for(("System Manager", "Healthcare Administrator"))
	saved = []
	for row in calculate(company, from_date, to_date):
		if row["source"] == "Calculated":
			saved.append(
				_save(
					row["measure"],
					company,
					getdate(from_date),
					getdate(to_date),
					row["numerator"],
					row["denominator"],
					"Calculated",
				)
			)
	return saved


# Export -----------------------------------------------------------------------------------


def _rows_for_export(company, from_date, to_date):
	return [r for r in calculate(company, from_date, to_date) if r["denominator"] is not None]


def to_csv(rows, from_date, to_date):
	out = io.StringIO()
	writer = csv.writer(out)
	writer.writerow(CSV_COLUMNS)
	for r in rows:
		writer.writerow(
			[
				r["measure"],
				r["measure_name"],
				str(from_date),
				str(to_date),
				r["numerator"],
				r["denominator"],
				r["rate"],
			]
		)
	return out.getvalue()


def to_fhir(rows, company, from_date, to_date):
	"""A FHIR R4 Bundle (collection) of summary MeasureReports."""
	now = get_datetime(now_datetime()).isoformat()
	entries = []
	for r in rows:
		denominator = cint(r["denominator"])
		report = {
			"resourceType": "MeasureReport",
			"status": "complete",
			"type": "summary",
			"measure": MEASURE_URI + r["measure"],
			"date": now,
			"reporter": {"display": company},
			"period": {"start": str(getdate(from_date)), "end": str(getdate(to_date))},
			"group": [
				{
					"code": {"text": r["measure_name"]},
					"population": [
						{
							"code": {"coding": [{"system": POPULATION, "code": "numerator"}]},
							"count": cint(r["numerator"]),
						},
						{
							"code": {"coding": [{"system": POPULATION, "code": "denominator"}]},
							"count": denominator,
						},
					],
					"measureScore": {
						"value": round(cint(r["numerator"]) / denominator, 4) if denominator else 0
					},
				}
			],
		}
		entries.append({"fullUrl": f"urn:uuid:{frappe.generate_hash(length=32)}", "resource": report})
	return {"resourceType": "Bundle", "type": "collection", "timestamp": now, "entry": entries}


@frappe.whitelist()
def export(company: str, from_date: str, to_date: str, fmt: str = "fhir"):
	"""Download the period's results: fmt "fhir" (JSON) or "csv"."""
	frappe.has_permission("Quality Measure Result", "export", throw=True)
	rows = _rows_for_export(company, from_date, to_date)
	if fmt == "csv":
		frappe.response.filename = f"quality-measures-{from_date}-{to_date}.csv"
		frappe.response.filecontent = to_csv(rows, from_date, to_date)
	else:
		frappe.response.filename = f"quality-measures-{from_date}-{to_date}.json"
		frappe.response.filecontent = json.dumps(to_fhir(rows, company, from_date, to_date), indent=1)
	frappe.response.type = "download"


# Import ------------------------------------------------------------------------------------


def parse_import(content):
	"""[(measure_code, start, end, numerator, denominator)] from CSV text or FHIR JSON."""
	text = content.decode("utf-8-sig") if isinstance(content, bytes) else content
	stripped = text.lstrip()
	if stripped.startswith("{"):
		data = json.loads(stripped)
		reports = (
			[e.get("resource", {}) for e in data.get("entry", [])]
			if data.get("resourceType") == "Bundle"
			else [data]
		)
		out = []
		for rep in reports:
			if rep.get("resourceType") != "MeasureReport":
				continue
			code = (rep.get("measure") or "").removeprefix(MEASURE_URI).rsplit("/", 1)[-1]
			counts = {}
			for group in rep.get("group", [])[:1]:
				for pop in group.get("population", []):
					for coding in pop.get("code", {}).get("coding", []):
						counts[coding.get("code")] = pop.get("count")
			period = rep.get("period", {})
			out.append(
				(
					code,
					period.get("start"),
					period.get("end"),
					counts.get("numerator"),
					counts.get("denominator"),
				)
			)
		return out
	reader = csv.DictReader(io.StringIO(text))
	return [
		(r["measure_code"], r["period_start"], r["period_end"], r.get("numerator"), r.get("denominator"))
		for r in reader
	]


@frappe.whitelist()
def import_results(company: str, file_url: str):
	"""Import results from an uploaded CSV or FHIR file. Unknown measure codes
	are reported, not created."""
	frappe.only_for(("System Manager", "Healthcare Administrator"))
	content = frappe.get_doc("File", {"file_url": file_url}).get_content()
	imported, unknown = [], []
	for code, start, end, numerator, denominator in parse_import(content):
		if not frappe.db.exists("Quality Measure", code):
			unknown.append(code)
			continue
		imported.append(
			_save(code, company, getdate(start), getdate(end), numerator, denominator, "Imported")
		)
	return {"imported": len(imported), "unknown": sorted(set(unknown))}
