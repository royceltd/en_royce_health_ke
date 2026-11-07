# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Demo kitchen and laundry: diet types, Daniel (after theatre) nil by mouth
then on a soft diet, meals charged per day, and the General Ward's linen - issued from the linen store,
soiled sheets collected to the laundry, some returned clean, one condemned."""

import frappe
from frappe.utils import add_days, getdate, today

from royce_health_ke.demo import journey, masters

DIETS = (
	("Normal", 0, "Regular hospital meals."),
	("Soft", 0, "Soft, easy to chew; no fried or hard foods."),
	("Liquid", 0, "Clear and full fluids only."),
	("Diabetic", 0, "Controlled carbohydrate, no added sugar."),
	("Low Salt", 0, "No added salt; for hypertension, heart and kidney disease."),
	("Nil by Mouth", 1, "Nothing to eat or drink (before theatre, vomiting, ordered by the doctor)."),
)
MEAL_ITEM = ("MEAL-DAY", "Patient Meals (per day)", 600)
LINEN = (
	("LIN-SHEET", "Bed Sheet", 900, 120),
	("LIN-PILLOW", "Pillow Case", 300, 120),
	("LIN-BLANKET", "Blanket", 1800, 40),
	("LIN-GOWN", "Patient Gown", 700, 60),
)
MOVEMENTS = (
	("Issue to ward", {"LIN-SHEET": 20, "LIN-PILLOW": 20, "LIN-BLANKET": 8, "LIN-GOWN": 12}, None),
	("Collect soiled from ward", {"LIN-SHEET": 6, "LIN-PILLOW": 6, "LIN-GOWN": 3}, None),
	("Return clean to store", {"LIN-SHEET": 4, "LIN-PILLOW": 6, "LIN-GOWN": 3}, None),
	("Condemn", {"LIN-SHEET": 1}, "Torn beyond repair"),
)


def run(company):
	kitchen(company)
	return {"diet_orders": daniel_diet(), "linen": laundry(company)}


def kitchen(company):
	for name, nbm, description in DIETS:
		if not frappe.db.exists("Diet Type", name):
			frappe.get_doc(
				{"doctype": "Diet Type", "diet_name": name, "nil_by_mouth": nbm, "description": description}
			).insert(ignore_permissions=True)
	code, item_name, rate = MEAL_ITEM
	masters.item(company, code, item_name, "Services", rate)
	settings = frappe.get_doc("Kenya Health Settings")
	if not settings.meal_item:
		# the demo bills meals per day; a hospital chooses in Kenya Health Settings
		settings.meal_billing = "Per day"
		settings.meal_item = code
		settings.save(ignore_permissions=True)


def daniel_diet():
	"""Daniel (theatre) is nil by mouth on the day of his operation, then on a
	soft diet from the next day (or later the same day if that's today)."""
	ip = frappe.db.get_value(
		"Inpatient Record",
		{"patient_name": ["like", "Daniel%Kioko"], "status": "Admitted"},
		["name", "admitted_datetime"],
		as_dict=True,
	)
	if not ip:
		return None
	existing = frappe.get_all(
		"Diet Order", filters={"inpatient_record": ip.name, "docstatus": 1}, pluck="name"
	)
	if existing:
		return existing
	admitted = getdate(ip.admitted_datetime)
	surgeon = frappe.db.get_value("Healthcare Practitioner", {"first_name": "Brian"})
	orders = []
	for diet, start, meals, note in (
		("Nil by Mouth", admitted, 0, "Theatre today."),
		(
			"Soft",
			max(add_days(admitted, 1), getdate(today())) if admitted < getdate(today()) else admitted,
			3,
			"Post-op: start with fluids, then soft foods as tolerated.",
		),
	):
		orders.append(
			journey._insert(
				{
					"doctype": "Diet Order",
					"inpatient_record": ip.name,
					"diet_type": diet,
					"start_date": start,
					"meals_per_day": meals,
					"ordered_by": surgeon,
					"instructions": note,
				},
				submit=True,
			).name
		)
	return orders


def laundry(company):
	a = masters.abbr(company)
	if not frappe.db.exists("Item Group", "Linen"):
		frappe.get_doc(
			{"doctype": "Item Group", "item_group_name": "Linen", "parent_item_group": "All Item Groups"}
		).insert(ignore_permissions=True)
	if masters.has_kra_class(masters.CLS_EXEMPT) and not frappe.db.get_value(
		"Item Group", "Linen", "royce_etims_item_classification"
	):
		frappe.db.set_value("Item Group", "Linen", "royce_etims_item_classification", masters.CLS_EXEMPT)
	for code, name, _cost, _qty in LINEN:
		masters.item(company, code, name, "Linen", 0, stock=1)

	parent = frappe.db.get_value(
		"Warehouse", {"company": company, "is_group": 1, "parent_warehouse": ["is", "not set"]}
	)
	stores = {}
	for key, label in (("store", "Linen Store"), ("laundry", "Laundry"), ("ward", "General Ward Linen")):
		name = f"{label} - {a}"
		if not frappe.db.exists("Warehouse", name):
			frappe.get_doc(
				{
					"doctype": "Warehouse",
					"warehouse_name": label,
					"company": company,
					"parent_warehouse": parent,
				}
			).insert(ignore_permissions=True)
		stores[key] = name
	settings = frappe.get_doc("Kenya Health Settings")
	if not settings.linen_store:
		settings.linen_store, settings.laundry_warehouse = stores["store"], stores["laundry"]
		settings.linen_item_group = "Linen"
		settings.save(ignore_permissions=True)
	ward = f"General Ward - {a}"
	if frappe.db.exists("Healthcare Service Unit", ward) and not frappe.db.get_value(
		"Healthcare Service Unit", ward, "ke_linen_warehouse"
	):
		frappe.db.set_value("Healthcare Service Unit", ward, "ke_linen_warehouse", stores["ward"])

	if frappe.db.exists("Linen Movement", {"company": company, "docstatus": 1}):
		return frappe.db.count("Linen Movement", {"company": company, "docstatus": 1})

	etims = journey._etims_active(company)
	if etims:
		journey._register_items(company)
	journey._insert(
		{
			"doctype": "Stock Entry",
			"stock_entry_type": "Material Receipt",
			"company": company,
			"remarks": "Demo linen opening stock",
			"items": [
				{"item_code": code, "qty": qty, "basic_rate": cost, "t_warehouse": stores["store"]}
				for code, _n, cost, qty in LINEN
			],
		},
		submit=True,
	)
	for movement, items, remarks in MOVEMENTS:
		journey._insert(
			{
				"doctype": "Linen Movement",
				"movement_type": movement,
				"company": company,
				"posting_date": today(),
				"ward": ward if movement in ("Issue to ward", "Collect soiled from ward") else None,
				"remarks": remarks,
				"items": [{"item_code": code, "qty": qty} for code, qty in items.items()],
			},
			submit=True,
		)
	if etims:
		journey._push_stock(company)
	return len(MOVEMENTS)
