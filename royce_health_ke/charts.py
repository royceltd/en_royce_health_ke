# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Nursing charts as data (Bethesda proposals, 18 Nov 2026: feeding, blood
transfusion and "other charts, configurable as new needs arise").

A Nursing Chart Template is the hospital's chart: its columns (number, text,
yes/no or a choice), units, alert ranges, which numbers are totalled per 24
hours, and whether a second nurse checks each entry. A Nursing Chart Entry is
one reading, stamped with who, when and the shift. A new chart is a new
template, not a release.

Fluid intake and output stays Marley's chart (its Nursing Dialog and 24-hour
balance); pain and GCS are Marley's vital signs and assessments."""

import frappe
from frappe import _
from frappe.utils import add_to_date, cint, flt, now_datetime

TEMPLATE, ENTRY = "Nursing Chart Template", "Nursing Chart Entry"
YES_NO = ("Yes", "No")


def _template(name):
	doc = frappe.get_cached_doc(TEMPLATE, name)
	if cint(doc.disabled):
		frappe.throw(_("The chart {0} is disabled.").format(name))
	return doc


def validate_entry(doc):
	from royce_health_ke.inpatient import ON_WARD, shift_of

	template = _template(doc.template)
	if doc.is_new():
		doc.recorded_by = frappe.session.user
	if not doc.inpatient_record:
		doc.inpatient_record = frappe.db.get_value(
			"Inpatient Record", {"patient": doc.patient, "status": ["in", ON_WARD]}, "name"
		)
	doc.shift = shift_of(doc.recorded_at or now_datetime())
	given = {(v.column_label or "").strip(): (v.value or "").strip() for v in doc.get("values") or []}
	doc.set("values", [])
	alerts = []
	for col in template.columns:
		value = given.get(col.label, "")
		if not value:
			if cint(col.reqd):
				frappe.throw(_("{0}: enter {1}.").format(template.template_name, col.label))
			continue
		flag = ""
		if col.kind == "Number":
			try:
				number = float(value)
			except ValueError:
				frappe.throw(_("{0} must be a number.").format(col.label))
			if col.low is not None and flt(col.low) and number < flt(col.low):
				flag = _("low")
			elif col.high is not None and flt(col.high) and number > flt(col.high):
				flag = _("high")
		elif col.kind == "Yes or No" and value not in YES_NO:
			frappe.throw(_("{0}: answer Yes or No.").format(col.label))
		elif col.kind == "Choice":
			choices = [c.strip() for c in (col.options or "").split("\n") if c.strip()]
			if choices and value not in choices:
				frappe.throw(_("{0}: choose one of {1}.").format(col.label, ", ".join(choices)))
		if flag:
			alerts.append(f"{col.label} {value} {col.unit or ''} ({flag})".replace("  ", " "))
		doc.append("values", {"column_label": col.label, "value": value, "unit": col.unit, "flag": flag})
	if not doc.get("values"):
		frappe.throw(_("Enter at least one reading."))
	unknown = set(given) - {c.label for c in template.columns}
	if unknown:
		frappe.throw(_("{0} has no column {1}.").format(template.template_name, ", ".join(sorted(unknown))))
	if cint(template.needs_second_signature):
		if not doc.second_check_by:
			frappe.throw(_("{0}: a second nurse checks each entry.").format(template.template_name))
		if doc.second_check_by == doc.recorded_by:
			frappe.throw(_("The second check is by another nurse."))
	doc.alerts = "; ".join(alerts)


@frappe.whitelist()
def record(
	inpatient_record: str,
	template: str,
	values: str | dict,
	note: str | None = None,
	second_check_by: str | None = None,
	recorded_at: str | None = None,
) -> str:
	"""A reading on a chart, from the patient screen."""
	frappe.has_permission(ENTRY, "create", throw=True)
	values = frappe.parse_json(values) if isinstance(values, str) else values
	patient = frappe.db.get_value("Inpatient Record", inpatient_record, "patient")
	doc = frappe.get_doc(
		{
			"doctype": ENTRY,
			"template": template,
			"patient": patient,
			"inpatient_record": inpatient_record,
			"recorded_at": recorded_at or now_datetime(),
			"second_check_by": second_check_by,
			"note": note,
			"values": [
				{"column_label": k, "value": str(v)} for k, v in (values or {}).items() if v not in (None, "")
			],
		}
	)
	doc.insert()
	return doc.name


