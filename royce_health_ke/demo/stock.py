# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Demo: batch and expiry tracking (guide 06).

Metformin 500mg is counted in tablets and also sold by the strip of 10. Two
batches arrive in one delivery, the OPD pharmacy requisitions stock from the
main store and the transfer takes the batch that expires first, and a cash
patient buys two strips, again from the first-expiring batch.

Turning batches on changes nothing for the older demo medicines: only items
marked Has Batch No need a batch."""

import frappe
from frappe.utils import add_days, add_months, get_last_day, today

from royce_health_ke.demo import masters

DRUG = "DRG-MET500"
SUPPLIER = "Mlango Pharmaceuticals Ltd (Demo)"
# Lot numbers as printed on the packs; the first expires in about five months.
BATCHES = (("MF24117", 5, 30, 28), ("MF25032", 17, 100, 30))  # id, months to expiry, strips, cost per strip
REQUISITION_TABLETS = 400
SOLD_STRIPS = 2


def opd_pharmacy(company):
	return f"OPD Pharmacy - {masters.abbr(company)}"


def setup(company):
	settings = frappe.get_single("Stock Settings")
	settings.enable_serial_and_batch_no_for_item = 1
	settings.pick_serial_and_batch_based_on = "Expiry"
	settings.use_serial_batch_fields = 1
	settings.save(ignore_permissions=True)

	# KRA takes 2-letter quantity units only: NO (number) for counted units.
	for uom, kra_unit in (("Tablet", "NO"), ("Strip", "NO")):
		if not frappe.db.exists("UOM", uom):
			frappe.get_doc({"doctype": "UOM", "uom_name": uom, "must_be_whole_number": 1}).insert(
				ignore_permissions=True
			)
		if frappe.get_meta("UOM").has_field("royce_etims_quantity_unit") and frappe.db.exists(
			"eTIMS Quantity Unit", kra_unit
		):
			frappe.db.set_value("UOM", uom, "royce_etims_quantity_unit", kra_unit)

	a = masters.abbr(company)
	if not frappe.db.exists("Warehouse", opd_pharmacy(company)):
		frappe.get_doc(
			{
				"doctype": "Warehouse",
				"warehouse_name": "OPD Pharmacy",
				"company": company,
				"parent_warehouse": f"All Warehouses - {a}",
			}
		).insert(ignore_permissions=True)

	if not frappe.db.exists("Supplier", SUPPLIER):
		frappe.get_doc(
			{
				"doctype": "Supplier",
				"supplier_name": SUPPLIER,
				"supplier_group": "Pharmaceutical"
				if frappe.db.exists("Supplier Group", "Pharmaceutical")
				else "All Supplier Groups",
				"supplier_type": "Company",
				"country": "Kenya",
			}
		).insert(ignore_permissions=True)

	if not frappe.db.exists("Item", DRUG):
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": DRUG,
				"item_name": "Metformin 500mg Tablet",
				"item_group": "Drug",
				"stock_uom": "Tablet",
				"is_stock_item": 1,
				"has_batch_no": 1,
				"has_expiry_date": 1,
				"include_item_in_manufacturing": 0,
				"uoms": [{"uom": "Strip", "conversion_factor": 10}],
				"reorder_levels": [
					{
						"warehouse": opd_pharmacy(company),
						"warehouse_reorder_level": 200,
						"warehouse_reorder_qty": REQUISITION_TABLETS,
						"material_request_type": "Transfer",
					}
				],
			}
		).insert(ignore_permissions=True)
	if frappe.db.get_value("Item", DRUG, "royce_etims_quantity_unit") == "U":  # made before the fix
		frappe.db.set_value(
			"Item", DRUG, {"royce_etims_quantity_unit": "NO", "royce_etims_quantity_unit_code": "NO"}
		)
	masters.set_item_tax(company, DRUG)
	for uom, rate in (("Tablet", 5), ("Strip", 45)):
		if not frappe.db.exists(
			"Item Price", {"item_code": DRUG, "price_list": "Standard Selling", "uom": uom}
		):
			frappe.get_doc(
				{
					"doctype": "Item Price",
					"item_code": DRUG,
					"price_list": "Standard Selling",
					"uom": uom,
					"price_list_rate": rate,
				}
			).insert(ignore_permissions=True)

	if not frappe.db.exists("Medication", {"generic_name": "Metformin"}):
		frappe.get_doc(
			{
				"doctype": "Medication",
				"generic_name": "Metformin",
				"medication_class": "Biguanides"
				if frappe.db.exists("Medication Class", "Biguanides")
				else frappe.db.get_value("Medication Class", {}, "name"),
				"strength": 500,
				"strength_uom": "mg",
				"dosage_form": "Tablet",
				"linked_items": [
					{"item_code": DRUG, "item_group": "Drug", "stock_uom": "Tablet", "is_billable": 1}
				],
			}
		).insert(ignore_permissions=True)


def run(company):
	"""The delivery, the requisition and its transfer, and an OPD sale. Runs once."""
	if frappe.db.exists("Batch", BATCHES[0][0]):
		return {"created": False}
	from royce_health_ke.demo import journey

	etims = journey._etims_active(company)
	if etims:
		journey._register_items(company)
	a = masters.abbr(company)
	stores = f"Stores - {a}"

	for batch_id, months, _strips, _cost in BATCHES:
		frappe.get_doc(
			{
				"doctype": "Batch",
				"batch_id": batch_id,
				"item": DRUG,
				"expiry_date": get_last_day(add_months(today(), months)),
				"manufacturing_date": add_months(today(), months - 36),  # a 3-year shelf life
				"supplier": SUPPLIER,
			}
		).insert(ignore_permissions=True)

	receipt = journey._insert(
		{
			"doctype": "Purchase Receipt",
			"company": company,
			"supplier": SUPPLIER,
			"supplier_delivery_note": "MPL-DN-4471",
			"posting_date": add_days(today(), -3),
			"set_posting_time": 1,
			"set_warehouse": stores,
			"items": [
				{
					"item_code": DRUG,
					"qty": strips,
					"uom": "Strip",
					"rate": cost,
					"batch_no": batch_id,
					"use_serial_batch_fields": 1,
				}
				for batch_id, _months, strips, cost in BATCHES
			],
		},
		submit=True,
	)
	if etims:
		journey._push_stock(company)

	from erpnext.stock.doctype.material_request.material_request import make_stock_entry

	request = journey._insert(
		{
			"doctype": "Material Request",
			"material_request_type": "Material Transfer",
			"company": company,
			"transaction_date": add_days(today(), -2),
			"schedule_date": add_days(today(), -1),
			"set_from_warehouse": stores,
			"set_warehouse": opd_pharmacy(company),
			"items": [
				{
					"item_code": DRUG,
					"qty": REQUISITION_TABLETS,
					"uom": "Tablet",
					"from_warehouse": stores,
					"warehouse": opd_pharmacy(company),
					"schedule_date": add_days(today(), -1),
				}
			],
		},
		submit=True,
	)
	transfer = make_stock_entry(request.name)
	transfer.posting_date = add_days(today(), -1)
	transfer.set_posting_time = 1
	transfer.insert(ignore_permissions=True)
	transfer.submit()

	patient = frappe.db.get_value(
		"Patient", {"first_name": journey.PATIENT["first_name"], "last_name": journey.PATIENT["last_name"]}
	)
	sale = frappe.new_doc("Sales Invoice")
	sale.update(
		{
			"customer": frappe.db.get_value("Patient", patient, "customer"),
			"patient": patient,
			"company": company,
			"update_stock": 1,
			"set_warehouse": opd_pharmacy(company),
			"remarks": "OPD pharmacy: metformin, 2 strips",
			"is_pos": 1,
			"items": [{"item_code": DRUG, "qty": SOLD_STRIPS, "uom": "Strip"}],
		}
	)
	sale.set_missing_values()
	sale.calculate_taxes_and_totals()
	sale.append("payments", {"mode_of_payment": _mode_of_payment(company), "amount": sale.grand_total})
	sale.insert(ignore_permissions=True)
	sale.submit()
	if etims:
		journey._sign(sale)
	return {
		"created": True,
		"purchase_receipt": receipt.name,
		"material_request": request.name,
		"transfer": transfer.name,
		"sale": sale.name,
	}


def _mode_of_payment(company):
	return (
		"M-Pesa"
		if frappe.db.exists("Mode of Payment Account", {"parent": "M-Pesa", "company": company})
		else "Cash"
	)
