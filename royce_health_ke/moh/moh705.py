# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""MOH 705A (under 5) / 705B (5 and over) outpatient summary: one row per
indicator, one column per day of the month, plus the total.

Counting rules (confirm with the hospital's Health Records Officer):
- Outpatient encounters only (no inpatient record), submitted, in the month.
- Age at the end of the month decides the form; no date of birth -> 705B.
- Diagnoses: a Diagnosis mapped explicitly to an indicator wins; otherwise
  the indicator with the longest code prefix matching one of the diagnosis's
  codes (ICD-10 or ICD-11); otherwise 'All other diseases'.
- New cases only: a patient counts once per indicator per month, on the
  first day seen for it.
- First attendance: the patient's first outpatient day at the hospital in
  the calendar year; later days are re-attendances.
- Tested malaria (Lab Test rows): every submitted test of a mapped template
  or code, on its test date."""

import calendar
from collections import defaultdict
from datetime import date

import frappe
from frappe.utils import getdate

FORMS = {"705A": lambda age: age is not None and age < 5, "705B": lambda age: age is None or age >= 5}


def period(year, month):
	year, month = int(year), int(month)
	return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


def age_on(dob, on_date):
	if not dob:
		return None
	dob = getdate(dob)
	return on_date.year - dob.year - ((on_date.month, on_date.day) < (dob.month, dob.day))


class Mapping:
	"""The form's indicators and what counts toward each."""

	def __init__(self, form):
		self.indicators = frappe.get_all(
			"MOH 705 Indicator",
			filters={"form": form, "disabled": 0},
			fields=["name", "code", "label", "kind"],
			order_by="sequence asc, code asc",
		)
		kinds = {i.name: i.kind for i in self.indicators}
		self.by_kind = defaultdict(list)
		for i in self.indicators:
			self.by_kind[i.kind].append(i.name)
		self.prefixes = []  # (system, prefix, indicator) for Diagnosis rows
		self.diagnoses = {}
		self.lab_templates = {}
		self.lab_codes = []  # (system, prefix, indicator) for Lab Test rows
		for row in frappe.get_all(
			"MOH 705 Indicator Code",
			filters={"parent": ["in", list(kinds)], "parenttype": "MOH 705 Indicator"},
			fields=["parent", "code_system", "code_prefix", "diagnosis", "lab_test_template"],
		):
			if kinds[row.parent] == "Lab Test":
				if row.lab_test_template:
					self.lab_templates[row.lab_test_template] = row.parent
				if row.code_system and row.code_prefix:
					self.lab_codes.append((row.code_system, row.code_prefix.upper(), row.parent))
			else:
				if row.diagnosis:
					self.diagnoses[row.diagnosis] = row.parent
				if row.code_system and row.code_prefix:
					self.prefixes.append((row.code_system, row.code_prefix.upper(), row.parent))

	def indicator_for(self, diagnosis, codes):
		"""`codes`: [(code_system, code)] carried by the diagnosis."""
		if diagnosis in self.diagnoses:
			return self.diagnoses[diagnosis]
		return longest_prefix(self.prefixes, codes) or next(iter(self.by_kind["All Other Diseases"]), None)

	def lab_indicator_for(self, template, codes):
		return self.lab_templates.get(template) or longest_prefix(self.lab_codes, codes)


def longest_prefix(prefixes, codes):
	best, best_len = None, -1
	for system, code in codes:
		code = (code or "").upper()
		for p_system, prefix, indicator in prefixes:
			if p_system == system and code.startswith(prefix) and len(prefix) > best_len:
				best, best_len = indicator, len(prefix)
	return best


def codings(doctype, names):
	"""{name: [(code_system, code)]} from the codification tables."""
	out = defaultdict(list)
	if names:
		for row in frappe.get_all(
			"Codification Table",
			filters={"parenttype": doctype, "parent": ["in", list(names)]},
			fields=["parent", "code_system", "code"],
		):
			out[row.parent].append((row.code_system, row.code))
	return out


def compute(company, year, month, form):
	start, end = period(year, month)
	in_form = FORMS[form]
	mapping = Mapping(form)
	counts = defaultdict(lambda: defaultdict(int))  # indicator -> day -> count

	encounters = frappe.get_all(
		"Patient Encounter",
		filters={
			"company": company,
			"docstatus": 1,
			"encounter_date": ["between", [start, end]],
			"inpatient_record": ["in", ["", None]],
		},
		fields=["name", "patient", "encounter_date", "source", "ke_referred_out"],
		order_by="encounter_date asc, encounter_time asc",
	)
	dobs = dict(
		frappe.get_all(
			"Patient",
			filters={"name": ["in", list({e.patient for e in encounters}) or [""]]},
			fields=["name", "dob"],
			as_list=True,
		)
	)
	age_ok = {p: in_form(age_on(dob, end)) for p, dob in dobs.items()}
	encounters = [e for e in encounters if age_ok.get(e.patient)]

	diagnoses = defaultdict(list)
	for row in frappe.get_all(
		"Patient Encounter Diagnosis",
		filters={"parenttype": "Patient Encounter", "parent": ["in", [e.name for e in encounters] or [""]]},
		fields=["parent", "diagnosis"],
	):
		diagnoses[row.parent].append(row.diagnosis)
	dx_codes = codings("Diagnosis", {d for ds in diagnoses.values() for d in ds})

	counted = set()  # (patient, indicator): new cases once a month
	seen_days = set()  # (patient, date): attendance once a day
	for e in encounters:
		day = getdate(e.encounter_date)
		for dx in diagnoses[e.name]:
			indicator = mapping.indicator_for(dx, dx_codes.get(dx, []))
			if indicator and (e.patient, indicator) not in counted:
				counted.add((e.patient, indicator))
				counts[indicator][day.day] += 1
		if (e.patient, day) in seen_days:
			continue
		seen_days.add((e.patient, day))
		kind = "First Attendance" if first_visit_of_year(company, e.patient, day) else "Re-Attendance"
		for indicator in mapping.by_kind[kind]:
			counts[indicator][day.day] += 1
		if e.source == "External Referral":
			for indicator in mapping.by_kind["Referral In"]:
				counts[indicator][day.day] += 1
		if e.ke_referred_out:
			for indicator in mapping.by_kind["Referral Out"]:
				counts[indicator][day.day] += 1

	_count_lab_tests(company, start, end, in_form, mapping, counts)
	return [
		{
			"code": i.code,
			"indicator": i.label,
			**{f"d{d}": counts[i.name].get(d, 0) for d in range(1, 32)},
			"total": sum(counts[i.name].values()),
		}
		for i in mapping.indicators
	]


def first_visit_of_year(company, patient, day):
	return not frappe.db.exists(
		"Patient Encounter",
		{
			"company": company,
			"patient": patient,
			"docstatus": 1,
			"inpatient_record": ["in", ["", None]],
			"encounter_date": ["between", [date(day.year, 1, 1), frappe.utils.add_days(day, -1)]],
		},
	)


def _count_lab_tests(company, start, end, in_form, mapping, counts):
	if not mapping.by_kind["Lab Test"]:
		return
	tests = lab_tests(company, start, end)
	dobs = dict(
		frappe.get_all(
			"Patient",
			filters={"name": ["in", list({t.patient for t in tests}) or [""]]},
			fields=["name", "dob"],
			as_list=True,
		)
	)
	template_codes = codings("Lab Test Template", {t.template for t in tests})
	for t in tests:
		if not in_form(age_on(dobs.get(t.patient), end)):
			continue
		indicator = mapping.lab_indicator_for(t.template, template_codes.get(t.template, []))
		if indicator:
			counts[indicator][t.test_date.day] += 1


def lab_tests(company, start, end):
	"""Submitted lab tests done in the period, each with `test_date`: the
	test's date, or its result date when Marley left the date empty (tests
	made from a service request have no date)."""
	tests = frappe.get_all(
		"Lab Test",
		filters={"company": company, "docstatus": 1},
		or_filters=[["date", "between", [start, end]], ["result_date", "between", [start, end]]],
		fields=["name", "patient", "template", "date", "result_date"],
	)
	out = []
	for t in tests:
		t.test_date = getdate(t.date or t.result_date)
		if start <= t.test_date <= end:
			out.append(t)
	return out
