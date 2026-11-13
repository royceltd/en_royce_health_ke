# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Excel templates for moving a pharmacy's data into RoyceERP Health with
Frappe's Data Import (guide 15).

    bench --site <site> execute royce_health_ke.migration.pharmacy_templates.build \
        --kwargs "{'out_dir': '/path/to/folder'}"

One workbook per Data Import upload, in upload order (1-5), each with four
sheets:
- Upload: the column headers Data Import matches, nothing else (the sheet it reads)
- Example: the same columns filled in, to copy the pattern from
- Notes: what each column takes
- Lists: the values this site allows

Opening stock (6) is a CSV for the Items table's Upload button on an Opening
Stock reconciliation, plus a filled example.

Build the templates on the site the data is going to: the examples and the
allowed values (stores, price lists, tax templates, units) are read from it."""

import os

import frappe
from frappe.core.doctype.data_import.exporter import Exporter
from frappe.utils import add_days, add_months, getdate, today

# (table key, fieldname, required, note). Table key is the doctype for the
# parent's own fields, or the child table's fieldname.
UPLOADS = [
	{
		"file": "1 Suppliers",
		"doctype": "Supplier",
		"columns": [
			("Supplier", "supplier_name", True, "The supplier's name, exactly as you want it on orders."),
			("Supplier", "supplier_group", True, "One of the Supplier Groups (see Lists)."),
			("Supplier", "supplier_type", True, "Company or Individual."),
			("Supplier", "country", False, "Kenya for local suppliers."),
			("Supplier", "tax_id", False, "The supplier's KRA PIN, e.g. P051234567X."),
		],
		"examples": lambda s: [
			["Example Pharmaceuticals Ltd", s.supplier_group, "Company", "Kenya", "P000000000X"],
			["Example Medical Supplies", s.supplier_group, "Company", "Kenya", ""],
		],
	},
	{
		"file": "2 Items",
		"doctype": "Item",
		"columns": [
			(
				"Item",
				"item_code",
				True,
				"Your short code for the product, e.g. the SmartHealth code. Never reuse a code.",
			),
			(
				"Item",
				"item_name",
				True,
				"The name staff search for: generic, strength, form, e.g. Metformin 500mg Tablet.",
			),
			("Item", "item_group", True, "Drug for medicines, Consumable for sundries (see Lists)."),
			(
				"Item",
				"stock_uom",
				True,
				"The SMALLEST unit you count and sell: Tablet, Capsule, Bottle, Vial, Piece.",
			),
			("Item", "is_stock_item", True, "1 for anything kept on a shelf."),
			("Item", "has_batch_no", True, "1 for medicines and anything with a batch number on the pack."),
			(
				"Item",
				"has_expiry_date",
				True,
				"1 when the pack carries an expiry date. Every batch then needs one.",
			),
			("Item", "is_purchase_item", False, "1 (bought from suppliers)."),
			("Item", "is_sales_item", False, "1 (billed to patients)."),
			(
				"uoms",
				"uom",
				False,
				"A bigger unit you also buy or sell in, e.g. Strip or Box. One per line: see Example.",
			),
			(
				"uoms",
				"conversion_factor",
				False,
				"How many smallest units are in it, e.g. 10 tablets in a Strip.",
			),
			("taxes", "item_tax_template", False, "VAT: medicines are usually exempt (see Lists)."),
			("reorder_levels", "warehouse", False, "The store to watch for reordering."),
			(
				"reorder_levels",
				"warehouse_reorder_level",
				False,
				"Reorder when stock in that store falls to this many smallest units.",
			),
			("reorder_levels", "warehouse_reorder_qty", False, "How many to order then."),
			(
				"reorder_levels",
				"material_request_type",
				False,
				"Purchase (from a supplier) or Transfer (from the main store).",
			),
		],
		"examples": lambda s: [
			[
				"EX-MET500",
				"Metformin 500mg Tablet",
				"Drug",
				"Tablet",
				1,
				1,
				1,
				1,
				1,
				"Strip",
				10,
				s.exempt,
				s.store,
				500,
				2000,
				"Purchase",
			],
			["", "", "", "", "", "", "", "", "", "Box", 100, "", "", "", "", ""],
			[
				"EX-AMX250S",
				"Amoxicillin 250mg/5ml Suspension 100ml",
				"Drug",
				"Bottle",
				1,
				1,
				1,
				1,
				1,
				"",
				"",
				s.exempt,
				s.store,
				20,
				100,
				"Purchase",
			],
			[
				"EX-GLV-EXM",
				"Examination Gloves, Medium",
				"Consumable",
				"Piece",
				1,
				0,
				0,
				1,
				1,
				"Box",
				100,
				s.exempt,
				"",
				"",
				"",
				"",
			],
		],
	},
	{
		"file": "3 Item Prices",
		"doctype": "Item Price",
		"columns": [
			("Item Price", "item_code", True, "The item's code from file 2."),
			(
				"Item Price",
				"price_list",
				True,
				"Standard Selling is the cash price; one price list per insurer tariff (see Lists).",
			),
			(
				"Item Price",
				"price_list_rate",
				True,
				"The price in KES for ONE of the unit in the next column.",
			),
			(
				"Item Price",
				"uom",
				True,
				"The unit the price is for: the smallest unit, or Strip/Box to price those separately.",
			),
		],
		"examples": lambda s: [
			["EX-MET500", s.selling, 5, "Tablet"],
			["EX-MET500", s.selling, 45, "Strip"],
			["EX-AMX250S", s.selling, 350, "Bottle"],
			["EX-GLV-EXM", s.selling, 20, "Piece"],
		],
	},
	{
		"file": "4 Medications",
		"doctype": "Medication",
		"columns": [
			(
				"Medication",
				"generic_name",
				True,
				"Generic name only, e.g. Metformin. One line per strength and form.",
			),
			(
				"Medication",
				"medication_class",
				True,
				"Its class, used for interaction checks (see Lists for some; the full list is in the system).",
			),
			("Medication", "strength", True, "The number only, e.g. 500."),
			("Medication", "strength_uom", True, "mg, g, mcg, ml, IU, % (see Lists)."),
			(
				"Medication",
				"dosage_form",
				True,
				"Tablet, Capsule, Syrup, Injection... (see Lists; add missing forms first).",
			),
			(
				"linked_items",
				"item_code",
				True,
				"The stock item this medicine is dispensed as: its code from file 2.",
			),
			("linked_items", "item_group", True, "Drug."),
			("linked_items", "stock_uom", True, "The item's smallest unit, as in file 2."),
			("linked_items", "is_billable", True, "1."),
		],
		"examples": lambda s: [
			["Metformin", "Biguanides", 500, "mg", "Tablet", "EX-MET500", "Drug", "Tablet", 1],
			["Amoxicillin", "Penicillins", 250, "mg", "Syrup", "EX-AMX250S", "Drug", "Bottle", 1],
		],
	},
	{
		"file": "5 Batches",
		"doctype": "Batch",
		"columns": [
			(
				"Batch",
				"batch_id",
				True,
				"The batch (lot) number printed on the pack. Must be unique: if two items share a number, add the item code, e.g. AB123-MET500.",
			),
			("Batch", "item", True, "The item's code from file 2."),
			(
				"Batch",
				"expiry_date",
				True,
				"Expiry date as on the pack, YYYY-MM-DD. A pack showing only month/year expires on the last day of that month.",
			),
			("Batch", "manufacturing_date", False, "Optional, YYYY-MM-DD."),
			("Batch", "supplier", False, "Optional: the supplier's name from file 1."),
		],
		"examples": lambda s: [
			["EXM2611A", "EX-MET500", s.expiry_soon, "", "Example Pharmaceuticals Ltd"],
			["EXM2703B", "EX-MET500", s.expiry_late, "", "Example Pharmaceuticals Ltd"],
			["EXA2612", "EX-AMX250S", s.expiry_late, "", ""],
		],
	},
]

# Stock Reconciliation can't go through Data Import (ERPNext doesn't allow it),
# so opening stock is uploaded into the Items table of an Opening Stock
# reconciliation, one per store: Frappe's table upload reads a CSV with seven
# header lines (title, labels, fieldnames, descriptions, 2 notes, separator).
OPENING_STOCK = {
	"file": "6 Opening Stock",
	"doctype": "Stock Reconciliation Item",
	"columns": [
		("item_code", "Item code from file 2."),
		("warehouse", "The store where it was counted: the same store on every line."),
		("qty", "Counted quantity in the SMALLEST unit (tablets, not strips)."),
		("valuation_rate", "Cost of ONE smallest unit in KES (what you paid)."),
		("batch_no", "Batch from file 5; one line per batch. Empty for items without batches."),
		("use_serial_batch_fields", "1 on every line."),
	],
	"examples": lambda s: [
		["EX-MET500", s.store, 300, 3.2, "EXM2611A", 1],
		["EX-MET500", s.store, 1000, 3.5, "EXM2703B", 1],
		["EX-AMX250S", s.store, 24, 180, "EXA2612", 1],
		["EX-GLV-EXM", s.store, 400, 9, "", 1],
	],
}
HEADER_ROWS = 7


def build(out_dir: str, company: str | None = None):
	"""Write the five workbooks and the opening stock CSVs to `out_dir`;
	return their paths."""
	site = site_values(company)
	os.makedirs(out_dir, exist_ok=True)
	paths = [write_workbook(upload, site, out_dir) for upload in UPLOADS]
	paths.append(write_opening_csv(os.path.join(out_dir, "6 Opening Stock.csv"), []))
	paths.append(
		write_opening_csv(
			os.path.join(out_dir, "6 Opening Stock - Example.csv"), OPENING_STOCK["examples"](site)
		)
	)
	return paths


def write_opening_csv(path, rows):
	"""The table-upload CSV for an Opening Stock reconciliation's Items."""
	import csv

	meta = frappe.get_meta(OPENING_STOCK["doctype"])
	fieldnames = [f for f, _note in OPENING_STOCK["columns"]]
	lines = [
		["Bulk Edit Items"],
		[meta.get_label(f) for f in fieldnames],
		fieldnames,
		[note for _f, note in OPENING_STOCK["columns"]],
		["The CSV format is case sensitive"],
		["Do not edit headers which are preset in the template"],
		["------"],
		*rows,
	]
	assert len(lines) - len(rows) == HEADER_ROWS
	with open(path, "w", newline="", encoding="utf-8") as f:
		csv.writer(f).writerows(lines)
	return path


