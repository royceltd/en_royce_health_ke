# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Medication (extend_doctype_class): linking a medication to an Item that
already exists keeps the Item as it is.

Marley's insert_item renames an existing Item to its code and always adds a
selling price, which fails with ItemPriceDuplicateItem once the Item has one.
A hospital moving from another system uploads its items and prices first and
its formulary after, so every medication row would be refused."""

import frappe
from frappe import _
from frappe.utils import flt


class MedicationLinking:
	def before_naming(self):
		"""The name is "<form> <generic> <strength><unit>", and Frappe's naming
		drops a float: an uploaded 500.0 made "Tablet Metformin mg", so every
		strength of a drug got the same name. Name with 500 (or "2.5")."""
		strength = flt(self.strength)
		self.strength = int(strength) if strength.is_integer() else str(strength)

	def validate(self):
		self.strength = flt(self.strength)
		super().validate()

	def after_insert(self):
		link_items(self)

	def update_item_and_item_price(self):
		link_items(self)
		super().update_item_and_item_price()


def link_items(doc):
	"""Link each row that has no Item yet: an existing Item is linked as it is
	(price added only when the row has one and the price list has none); a new
	code goes through Marley, which creates the Item and its price."""
	from healthcare.healthcare.doctype.medication.medication import insert_item

	for row in doc.linked_items:
		if row.item or not row.item_code:
			continue
		if not frappe.db.exists("Item", row.item_code):
			insert_item(doc, row)
		else:
			_link_existing(doc, row)
		row.item = row.item_code


def _link_existing(doc, row):
	stock_uom = frappe.db.get_value("Item", row.item_code, "stock_uom")
	if row.stock_uom and row.stock_uom != stock_uom:
		frappe.throw(
			_("Item {0} is counted in {1}, not {2}. Set the medication's Stock UOM to {1}.").format(
				row.item_code, stock_uom, row.stock_uom
			),
			title=_("Unit does not match"),
		)
	price_list = doc.price_list
	if (
		flt(row.rate)
		and price_list
		and not frappe.db.exists("Item Price", {"item_code": row.item_code, "price_list": price_list})
	):
		from healthcare.healthcare.doctype.medication.medication import make_item_price

		make_item_price(row.item_code, row.rate, price_list)
	frappe.db.set_value("Medication Linked Item", row.name, {"item": row.item_code, "stock_uom": stock_uom})


BATCH_QUICK_ENTRY = ("expiry_date", "manufacturing_date")


def batch_quick_entry():
	"""A new batch typed on a receipt line opens Batch's quick entry, which
	asks only for the batch number and item; a medicine with expiry dates then
	can't be saved ("Please set Shelf Life in Days"). Show the dates there too.
	Only where the hospital hasn't set the property itself (ADR-023)."""
	for fieldname in BATCH_QUICK_ENTRY:
		if frappe.db.exists(
			"Property Setter",
			{"doc_type": "Batch", "field_name": fieldname, "property": "allow_in_quick_entry"},
		):
			continue
		frappe.make_property_setter(
			{
				"doctype": "Batch",
				"doctype_or_field": "DocField",
				"fieldname": fieldname,
				"property": "allow_in_quick_entry",
				"value": "1",
				"property_type": "Check",
			},
			is_system_generated=False,
		)
