# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

from frappe import _

from royce_health_ke.surveillance import week_dates, weekly_summary


def execute(filters=None):
	filters = filters or {}
	columns = [
		{
			"fieldname": "disease",
			"label": _("Disease"),
			"fieldtype": "Link",
			"options": "Notifiable Disease",
			"width": 280,
		},
		{"fieldname": "category", "label": _("IDSR Category"), "fieldtype": "Data", "width": 170},
		{"fieldname": "ihr", "label": _("IHR"), "fieldtype": "Data", "width": 60},
		{"fieldname": "cases_u5", "label": _("Cases < 5"), "fieldtype": "Int", "width": 90},
		{"fieldname": "deaths_u5", "label": _("Deaths < 5"), "fieldtype": "Int", "width": 90},
		{"fieldname": "cases_o5", "label": _("Cases 5+"), "fieldtype": "Int", "width": 90},
		{"fieldname": "deaths_o5", "label": _("Deaths 5+"), "fieldtype": "Int", "width": 90},
		{"fieldname": "cases", "label": _("Total Cases"), "fieldtype": "Int", "width": 100},
		{"fieldname": "deaths", "label": _("Total Deaths"), "fieldtype": "Int", "width": 100},
	]
	year, week = int(filters["year"]), int(filters["week"])
	start, end = week_dates(year, week)
	data = weekly_summary(filters["company"], year, week)
	message = _("Epidemiological week {0} of {1}: Monday {2} to Sunday {3}.").format(
		week, year, start.strftime("%d %b %Y"), end.strftime("%d %b %Y")
	)
	return columns, data, message
