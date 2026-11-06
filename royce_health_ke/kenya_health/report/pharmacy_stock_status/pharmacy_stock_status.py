# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Medicines in the pharmacy: stock, reorder level, daily use, days of cover,
nearest expiry and status. The pharmacy item group, warehouse and thresholds
are in Kenya Health Settings."""

from collections import Counter

import frappe
from frappe import _

from royce_health_ke.dashboards import STOCK_STATUSES, pharmacy_stock


def execute(filters=None):
	filters = frappe._dict(filters or {})
	company = filters.company or frappe.defaults.get_user_default("Company")
	rows = pharmacy_stock(company)
	counts = Counter(r.status for r in rows)
	if filters.status:
		rows = [r for r in rows if r.status == filters.status]
	return columns(), rows, None, chart(counts), summary(rows)


def columns():
	return [
		{"fieldname": "item_code", "label": _("Item"), "fieldtype": "Link", "options": "Item", "width": 140},
		{"fieldname": "item_name", "label": _("Medicine"), "fieldtype": "Data", "width": 220},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 150},
		{"fieldname": "qty", "label": _("In Stock"), "fieldtype": "Float", "width": 90},
		{"fieldname": "uom", "label": _("UOM"), "fieldtype": "Link", "options": "UOM", "width": 80},
		{"fieldname": "reorder_level", "label": _("Reorder Level"), "fieldtype": "Float", "width": 110},
		{"fieldname": "daily_use", "label": _("Daily Use (30 Days)"), "fieldtype": "Float", "width": 130},
		{"fieldname": "days_of_cover", "label": _("Days of Cover"), "fieldtype": "Float", "width": 110},
		{"fieldname": "nearest_expiry", "label": _("Nearest Expiry"), "fieldtype": "Date", "width": 120},
		{"fieldname": "stock_value", "label": _("Stock Value"), "fieldtype": "Currency", "width": 120},
	]


def chart(counts):
	return {
		"data": {
			"labels": [_(s) for s in STOCK_STATUSES],
			"datasets": [{"name": _("Medicines"), "values": [counts[s] for s in STOCK_STATUSES]}],
		},
		"type": "bar",
		"colors": ["#E24C4C"],
		"height": 220,
	}


def summary(rows):
	return [
		{"label": _("Medicines"), "value": len(rows), "datatype": "Int"},
		{
			"label": _("Need Ordering"),
			"value": sum(1 for r in rows if r.status in ("Out of Stock", "Below Reorder Level", "Low Cover")),
			"datatype": "Int",
			"indicator": "Red",
		},
		{"label": _("Stock Value"), "value": sum(r.stock_value for r in rows), "datatype": "Currency"},
	]
