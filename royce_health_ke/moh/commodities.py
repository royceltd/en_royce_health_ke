# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""MOH commodity reports (F-CDRR: facility consumption data report and
request): MOH 747A family planning, MOH 730A/730B ARV and OI medicines,
MOH 643B HIV testing and ART monitoring, TB and leprosy (Bethesda's list of
monthly reports, 18 Nov 2026).

Every form is data (Commodity Report Form): its lines, each mapped to the
hospital's stock item and unit. One engine fills the columns every F-CDRR
has, from the stock ledger of the chosen stores:

- Beginning balance: stock at the start of the period.
- Received: purchase receipts and invoices, material receipts, transfers in
  from a store outside the chosen ones.
- Dispensed: delivery notes and sales invoices (outpatient and counter
  dispensing, returns netted), material issues (ward doses, procedures).
- Losses: stock entries whose Stock Entry Type is ticked "Counts as a Loss"
  (expired, damaged, lost).
- Positive / negative adjustments: stock counts (reconciliations), transfers
  out to other stores, anything else.
- Ending balance: the stock at the end of the period (counts included, so it
  is the physical count when one was posted).
- Expiring within 6 months (current batches), days out of stock, and the
  quantity requested: the months of stock to hold times the period's use,
  less the ending balance.

A movement between two of the chosen stores nets to nothing and is left out.
The seeded forms follow the forms as we know them; compare each with the
current paper form and edit its lines (they are the hospital's, ADR-023)."""

import frappe
from frappe import _
from frappe.utils import add_days, cint, date_diff, flt, getdate, nowdate

FORM = "Commodity Report Form"
COLUMNS = (
	"beginning",
	"received",
	"dispensed",
	"losses",
	"adjust_plus",
	"adjust_minus",
	"ending",
	"expiring",
	"days_out",
	"requested",
)
SALES = ("Delivery Note", "Sales Invoice", "POS Invoice")
PURCHASES = ("Purchase Receipt", "Purchase Invoice")


def warehouses(company, warehouse=None):
	"""The leaf stores the report reads: the chosen store (with its children),
	else every store of the company."""
	if warehouse:
		lft, rgt = frappe.db.get_value("Warehouse", warehouse, ["lft", "rgt"])
		return frappe.get_all(
			"Warehouse", filters={"lft": [">=", lft], "rgt": ["<=", rgt], "is_group": 0}, pluck="name"
		)
	return frappe.get_all("Warehouse", filters={"company": company, "is_group": 0}, pluck="name")


def _entries(item, stores, start, end):
	return frappe.get_all(
		"Stock Ledger Entry",
		filters={
			"item_code": item,
			"warehouse": ["in", stores],
			"is_cancelled": 0,
			"posting_date": ["between", [start, end]],
		},
		fields=["posting_date", "voucher_type", "voucher_no", "actual_qty"],
		order_by="posting_date asc, posting_time asc, creation asc",
	)


def _opening(item, stores, start):
	return flt(
		frappe.db.sql(
			"""select sum(actual_qty) from `tabStock Ledger Entry`
			where item_code=%s and warehouse in %s and is_cancelled=0 and posting_date < %s""",
			(item, tuple(stores), start),
		)[0][0]
	)


_entry_info = {}


def _stock_entry(name):
	if name not in _entry_info:
		purpose, entry_type = frappe.db.get_value("Stock Entry", name, ["purpose", "stock_entry_type"])
		loss = cint(
			entry_type and frappe.db.get_value("Stock Entry Type", entry_type, "ke_counts_as_loss")
			if frappe.get_meta("Stock Entry Type").has_field("ke_counts_as_loss")
			else 0
		)
		_entry_info[name] = (purpose, loss)
	return _entry_info[name]


def classify(voucher_type, voucher_no, net):
	"""(column, quantity) for one document's net movement of an item."""
	if voucher_type == "Stock Reconciliation":
		return ("adjust_plus", net) if net > 0 else ("adjust_minus", -net)
	if voucher_type in PURCHASES:
		return ("received", net) if net > 0 else ("adjust_minus", -net)
	if voucher_type in SALES:
		return ("dispensed", -net)  # a return (positive) lowers what was dispensed
	if voucher_type == "Stock Entry":
		purpose, loss = _stock_entry(voucher_no)
		if loss and net < 0:
			return ("losses", -net)
		if purpose in ("Material Receipt",) and net > 0:
			return ("received", net)
		if purpose in ("Material Issue", "Material Consumption for Manufacture") and net < 0:
			return ("dispensed", -net)
		if purpose == "Material Transfer":
			return ("received", net) if net > 0 else ("adjust_minus", -net)
	return ("adjust_plus", net) if net > 0 else ("adjust_minus", -net)


def item_figures(item, stores, start, end, months_of_stock=3):
	"""The F-CDRR columns of one item, in stock units."""
	start, end = getdate(start), getdate(end)
	out = dict.fromkeys(COLUMNS, 0.0)
	opening = _opening(item, stores, start)
	out["beginning"] = opening
	entries = _entries(item, stores, start, end)
	net = {}
	daily = {}
	for e in entries:
		key = (e.voucher_type, e.voucher_no)
		net[key] = net.get(key, 0) + flt(e.actual_qty)
		day = getdate(e.posting_date)
		daily[day] = daily.get(day, 0) + flt(e.actual_qty)
	for (voucher_type, voucher_no), qty in net.items():
		if abs(qty) < 1e-9:
			continue
		column, value = classify(voucher_type, voucher_no, qty)
		out[column] += value
	out["ending"] = opening + sum(net.values())
	# days out of stock: days (up to today) that ended with nothing on the shelf
	last = min(end, getdate(nowdate()))
	balance, days_out = opening, 0
	for i in range(date_diff(last, start) + 1):
		day = add_days(start, i)
		balance += daily.get(getdate(day), 0)
		if balance <= 0:
			days_out += 1
	out["days_out"] = days_out
	out["expiring"] = _expiring(item, stores, end)
	months = max(date_diff(end, start) + 1, 1) / 30.4
	monthly_use = out["dispensed"] / months if months else out["dispensed"]
	out["requested"] = max(0.0, flt(months_of_stock) * monthly_use - out["ending"])
	return out


def _expiring(item, stores, end):
	"""Stock in batches expiring within 6 months of the period end (the
	batches as they are now)."""
	if not frappe.db.get_value("Item", item, "has_batch_no"):
		return 0.0
	try:
		from erpnext.stock.doctype.batch.batch import get_batch_qty
	except ImportError:
		return 0.0
	limit = add_days(end, 183)
	total = 0.0
	for store in stores:
		for row in get_batch_qty(item_code=item, warehouse=store) or []:
			expiry = frappe.db.get_value("Batch", row.get("batch_no"), "expiry_date")
			if expiry and getdate(expiry) <= getdate(limit) and flt(row.get("qty")) > 0:
				total += flt(row.get("qty"))
	return total


def report(form, start, end, company, warehouse=None):
	"""The form's lines with their columns, in the form's units."""
	_entry_info.clear()
	doc = frappe.get_doc(FORM, form)
	stores = warehouses(company, warehouse)
	if not stores:
		frappe.throw(_("No store found for {0}.").format(warehouse or company))
	rows, section = [], None
	for line in doc.items:
		if line.section and line.section != section:
			section = line.section
			rows.append({"commodity": section, "is_section": 1, "indent": 0})
		row = {
			"commodity": line.commodity,
			"unit": line.unit,
			"item": line.item,
			"indent": 1 if section else 0,
		}
		if line.item:
			figures = item_figures(line.item, stores, start, end, doc.months_of_stock or 3)
			per = flt(line.units_per_issue) or 1
			for column in COLUMNS:
				value = figures[column]
				row[column] = value if column == "days_out" else flt(value / per, 2)
		else:
			row["not_mapped"] = 1
		rows.append(row)
	return rows


# The forms as seeded: (form, title, programme, [(section, commodity, unit)])
FP = [
	("Pills", "Combined oral contraceptive (COC)", "Cycle"),
	("Pills", "Progestin-only pill (POP)", "Cycle"),
	("Pills", "Emergency contraceptive pill", "Tablet"),
	("Injectables", "DMPA-IM (Depo-Provera) 150 mg", "Vial"),
	("Injectables", "DMPA-SC (Sayana Press) 104 mg", "Unit"),
	("Implants", "Implant, 1-rod (etonogestrel 68 mg)", "Set"),
	("Implants", "Implant, 2-rod (levonorgestrel 75 mg)", "Set"),
	("IUCD", "Copper IUCD", "Piece"),
	("IUCD", "Hormonal IUS (levonorgestrel)", "Piece"),
	("Barrier", "Male condoms", "Piece"),
	("Barrier", "Female condoms", "Piece"),
	("Other", "Cycle beads", "Piece"),
]
ARV = [
	("Adult ARVs", "TDF/3TC/DTG 300/300/50 mg (TLD)", "Pack of 30"),
	("Adult ARVs", "TDF/3TC/EFV 300/300/400 mg", "Pack of 30"),
	("Adult ARVs", "AZT/3TC 300/150 mg", "Pack of 60"),
	("Adult ARVs", "ABC/3TC 600/300 mg", "Pack of 30"),
	("Adult ARVs", "Dolutegravir (DTG) 50 mg", "Pack of 30"),
	("Adult ARVs", "Atazanavir/ritonavir (ATV/r) 300/100 mg", "Pack of 30"),
	("Adult ARVs", "Lopinavir/ritonavir (LPV/r) 200/50 mg", "Pack of 120"),
	("Adult ARVs", "Darunavir 600 mg", "Pack of 60"),
	("Adult ARVs", "Ritonavir 100 mg", "Pack of 60"),
	("Paediatric ARVs", "ABC/3TC 120/60 mg dispersible", "Pack of 30"),
	("Paediatric ARVs", "Dolutegravir (pDTG) 10 mg dispersible", "Pack of 90"),
	("Paediatric ARVs", "LPV/r 40/10 mg pellets/granules", "Pack of 120"),
	("Paediatric ARVs", "Nevirapine (NVP) 10 mg/ml suspension", "Bottle 100 ml"),
	("Paediatric ARVs", "Zidovudine (AZT) 10 mg/ml syrup", "Bottle 100 ml"),
	("OI medicines", "Cotrimoxazole 960 mg", "Pack of 100"),
	("OI medicines", "Cotrimoxazole 240 mg/5 ml suspension", "Bottle 100 ml"),
	("OI medicines", "Fluconazole 200 mg", "Pack of 100"),
	("OI medicines", "Dapsone 100 mg", "Pack of 100"),
	("TB preventive therapy", "Isoniazid 300 mg", "Pack of 100"),
	("TB preventive therapy", "Isoniazid 100 mg", "Pack of 100"),
	("TB preventive therapy", "Rifapentine/Isoniazid 300/300 mg (3HP)", "Pack of 36"),
	("TB preventive therapy", "Pyridoxine (vitamin B6) 25 mg", "Pack of 100"),
]
HIV_TESTS = [
	("HIV testing", "HIV rapid test, screening (Determine)", "Test"),
	("HIV testing", "HIV rapid test, confirmatory (First Response)", "Test"),
	("HIV testing", "HIV self-test kit (OraQuick)", "Kit"),
	("HIV testing", "HIV/syphilis duo test", "Test"),
	("Sample collection", "DBS bundle (early infant diagnosis)", "Kit"),
	("Sample collection", "Viral load sample collection kit (EDTA tubes)", "Kit"),
	("ART monitoring", "CD4 test (point of care)", "Test"),
	("ART monitoring", "CrAg lateral flow assay", "Test"),
	("ART monitoring", "TB LAM test", "Test"),
]
TB = [
	("TB, adults", "RHZE 150/75/400/275 mg (intensive phase)", "Pack of 672"),
	("TB, adults", "RH 150/75 mg (continuation phase)", "Pack of 672"),
	("TB, adults", "Ethambutol 400 mg", "Pack of 672"),
	("TB, children", "RHZ 75/50/150 mg dispersible", "Pack of 84"),
	("TB, children", "RH 75/50 mg dispersible", "Pack of 84"),
	("TB, children", "Ethambutol 100 mg dispersible", "Pack of 100"),
	("Drug-resistant TB", "Bedaquiline 100 mg", "Pack of 188"),
	("Drug-resistant TB", "Linezolid 600 mg", "Pack of 30"),
	("Drug-resistant TB", "Levofloxacin 250 mg", "Pack of 100"),
	("Leprosy", "MDT multibacillary, adult (blister pack)", "Blister"),
	("Leprosy", "MDT paucibacillary, adult (blister pack)", "Blister"),
	("Leprosy", "MDT multibacillary, child (blister pack)", "Blister"),
	("Leprosy", "MDT paucibacillary, child (blister pack)", "Blister"),
]
FORMS = (
	("MOH 747A", "F-CDRR: Family Planning Commodities", "Family Planning", FP),
	("MOH 730B", "F-CDRR: ARV and OI Medicines (satellite / standalone site)", "HIV", ARV),
	("MOH 730A", "F-CDRR: ARV and OI Medicines (central site)", "HIV", ARV),
	("MOH 643B", "F-CDRR: HIV Testing and ART Monitoring Commodities", "HIV", HIV_TESTS),
	("TB and Leprosy", "Facility TB and Leprosy Commodities Consumption Report", "TB and Leprosy", TB),
)
SEED_NOTE = (
	"Seeded by RoyceERP Health with the commodities as we know this form. Compare with the "
	"current paper form, edit the lines, and map each to your stock item."
)
LOSS_TYPE = "Expired or Damaged"


def seed():
	"""The forms, once each (afterwards the hospital's), and a loss Stock Entry
	Type."""
	for form, title, programme, lines in FORMS:
		if frappe.db.exists(FORM, form):
			continue
		frappe.get_doc(
			{
				"doctype": FORM,
				"form_name": form,
				"title": title,
				"program": programme,
				"months_of_stock": 3,
				"notes": SEED_NOTE,
				"items": [
					{"section": s, "commodity": c, "unit": u, "units_per_issue": 1} for s, c, u in lines
				],
			}
		).insert(ignore_permissions=True)
	if not frappe.db.exists("Stock Entry Type", LOSS_TYPE) and frappe.get_meta("Stock Entry Type").has_field(
		"ke_counts_as_loss"
	):
		frappe.get_doc(
			{
				"doctype": "Stock Entry Type",
				"name": LOSS_TYPE,
				"purpose": "Material Issue",
				"ke_counts_as_loss": 1,
			}
		).insert(ignore_permissions=True)