def read_opening_csv(path):
	"""The rows as the table upload reads them: fieldnames from line 3, data
	after the header lines, blank lines skipped."""
	import csv

	with open(path, encoding="utf-8-sig") as f:
		data = list(csv.reader(f))
	fieldnames = data[2]
	return [
		{f: v for f, v in zip(fieldnames, row, strict=False) if f} for row in data[HEADER_ROWS:] if any(row)
	]


def headers(upload):
	fields = {}
	for key, fieldname, *_ in upload["columns"]:
		fields.setdefault(key, []).append(fieldname)
	exporter = Exporter(upload["doctype"], export_fields=fields, export_data=False)
	header_row = exporter.get_csv_array()[0]
	title = {
		(f.child_table_df.fieldname if f.is_child_table_field else upload["doctype"], f.fieldname): header
		for f, header in zip(exporter.fields, header_row, strict=True)
	}
	# The exporter orders columns itself; keep the guide's order instead.
	return [title[(key, fieldname)] for key, fieldname, *_ in upload["columns"]]


def write_workbook(upload, site, out_dir):
	from openpyxl import Workbook
	from openpyxl.styles import Alignment, Font, PatternFill

	head = headers(upload)
	bold = Font(bold=True)
	required_fill = PatternFill("solid", fgColor="FFF2CC")
	wb = Workbook()

	sheet = wb.active
	sheet.title = "Upload"
	sheet.append(head)

	example = wb.create_sheet("Example")
	example.append(head)
	for row in upload["examples"](site):
		example.append(row)

	for ws in (sheet, example):
		for cell, (_k, _f, required, _n) in zip(ws[1], upload["columns"], strict=True):
			cell.font = bold
			if required:
				cell.fill = required_fill
		for i, title in enumerate(head, start=1):
			ws.column_dimensions[ws.cell(1, i).column_letter].width = max(14, len(title) + 2)
		ws.freeze_panes = "A2"

	notes = wb.create_sheet("Notes")
	notes.append(["Column", "Required", "What to put"])
	for title, (_k, _f, required, note) in zip(head, upload["columns"], strict=True):
		notes.append([title, "Yes" if required else "", note])
	notes.append([])
	notes.append(["Fill the Upload sheet only (yellow columns are required). Delete nothing from row 1."])
	notes.append(["Example rows use codes starting EX-: never upload them."])
	if any(key != upload["doctype"] for key, *_ in upload["columns"]):
		notes.append(
			[
				"Extra lines for the same record (another unit, another batch): leave the record's own "
				"columns empty on the following lines, as in the Example sheet."
			]
		)
	for col, width in zip("ABC", (34, 10, 110), strict=True):
		notes.column_dimensions[col].width = width
	for cell in notes[1]:
		cell.font = bold
	for row in notes.iter_rows(min_row=2):
		row[-1].alignment = Alignment(wrap_text=True, vertical="top")

	lists = wb.create_sheet("Lists")
	columns = list_values(upload, site)
	for i, (title, values) in enumerate(columns, start=1):
		lists.cell(1, i, title).font = bold
		for j, value in enumerate(values, start=2):
			lists.cell(j, i, value)
		lists.column_dimensions[lists.cell(1, i).column_letter].width = 32

	wb.active = 0
	path = os.path.join(out_dir, f"{upload['file']}.xlsx")
	wb.save(path)
	return path


