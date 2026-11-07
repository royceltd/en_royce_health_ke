# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Where the linen is: per item, the linen store, the laundry and each ward,
plus what was condemned or reported lost this month."""

import frappe
from frappe import _
from frappe.utils import flt

from royce_health_ke.laundry import CONDEMN, LOST, linen_status


def execute(filters=None):
	filters = frappe._dict(filters or {})
	locations, items, qty, written_off = linen_status(filters.company, filters.get("date"))
	columns = [
		{"fieldname": "item_code", "label": _("Item"), "fieldtype": "Link", "options": "Item", "width": 130},
		{"fieldname": "item_name", "label": _("Linen"), "fieldtype": "Data", "width": 180},
	]
	for i, (label, _store) in enumerate(locations):
		columns.append({"fieldname": f"loc_{i}", "label": label, "fieldtype": "Float", "width": 120})
	columns += [
		{"fieldname": "total", "label": _("Total in Use"), "fieldtype": "Float", "width": 110},
		{"fieldname": "condemned", "label": _("Condemned this Month"), "fieldtype": "Float", "width": 150},
		{"fieldname": "lost", "label": _("Lost this Month"), "fieldtype": "Float", "width": 120},
	]
	rows = []
	for item in items:
		row = {"item_code": item.name, "item_name": item.item_name, "total": 0}
		for i, (_label, store) in enumerate(locations):
			row[f"loc_{i}"] = flt(qty.get((item.name, store)))
			row["total"] += row[f"loc_{i}"]
		row["condemned"] = flt(written_off.get((CONDEMN, item.name)))
		row["lost"] = flt(written_off.get((LOST, item.name)))
		rows.append(row)
	return columns, rows
