# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Clinical alerts shown and how each clinician responded (acted on,
overridden, still pending), by clinician or by alert."""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = filters or {}
	by_alert = filters.get("group_by") == "Alert"
	conditions = {
		"shown_on": ["between", [f"{filters['from_date']} 00:00:00", f"{filters['to_date']} 23:59:59"]]
	}
	if filters.get("company"):
		conditions["company"] = filters["company"]
	logs = frappe.get_all(
		"Clinical Alert Log", filters=conditions, fields=["shown_to", "kind", "rule", "severity", "response"]
	)
	counts = defaultdict(lambda: defaultdict(int))
	for log in logs:
		key = (log.rule or log.kind) if by_alert else log.shown_to
		counts[key]["shown"] += 1
		counts[key][log.response] += 1
		if log.severity == "Critical":
			counts[key]["critical"] += 1
	names = {}
	if not by_alert and counts:
		names = dict(
			frappe.get_all(
				"User", filters={"name": ["in", list(counts)]}, fields=["name", "full_name"], as_list=True
			)
		)
	data = []
	for key, c in sorted(counts.items(), key=lambda kv: -kv[1]["shown"]):
		responded = c["Acted On"] + c["Overridden"]
		data.append(
			{
				"key": key,
				"name": names.get(key, key),
				"shown": c["shown"],
				"critical": c["critical"],
				"acted_on": c["Acted On"],
				"overridden": c["Overridden"],
				"pending": c["Pending"],
				"response_rate": flt(100 * responded / c["shown"], 1) if c["shown"] else 0,
			}
		)
	first = (
		{"fieldname": "key", "label": _("Alert"), "fieldtype": "Data", "width": 300}
		if by_alert
		else {
			"fieldname": "key",
			"label": _("Clinician"),
			"fieldtype": "Link",
			"options": "User",
			"width": 220,
		}
	)
	columns = [first]
	if not by_alert:
		columns.append({"fieldname": "name", "label": _("Name"), "fieldtype": "Data", "width": 180})
	columns += [
		{"fieldname": "shown", "label": _("Alerts Shown"), "fieldtype": "Int", "width": 110},
		{"fieldname": "critical", "label": _("Critical"), "fieldtype": "Int", "width": 90},
		{"fieldname": "acted_on", "label": _("Acted On"), "fieldtype": "Int", "width": 100},
		{"fieldname": "overridden", "label": _("Overridden"), "fieldtype": "Int", "width": 100},
		{"fieldname": "pending", "label": _("Not Answered"), "fieldtype": "Int", "width": 110},
		{"fieldname": "response_rate", "label": _("Response Rate %"), "fieldtype": "Percent", "width": 130},
	]
	return columns, data