def list_values(upload, site):
	"""Allowed values from this site for the columns the upload has."""
	fields = {fieldname for _k, fieldname, *_ in upload["columns"]}
	catalogue = [
		(
			"supplier_group",
			"Supplier Groups",
			lambda: frappe.get_all("Supplier Group", {"is_group": 0}, pluck="name"),
		),
		(
			"item_group",
			"Item Groups",
			lambda: frappe.get_all("Item Group", {"is_group": 0}, pluck="name", order_by="name"),
		),
		(
			"stock_uom",
			"Units (UOM)",
			lambda: frappe.get_all("UOM", {"enabled": 1}, pluck="name", order_by="name"),
		),
		(
			"item_tax_template",
			"Item Tax Templates",
			lambda: frappe.get_all(
				"Item Tax Template", {"company": site.company, "disabled": 0}, pluck="name"
			),
		),
		("warehouse", "Stores (warehouses)", lambda: site.stores),
		(
			"price_list",
			"Selling Price Lists",
			lambda: frappe.get_all("Price List", {"selling": 1, "enabled": 1}, pluck="name"),
		),
		("dosage_form", "Dosage Forms", lambda: frappe.get_all("Dosage Form", pluck="name", order_by="name")),
		(
			"strength_uom",
			"Strength Units",
			lambda: [u for u in ("mg", "g", "mcg", "ml", "IU", "%") if frappe.db.exists("UOM", u)],
		),
		(
			"medication_class",
			"Medication Classes (first 200)",
			lambda: frappe.get_all("Medication Class", pluck="name", order_by="name", limit=200),
		),
	]
	return [(title, get()) for field, title, get in catalogue if field in fields]


