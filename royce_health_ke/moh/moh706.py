# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""MOH 706 monthly laboratory summary. Rows are MOH 706 Indicator records
(seeded from KenyaEMR, see seed706.py), each mapped by the lab to its own
Lab Test Templates, so the lab manager can correct or add rows without code.

A row counts submitted lab tests done in the month (test date, else result
date, as MOH 705), optionally only one result line of a compound test (the
Component) and one age group:
- Tests done: tests with that template (and component line).
- Positive: the result contains one of the row's positive words and none of
  NEGATIVE_WORDS ("non-reactive" contains "reactive").
- Numeric range: the result's number is from the row's low value up to,
  not including, its high value."""

import re
from collections import defaultdict

import frappe
from frappe.utils import flt

from royce_health_ke.moh.moh705 import age_on, lab_tests, period

NEGATIVE_WORDS = (
	"negative",
	"non-reactive",
	"nonreactive",
	"non reactive",
	"not seen",
	"none seen",
	"nil",
	"absent",
	"not detected",
)
NOT_MAPPED = "Not mapped to a lab test"
NUMBER = re.compile(r"-?\d+(?:\.\d+)?")


def is_positive(value, words):
	text = (value or "").strip().lower()
	if not text or any(n in text for n in NEGATIVE_WORDS):
		return False
	return any(w and w in text for w in words)


def number(value):
	match = NUMBER.search((value or "").replace(",", ""))
	return float(match.group()) if match else None


def in_range(value, low, high):
	n = number(value)
	return n is not None and bool(high) and flt(low) <= n < flt(high)


def matches_age(age, group):
	if not group:
		return True
	if age is None:
		return False
	return age < 5 if group == "Under 5" else age >= 5


def results_by_test(names):
	"""lab test -> [(line name, result value)] from normal and descriptive results."""
	out = defaultdict(list)
	if not names:
		return out
	for r in frappe.get_all(
		"Normal Test Result",
		filters={"parenttype": "Lab Test", "parent": ["in", names]},
		fields=["parent", "lab_test_name", "lab_test_event", "result_value"],
		order_by="idx asc",
	):
		out[r.parent].append(((r.lab_test_event or r.lab_test_name or "").strip().lower(), r.result_value))
		if r.lab_test_event and r.lab_test_name:  # compound: also findable by the parent line's name
			out[r.parent].append((r.lab_test_name.strip().lower(), r.result_value))
	for r in frappe.get_all(
		"Descriptive Test Result",
		filters={"parenttype": "Lab Test", "parent": ["in", names]},
		fields=["parent", "lab_test_particulars", "result_value"],
		order_by="idx asc",
	):
		out[r.parent].append(((r.lab_test_particulars or "").strip().lower(), r.result_value))
	return out


def indicators():
	rows = frappe.get_all(
		"MOH 706 Indicator",
		filters={"disabled": 0},
		fields=[
			"name",
			"code",
			"label",
			"section",
			"kind",
			"positive_results",
			"range_low",
			"range_high",
			"age_group",
		],
		order_by="sequence asc, code asc",
	)
	tests = defaultdict(list)
	for t in frappe.get_all(
		"MOH 706 Indicator Test",
		filters={"parenttype": "MOH 706 Indicator"},
		fields=["parent", "lab_test_template", "component"],
	):
		tests[t.parent].append(t)
	for r in rows:
		r.tests = tests.get(r.name, [])
		r.words = [w.strip().lower() for w in (r.positive_results or "").split(",") if w.strip()]
	return rows


def count(indicator, tests, results, ages):
	n = 0
	for mapping in indicator.tests:
		component = (mapping.component or "").strip().lower()
		for t in tests:
			if t.template != mapping.lab_test_template or not matches_age(
				ages.get(t.name), indicator.age_group
			):
				continue
			lines = results.get(t.name, [])
			if component:
				lines = [line for line in lines if line[0] == component]
				if not lines:
					continue
			values = [v for _line, v in lines]
			if indicator.kind == "Tests done":
				n += 1
			elif indicator.kind == "Positive":
				n += any(is_positive(v, indicator.words) for v in values)
			elif indicator.kind == "Numeric range":
				first = next((v for v in values if number(v) is not None), None)
				n += in_range(first, indicator.range_low, indicator.range_high)
	return n


def compute(company, year, month):
	start, end = period(year, month)
	tests = lab_tests(company, start, end)
	results = results_by_test([t.name for t in tests])
	dobs = dict(
		frappe.get_all(
			"Patient",
			filters={"name": ["in", list({t.patient for t in tests}) or [""]]},
			fields=["name", "dob"],
			as_list=True,
		)
	)
	ages = {t.name: age_on(dobs.get(t.patient), t.test_date) for t in tests}
	rows, section = [], None
	for ind in indicators():
		if ind.section != section:
			section = ind.section
			rows.append({"indicator": section, "value": None, "is_section": 1})
		if not ind.tests:
			rows.append(
				{
					"code": ind.code,
					"indicator": ind.label,
					"value": None,
					"note": NOT_MAPPED,
					"name": ind.name,
				}
			)
			continue
		if ind.kind == "Numeric range" and not ind.range_high:
			rows.append(
				{
					"code": ind.code,
					"indicator": ind.label,
					"value": None,
					"note": "No range set",
					"name": ind.name,
				}
			)
			continue
		rows.append(
			{
				"code": ind.code,
				"indicator": ind.label,
				"value": count(ind, tests, results, ages),
				"name": ind.name,
			}
		)
	return rows
