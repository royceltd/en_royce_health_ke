# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""The monthly temperature recording sheet of a vaccine fridge: each day's
morning and evening readings, who took them, and the action when out of
range (royce_health_ke/moh/cold_chain.py)."""

import frappe
from frappe import _

from royce_health_ke.moh.cold_chain import sheet


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not (filters.fridge and filters.from_date and filters.to_date):
		return columns(), []
	rows = sheet(filters.fridge, filters.from_date, filters.to_date)
	warm = sum(1 for r in rows for k in ("am_flag", "pm_flag") if r.get(k) == "Too warm")
	cold = sum(1 for r in rows for k in ("am_flag", "pm_flag") if r.get(k) == "Too cold")
	missed = sum(1 for r in rows for k in ("am_temp", "pm_temp") if r.get(k) is None)
	summary = [
		{"label": _("Too warm"), "value": warm, "indicator": "red" if warm else "green"},
		{"label": _("Too cold (freezing risk)"), "value": cold, "indicator": "red" if cold else "green"},
		{"label": _("Readings not taken"), "value": missed, "indicator": "orange" if missed else "green"},
	]
	return columns(), rows, None, None, summary


def columns():
	return [
		{"fieldname": "day", "label": _("Date"), "fieldtype": "Date", "width": 105},
		{"fieldname": "am_temp", "label": _("Morning °C"), "fieldtype": "Float", "width": 100},
		{"fieldname": "am_time", "label": _("Time"), "fieldtype": "Time", "width": 80},
		{"fieldname": "am_by", "label": _("By"), "fieldtype": "Data", "width": 60},
		{"fieldname": "pm_temp", "label": _("Evening °C"), "fieldtype": "Float", "width": 100},
		{"fieldname": "pm_time", "label": _("Time"), "fieldtype": "Time", "width": 80},
		{"fieldname": "pm_by", "label": _("By"), "fieldtype": "Data", "width": 60},
		{"fieldname": "action", "label": _("Action Taken"), "fieldtype": "Data", "width": 300},
	]