def panel(ip):
	"""The Nursing Care tab: each chart with its columns, latest entries and
	24-hour totals, plus Marley's fluid balance."""
	templates = frappe.get_all(
		TEMPLATE,
		filters={"disabled": 0},
		fields=["name", "description", "interval_hours", "needs_second_signature"],
		order_by="sequence asc, name asc",
	)
	since = add_to_date(now_datetime(), hours=-24)
	out = []
	for t in templates:
		doc = frappe.get_cached_doc(TEMPLATE, t.name)
		entries = frappe.get_all(
			ENTRY,
			filters={"inpatient_record": ip.name, "template": t.name},
			fields=["name", "recorded_at", "recorded_by", "second_check_by", "shift", "note", "alerts"],
			order_by="recorded_at desc",
			limit=50,
		)
		values = frappe.get_all(
			"Nursing Chart Value",
			filters={"parenttype": ENTRY, "parent": ["in", [e.name for e in entries] or [""]]},
			fields=["parent", "column_label", "value", "unit", "flag"],
		)
		by_entry = {}
		for v in values:
			by_entry.setdefault(v.parent, {})[v.column_label] = v
		totals = {}
		for e in entries:
			e.readings = by_entry.get(e.name, {})
			e.by = frappe.utils.get_fullname(e.recorded_by) if e.recorded_by else ""
			if e.recorded_at and frappe.utils.get_datetime(e.recorded_at) >= since:
				for col in doc.columns:
					if cint(col.total) and col.label in e.readings:
						totals[col.label] = totals.get(col.label, 0) + flt(e.readings[col.label].value)
		due = None
		if cint(t.interval_hours):
			last = entries[0].recorded_at if entries else None
			due = add_to_date(last, hours=cint(t.interval_hours)) if last else now_datetime()
		out.append(
			{
				"name": t.name,
				"description": t.description,
				"second_check": cint(t.needs_second_signature),
				"columns": [
					{
						"label": c.label,
						"kind": c.kind,
						"unit": c.unit,
						"options": c.options,
						"reqd": cint(c.reqd),
					}
					for c in doc.columns
				],
				"entries": entries,
				"totals": totals,
				"due": due,
			}
		)
	fluid = None
	try:
		from royce_health_ke.marley import get_intake_output_summary

		fluid = get_intake_output_summary(ip.patient, 24)
	except Exception:
		fluid = None
	return {"charts": out, "fluid": fluid}


SEED = (
	{
		"template_name": "Feeding Chart",
		"sequence": 10,
		"description": "What the patient ate or was fed, how, and how much.",
		"columns": [
			{
				"label": "Route",
				"kind": "Choice",
				"options": "Oral\nNasogastric tube\nBreastfeeding\nCup feeding\nGastrostomy",
				"reqd": 1,
			},
			{"label": "Feed or food", "kind": "Text"},
			{"label": "Amount", "kind": "Number", "unit": "ml", "total": 1},
			{"label": "Tolerated", "kind": "Yes or No"},
		],
	},
	{
		"template_name": "Blood Transfusion",
		"sequence": 20,
		"needs_second_signature": 1,
		"description": "Each unit: checks at the start, after 15 minutes, hourly and at the end. A second nurse checks.",
		"columns": [
			{
				"label": "Product",
				"kind": "Choice",
				"options": "Whole blood\nPacked red cells\nPlatelets\nFresh frozen plasma\nCryoprecipitate",
				"reqd": 1,
			},
			{"label": "Unit number", "kind": "Text", "reqd": 1},
			{"label": "Stage", "kind": "Choice", "options": "Start\n15 minutes\nHourly\nEnd", "reqd": 1},
			{"label": "Volume given", "kind": "Number", "unit": "ml", "total": 1},
			{"label": "Temperature", "kind": "Number", "unit": "°C", "low": 35.5, "high": 38},
			{"label": "Pulse", "kind": "Number", "unit": "/min", "low": 50, "high": 120},
			{"label": "BP systolic", "kind": "Number", "unit": "mmHg", "low": 90, "high": 180},
			{"label": "Reaction", "kind": "Yes or No", "reqd": 1},
		],
	},
	{
		"template_name": "Hygiene and Turning",
		"sequence": 30,
		"interval_hours": 2,
		"description": "Bed bath, oral care, turning and pressure-area care.",
		"columns": [
			{
				"label": "Care given",
				"kind": "Choice",
				"options": "Bed bath\nOral care\nTurned\nPressure area care\nLinen changed\nCatheter care\nEye care",
				"reqd": 1,
			},
			{"label": "Position", "kind": "Choice", "options": "Left side\nRight side\nBack\nSitting up"},
			{"label": "Skin intact", "kind": "Yes or No"},
		],
	},
)


def seed():
	"""The default charts, made once; afterwards the hospital's (ADR-023)."""
	for row in SEED:
		if not frappe.db.exists(TEMPLATE, row["template_name"]):
			frappe.get_doc({"doctype": TEMPLATE, **row}).insert(ignore_permissions=True)
