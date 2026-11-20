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
	score, scored = 0.0, False
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
		elif col.kind == "Yes or No":
			if value not in YES_NO:
				frappe.throw(_("{0}: answer Yes or No.").format(col.label))
			if value == "Yes" and cint(col.alert_if_yes):
				flag = _("yes")
		elif col.kind in ("Choice", "Score"):
			choices = [c.strip() for c in (col.options or "").split("\n") if c.strip()]
			if choices and value not in choices:
				frappe.throw(_("{0}: choose one of {1}.").format(col.label, ", ".join(choices)))
			if col.kind == "Score":
				score += points(value)
				scored = True
		if flag:
			alerts.append(f"{col.label} {value} {col.unit or ''} ({flag})".replace("  ", " "))
		doc.append("values", {"column_label": col.label, "value": value, "unit": col.unit, "flag": flag})
	if not doc.get("values"):
		frappe.throw(_("Enter at least one reading."))
	doc.score = score if scored else None
	if scored and template.score_label:
		low, high = flt(template.score_alert_below), flt(template.score_alert_above)
		if (low and score < low) or (high and score > high):
			alerts.append(f"{template.score_label} {score:g}")
	unknown = set(given) - {c.label for c in template.columns}
	if unknown:
		frappe.throw(_("{0} has no column {1}.").format(template.template_name, ", ".join(sorted(unknown))))
	if cint(template.needs_second_signature):
		if not doc.second_check_by:
			frappe.throw(
				_("{0}: fill in Counter Checked By (a second nurse checks each entry).").format(
					template.template_name
				)
			)
		if doc.second_check_by == doc.recorded_by:
			frappe.throw(_("Counter Checked By must be another nurse, not you."))
	doc.alerts = "; ".join(alerts)


def points(value):
	"""A Score choice's points: the number it starts with ("4 Opens eyes spontaneously" = 4)."""
	head = (value or "").strip().split(" ", 1)[0]
	try:
		return float(head)
	except ValueError:
		return 0.0


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


