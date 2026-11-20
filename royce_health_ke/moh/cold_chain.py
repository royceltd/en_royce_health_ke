# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""The vaccine fridge's temperature log (the monthly temperature recording
sheet on the fridge door, Bethesda's list of monthly reports): a reading each
morning and evening, flagged when outside the fridge's safe range (2-8 °C by
default), with the action taken."""

import frappe
from frappe import _
from frappe.utils import add_days, date_diff, flt, getdate

READING = "Fridge Temperature Reading"


def validate_reading(doc):
	low, high = frappe.db.get_value("Cold Chain Fridge", doc.fridge, ["min_temp", "max_temp"])
	low = 2.0 if low is None else flt(low)
	high = 8.0 if high is None or flt(high) == 0 else flt(high)
	t = flt(doc.temperature)
	doc.out_of_range = "Too warm" if t > high else ("Too cold" if t < low else "")
	if doc.out_of_range and not (doc.action_taken or "").strip():
		frappe.throw(
			_("{0} °C is outside {1} to {2} °C: write the action taken.").format(t, low, high),
			title=_("Out of range"),
		)
	other = frappe.db.get_value(
		READING,
		{
			"fridge": doc.fridge,
			"reading_date": doc.reading_date,
			"session": doc.session,
			"name": ["!=", doc.name],
		},
	)
	if other:
		frappe.throw(
			_("The {0} reading of {1} for {2} is already recorded ({3}).").format(
				_(doc.session).lower(), doc.fridge, frappe.format(doc.reading_date, "Date"), other
			)
		)
	if doc.is_new() or not doc.recorded_by:
		doc.recorded_by = frappe.session.user


def sheet(fridge, start, end):
	"""One row per day of the period: morning and evening readings."""
	start, end = getdate(start), getdate(end)
	readings = frappe.get_all(
		READING,
		filters={"fridge": fridge, "reading_date": ["between", [start, end]]},
		fields=[
			"reading_date",
			"session",
			"reading_time",
			"temperature",
			"out_of_range",
			"action_taken",
			"recorded_by",
		],
	)
	by_day = {}
	for r in readings:
		by_day.setdefault(getdate(r.reading_date), {})[r.session] = r
	rows = []
	for i in range(date_diff(end, start) + 1):
		day = getdate(add_days(start, i))
		got = by_day.get(day, {})
		row = {"day": day}
		actions = []
		for session, key in (("Morning", "am"), ("Evening", "pm")):
			r = got.get(session)
			if r:
				row[f"{key}_temp"] = r.temperature
				row[f"{key}_time"] = r.reading_time
				row[f"{key}_by"] = _initials(r.recorded_by)
				row[f"{key}_flag"] = r.out_of_range or ""
				if r.action_taken:
					actions.append(f"{_(session)}: {r.action_taken}")
		row["action"] = "; ".join(actions)
		rows.append(row)
	return rows


def _initials(user):
	name = frappe.utils.get_fullname(user) if user else ""
	return "".join(p[0] for p in name.split() if p).upper()