def site_values(company=None):
	company = (
		company
		or frappe.defaults.get_global_default("company")
		or frappe.get_all("Company", pluck="name", limit=1)[0]
	)
	stores = frappe.get_all(
		"Warehouse", {"company": company, "is_group": 0, "disabled": 0}, pluck="name", order_by="lft"
	)
	pharmacy = [w for w in stores if "pharm" in w.lower()]
	main = [w for w in stores if w.lower().startswith("stores")]
	expiry_base = getdate(add_months(today(), 9))
	return frappe._dict(
		company=company,
		stores=stores,
		store=(pharmacy or main or stores or [""])[0],
		supplier_group=next(
			(g for g in ("Pharmaceutical", "Distributor", "Local") if frappe.db.exists("Supplier Group", g)),
			"All Supplier Groups",
		),
		exempt=frappe.db.get_value(
			"Item Tax Template", {"company": company, "name": ["like", "%Exempt%"]}, "name"
		)
		or "",
		selling=frappe.db.get_single_value("Selling Settings", "selling_price_list") or "Standard Selling",
		opening_account=frappe.db.get_value(
			"Account", {"company": company, "account_type": "Temporary", "is_group": 0}, "name"
		)
		or "",
		go_live=today(),
		expiry_soon=str(add_days(expiry_base.replace(day=1), -1)),
		expiry_late=str(getdate(add_months(today(), 24)).replace(day=28)),
	)