def panel(ip, only=None, skip=None):
	"""The Nursing Care tab: each chart with its columns, latest entries and
	24-hour totals, plus Marley's fluid balance. `only`/`skip`: chart names."""
	filters = {"disabled": 0}
	if only:
		filters["name"] = ["in", only]
	elif skip:
		filters["name"] = ["not in", skip]
	templates = frappe.get_all(
		TEMPLATE,
		filters=filters,
		fields=["name", "description", "interval_hours", "needs_second_signature", "score_label"],
		order_by="sequence asc, name asc",
	)
	since = add_to_date(now_datetime(), hours=-24)
	out = []
	for t in templates:
		doc = frappe.get_cached_doc(TEMPLATE, t.name)
		entries = frappe.get_all(
			ENTRY,
			filters={"inpatient_record": ip.name, "template": t.name},
			fields=[
				"name",
				"recorded_at",
				"recorded_by",
				"second_check_by",
				"shift",
				"note",
				"alerts",
				"score",
			],
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
				"score_label": t.score_label,
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


# Bethesda's chart designs (feedback of 20 Nov 2026): the fields their paper
# charts have that ours did not. Added to the existing charts once (seed), as
# columns at the end; a hospital that changed a chart keeps its changes.
TRANSFUSION_V053 = [
	{"label": "Diagnosis", "kind": "Text"},
	{"label": "Blood group", "kind": "Choice", "options": "A\nB\nAB\nO"},
	{"label": "Rhesus", "kind": "Choice", "options": "Positive\nNegative"},
	{"label": "Expiry date", "kind": "Text"},
	{"label": "Started by", "kind": "Text"},
	{"label": "Rate", "kind": "Number", "unit": "ml/min"},
	{"label": "BP diastolic", "kind": "Number", "unit": "mmHg", "low": 50, "high": 110},
	{"label": "Respiratory rate", "kind": "Number", "unit": "/min", "low": 10, "high": 30},
	{"label": "Reaction details", "kind": "Text"},
	{"label": "Intervention drugs", "kind": "Text"},
]
FETAL_KICK_V053 = [
	{"label": "Start time", "kind": "Text"},
	{"label": "End time", "kind": "Text"},
	{"label": "Kicks per hour", "kind": "Number"},
	{"label": "Maternal condition", "kind": "Choice", "options": "Stable\nUnwell\nIn labour", "reqd": 1},
	{"label": "Next review", "kind": "Text"},
]
DIABETIC_V053 = [
	{"label": "FBS", "kind": "Number", "unit": "mg/dl", "low": 70, "high": 126},
	{"label": "RBS", "kind": "Number", "unit": "mg/dl", "low": 70, "high": 200},
	{"label": "Respiratory rate", "kind": "Number", "unit": "/min", "low": 10, "high": 30},
	{"label": "Urinalysis", "kind": "Text"},
	{"label": "Drug type", "kind": "Text"},
	{"label": "Dose", "kind": "Text"},
	{"label": "Blood sugar frequency", "kind": "Text"},
]
POSITIONS = "Supine\nLeft Lateral\nRight Lateral\nProne\nSemi-Fowler's\nFowler's"
CHARTS_V053 = (
	{
		"template_name": "Fluid Balance Chart",
		"sequence": 15,
		"description": "Intake (parenteral and alimentary) and output, with 24-hour totals.",
		"columns": [
			{
				"label": "Parenteral type",
				"kind": "Choice",
				"options": "Normal Saline\nRinger's Lactate\nDextrose 5%\nDextrose 10%\nBlood\nOther",
			},
			{"label": "Bottle", "kind": "Number", "unit": "ml"},
			{"label": "Infused", "kind": "Number", "unit": "ml", "total": 1},
			{"label": "Alimentary type", "kind": "Text"},
			{"label": "Alimentary amount", "kind": "Number", "unit": "ml", "total": 1},
			{"label": "Vomit", "kind": "Number", "unit": "ml", "total": 1},
			{"label": "Stool", "kind": "Yes or No"},
			{"label": "Nasogastric aspirate", "kind": "Number", "unit": "ml", "total": 1},
			{"label": "Other output", "kind": "Number", "unit": "ml", "total": 1},
			{"label": "Urine", "kind": "Number", "unit": "ml", "total": 1},
			{"label": "Urine specific gravity", "kind": "Number", "low": 1.005, "high": 1.03},
			{"label": "Intravenous infusion", "kind": "Text"},
			{"label": "Others", "kind": "Text"},
		],
	},
	{
		"template_name": "Turning Chart",
		"sequence": 31,
		"interval_hours": 2,
		"description": "Repositioning to prevent pressure injuries. Common positions: Supine, Left Lateral, "
		"Right Lateral, Prone, Semi-Fowler's, Fowler's.",
		"columns": [
			{"label": "Position before", "kind": "Choice", "options": POSITIONS, "reqd": 1},
			{"label": "Position turned to", "kind": "Choice", "options": POSITIONS, "reqd": 1},
		],
	},
)
EXTRA_COLUMNS_V053 = {
	"Blood Transfusion": TRANSFUSION_V053,
	"Fetal Kick Chart": FETAL_KICK_V053,
	"Diabetic Chart": DIABETIC_V053,
}
CHARTS_VERSION_KEY = "ke_chart_library_version"


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
			*TRANSFUSION_V053,
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


EYE = "4 Opens eyes spontaneously\n3 To voice\n2 To pain\n1 No response"
MOTOR = "6 Obeys commands\n5 Localises pain\n4 Withdraws from pain\n3 Abnormal flexion\n2 Extension\n1 No response"
REVIEW = " Columns, ranges and scores follow common practice: review them against your own protocol."

# Bethesda's nursing charts (PDF (9), 19 Nov 2026). Observation chart = vital
# signs, fluid balance = Marley's intake/output, partograph = the Labour Care
# Guide: those are recorded where they already live.
LIBRARY = (
	{
		"template_name": "TB Screening",
		"sequence": 1,
		"description": "Intensified TB case finding, on admission and as needed. Any Yes is flagged."
		+ REVIEW,
		"columns": [
			{"label": "Cough", "kind": "Yes or No", "reqd": 1, "alert_if_yes": 1},
			{"label": "Fever", "kind": "Yes or No", "reqd": 1, "alert_if_yes": 1},
			{"label": "Weight loss", "kind": "Yes or No", "reqd": 1, "alert_if_yes": 1},
			{"label": "Night sweats", "kind": "Yes or No", "reqd": 1, "alert_if_yes": 1},
			{
				"label": "Reduced playfulness, lethargy or irritability (child)",
				"kind": "Yes or No",
				"alert_if_yes": 1,
			},
			{"label": "Contact of a TB case", "kind": "Yes or No", "alert_if_yes": 1},
			{
				"label": "TB status",
				"kind": "Choice",
				"options": "No signs of TB\nPresumed TB\nOn TB treatment\nTB screening not done",
				"reqd": 1,
			},
			{"label": "Presumed TB result", "kind": "Text"},
		],
	},
	{
		"template_name": "Glasgow Coma Scale",
		"sequence": 40,
		"score_label": "GCS",
		"score_alert_below": 9,
		"interval_hours": 1,
		"description": "Adults and older children. A total of 8 or less is flagged." + REVIEW,
		"columns": [
			{"label": "Eye opening", "kind": "Score", "options": EYE, "reqd": 1},
			{
				"label": "Verbal response",
				"kind": "Score",
				"options": "5 Oriented\n4 Confused\n3 Inappropriate words\n2 Incomprehensible sounds\n1 No response",
				"reqd": 1,
			},
			{"label": "Motor response", "kind": "Score", "options": MOTOR, "reqd": 1},
			{"label": "Pupils", "kind": "Text"},
		],
	},
	{
		"template_name": "Paediatric Glasgow Coma Scale",
		"sequence": 41,
		"score_label": "GCS",
		"score_alert_below": 9,
		"interval_hours": 1,
		"description": "Infants and young children. A total of 8 or less is flagged." + REVIEW,
		"columns": [
			{"label": "Eye opening", "kind": "Score", "options": EYE, "reqd": 1},
			{
				"label": "Verbal response",
				"kind": "Score",
				"options": "5 Coos, babbles\n4 Irritable cry\n3 Cries to pain\n2 Moans to pain\n1 No response",
				"reqd": 1,
			},
			{
				"label": "Motor response",
				"kind": "Score",
				"options": "6 Moves spontaneously\n5 Withdraws to touch\n4 Withdraws to pain\n3 Abnormal flexion\n2 Extension\n1 No response",
				"reqd": 1,
			},
		],
	},
	{
		"template_name": "Thompson HIE Score",
		"sequence": 50,
		"score_label": "Thompson score",
		"score_alert_above": 10,
		"interval_hours": 24,
		"description": "Newborns with suspected hypoxic-ischaemic encephalopathy, daily. A total above 10 is flagged."
		+ REVIEW,
		"columns": [
			{
				"label": "Tone",
				"kind": "Score",
				"options": "0 Normal\n1 Hypertonia\n2 Hypotonia\n3 Flaccid",
				"reqd": 1,
			},
			{
				"label": "Level of consciousness",
				"kind": "Score",
				"options": "0 Normal\n1 Hyperalert, stare\n2 Lethargic\n3 Comatose",
				"reqd": 1,
			},
			{
				"label": "Fits",
				"kind": "Score",
				"options": "0 None\n1 Fewer than 3 a day\n2 More than 2 a day",
				"reqd": 1,
			},
			{
				"label": "Posture",
				"kind": "Score",
				"options": "0 Normal\n1 Fisting, cycling\n2 Strong distal flexion\n3 Decerebrate",
				"reqd": 1,
			},
			{"label": "Moro reflex", "kind": "Score", "options": "0 Normal\n1 Partial\n2 Absent", "reqd": 1},
			{"label": "Grasp", "kind": "Score", "options": "0 Normal\n1 Poor\n2 Absent", "reqd": 1},
			{"label": "Suck", "kind": "Score", "options": "0 Normal\n1 Poor\n2 Absent, bites", "reqd": 1},
			{
				"label": "Respiration",
				"kind": "Score",
				"options": "0 Normal\n1 Hyperventilation\n2 Brief apnoea\n3 Ventilated",
				"reqd": 1,
			},
			{
				"label": "Fontanelle",
				"kind": "Score",
				"options": "0 Normal\n1 Full, not tense\n2 Tense",
				"reqd": 1,
			},
		],
	},
	{
		"template_name": "NBU Observation Chart",
		"sequence": 51,
		"interval_hours": 3,
		"description": "Newborn unit observations." + REVIEW,
		"columns": [
			{"label": "Temperature", "kind": "Number", "unit": "°C", "low": 36.5, "high": 37.5, "reqd": 1},
			{"label": "Heart rate", "kind": "Number", "unit": "/min", "low": 100, "high": 160},
			{"label": "Respiratory rate", "kind": "Number", "unit": "/min", "low": 30, "high": 60},
			{"label": "SpO2", "kind": "Number", "unit": "%", "low": 90},
			{"label": "Colour", "kind": "Choice", "options": "Pink\nPale\nCyanosed\nJaundiced"},
			{
				"label": "Feeding",
				"kind": "Choice",
				"options": "Breastfeeding\nCup feeding\nNasogastric tube\nNot feeding\nIV fluids only",
			},
			{"label": "Weight", "kind": "Number", "unit": "g"},
		],
	},
	{
		"template_name": "Post Operation Chart",
		"sequence": 60,
		"interval_hours": 1,
		"description": "Observations after surgery until stable." + REVIEW,
		"columns": [
			{
				"label": "Conscious level",
				"kind": "Choice",
				"options": "Alert\nResponds to voice\nResponds to pain\nUnresponsive",
				"reqd": 1,
			},
			{"label": "Pulse", "kind": "Number", "unit": "/min", "low": 50, "high": 120},
			{"label": "BP systolic", "kind": "Number", "unit": "mmHg", "low": 90, "high": 180},
			{"label": "Respiratory rate", "kind": "Number", "unit": "/min", "low": 10, "high": 30},
			{"label": "SpO2", "kind": "Number", "unit": "%", "low": 92},
			{"label": "Pain score (0-10)", "kind": "Number", "high": 6},
			{"label": "Wound", "kind": "Choice", "options": "Dry\nOozing\nSoaked\nBleeding"},
			{"label": "Drain output", "kind": "Number", "unit": "ml", "total": 1},
		],
	},
	{
		"template_name": "Dressing Chart",
		"sequence": 61,
		"description": "Wound dressings.",
		"columns": [
			{"label": "Wound site", "kind": "Text", "reqd": 1},
			{
				"label": "Wound condition",
				"kind": "Choice",
				"options": "Clean, healing\nInflamed\nDischarging\nSloughy\nNecrotic",
				"reqd": 1,
			},
			{"label": "Dressing used", "kind": "Text"},
			{"label": "Next change due", "kind": "Text"},
		],
	},
	{
		"template_name": "Diabetic Chart",
		"sequence": 70,
		"description": "Blood glucose and insulin." + REVIEW,
		"columns": [
			{
				"label": "Time of test",
				"kind": "Choice",
				"options": "Fasting\nBefore lunch\nBefore supper\nBedtime\nRandom",
				"reqd": 1,
			},
			{"label": "Blood glucose", "kind": "Number", "unit": "mmol/L", "low": 4, "high": 14, "reqd": 1},
			{"label": "Urine ketones", "kind": "Choice", "options": "Negative\nTrace\n+\n++\n+++"},
			{"label": "Insulin", "kind": "Text"},
			{"label": "Insulin units", "kind": "Number", "unit": "IU", "total": 1},
			*DIABETIC_V053,
		],
	},
	{
		"template_name": "Oxygen Administration",
		"sequence": 71,
		"interval_hours": 4,
		"description": "Oxygen given and the response." + REVIEW,
		"columns": [
			{
				"label": "Device",
				"kind": "Choice",
				"options": "Nasal prongs\nFace mask\nNon-rebreather mask\nCPAP\nVentilator",
				"reqd": 1,
			},
			{"label": "Flow", "kind": "Number", "unit": "L/min", "reqd": 1},
			{"label": "SpO2", "kind": "Number", "unit": "%", "low": 92},
			{"label": "Respiratory rate", "kind": "Number", "unit": "/min", "low": 10, "high": 30},
		],
	},
	{
		"template_name": "Fetal Kick Chart",
		"sequence": 80,
		"description": "Fetal movements counted by the mother. Fewer than 10 is flagged." + REVIEW,
		"columns": [
			{"label": "Kicks counted", "kind": "Number", "low": 10, "reqd": 1},
			{"label": "Hours counted", "kind": "Number", "unit": "h"},
			*FETAL_KICK_V053,
		],
	},
)


def seed():
	"""The default charts, made once; afterwards the hospital's (ADR-023). The
	columns added in v0.53 are appended once to charts made before."""
	for row in (*SEED, *LIBRARY, *CHARTS_V053):
		if not frappe.db.exists(TEMPLATE, row["template_name"]):
			frappe.get_doc({"doctype": TEMPLATE, **row}).insert(ignore_permissions=True)
	if cint(frappe.db.get_default(CHARTS_VERSION_KEY)) >= 53:
		return
	for name, columns in EXTRA_COLUMNS_V053.items():
		if not frappe.db.exists(TEMPLATE, name):
			continue
		doc = frappe.get_doc(TEMPLATE, name)
		have = {c.label for c in doc.columns}
		for col in columns:
			if col["label"] not in have:
				doc.append("columns", col)
		doc.flags.ignore_permissions = True
		doc.save()
	frappe.db.set_default(CHARTS_VERSION_KEY, 53)
