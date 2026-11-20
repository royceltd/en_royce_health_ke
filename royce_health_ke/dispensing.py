# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Prescribing in dispensing units (Bethesda proposals, 18 Nov 2026).

The doctor writes the dose in clinical units (5 ml, 500 mg, 2 tablets), the
frequency (Marley's Prescription Dosage) and the duration (Prescription
Duration). The pharmacy hands over, and the bill charges, whole dispensing
units: the drug Item's stock unit (a bottle, a tablet, a tube).

	total  = dose x times a day x days                (in the dose unit)
	units  = ceil(total / pack size)                  (dispensing units)

Amoxicillin suspension 5 ml three times a day for 10 days = 150 ml; a
100 ml bottle (pack size 100) -> 2 bottles, billed as 2 bottles.

The pack size is data on the Medication (Dose and Dispensing Unit): how much
of the dose unit one dispensing unit holds. When it is blank: the strength,
if the dose is written in the strength's unit (500 mg tablets, dose 1000 mg
-> 2 tablets a dose); else 1 (the dose is already in dispensing units).

Without a dose, Marley's own convention stands: the frequency's strengths are
units per administration (1-0-1 = one tablet morning and evening).

The quantity lands on Marley's Medication Request (quantity, an integer),
which is what the pharmacy dispenses and the visit bill charges."""

import math
import re

import frappe
from frappe import _
from frappe.utils import cint, flt

ABBREVIATIONS = {
	"OD": 1,
	"ONCE DAILY": 1,
	"NOCTE": 1,
	"STAT": 1,
	"BD": 2,
	"BID": 2,
	"TDS": 3,
	"TID": 3,
	"QDS": 4,
	"QID": 4,
}
EPSILON = 1e-9


def _dosage(name):
	if not name:
		return None
	return frappe.get_cached_doc("Prescription Dosage", name)


def times_a_day(dosage):
	"""How many administrations a day a Prescription Dosage means."""
	doc = _dosage(dosage)
	if not doc:
		return 0
	rows = [r for r in doc.get("dosage_strength") or [] if flt(r.strength) > 0]
	if rows:
		return len(rows)
	text = (doc.get("dosage") or doc.name or "").strip().upper()
	pattern = re.match(r"^\s*(\d+(?:\.\d+)?(?:\s*-\s*\d+(?:\.\d+)?)+)", text)
	if pattern:
		return sum(1 for part in pattern.group(1).split("-") if flt(part) > 0)
	for word, n in ABBREVIATIONS.items():
		if re.search(rf"\b{re.escape(word)}\b", text):
			return n
	match = re.search(r"(\d+)\s*TIMES", text)
	return cint(match.group(1)) if match else 0


def units_a_day(dosage):
	"""Marley's convention: the sum of the dosage's strengths (units a day)."""
	doc = _dosage(dosage)
	if not doc:
		return 0
	total = sum(flt(r.strength) for r in doc.get("dosage_strength") or [])
	return total or times_a_day(dosage)


def days(period):
	if not period:
		return 0
	return flt(frappe.get_cached_doc("Prescription Duration", period).get_days())


def medication_for_item(item_code):
	if not item_code:
		return None
	return frappe.db.get_value("Medication Linked Item", {"item": item_code}, "parent") or (
		frappe.db.get_value("Medication Linked Item", {"item_code": item_code}, "parent")
	)


def item_for(medication):
	if not medication:
		return None
	return frappe.db.get_value(
		"Medication Linked Item", {"parent": medication, "parenttype": "Medication"}, "item"
	) or frappe.db.get_value("Medication Linked Item", {"parent": medication}, "item_code")


def pack_size(medication, dose_uom, item_code=None):
	"""How much of `dose_uom` one dispensing unit holds, or None when unknown."""
	m = (
		frappe.db.get_value(
			"Medication",
			medication,
			["ke_pack_size", "ke_dose_uom", "strength", "strength_uom"],
			as_dict=True,
		)
		if medication
		else None
	)
	stock_uom = item_code and frappe.db.get_value("Item", item_code, "stock_uom")
	if not dose_uom or (stock_uom and dose_uom == stock_uom):
		return 1.0
	if m:
		if flt(m.ke_pack_size) and (not m.ke_dose_uom or m.ke_dose_uom == dose_uom):
			return flt(m.ke_pack_size)
		if flt(m.strength) and m.strength_uom == dose_uom:
			return flt(m.strength)
	return None


def compute(
	medication=None,
	item_code=None,
	dose=None,
	dose_uom=None,
	dosage=None,
	period=None,
	interval=None,
	interval_uom=None,
	by_interval=False,
):
	"""frappe._dict(quantity, unit, total, dose_uom, how) in dispensing units,
	or None when the frequency or duration is missing."""
	item_code = item_code or item_for(medication)
	unit = item_code and frappe.db.get_value("Item", item_code, "stock_uom")
	n_days = days(period)
	if cint(by_interval) and cint(interval):
		hours = cint(interval) * (24 if interval_uom == "Day" else 1)
		per_day = 24 / hours if hours else 0
	else:
		per_day = times_a_day(dosage) if flt(dose) else units_a_day(dosage)
	if not per_day or not n_days:
		return None
	if not flt(dose):
		total = per_day * n_days
		return frappe._dict(
			quantity=max(math.ceil(total - EPSILON), 1), unit=unit, total=total, dose_uom=unit, how="units"
		)
	dose_uom = dose_uom or (medication and frappe.db.get_value("Medication", medication, "ke_dose_uom"))
	total = flt(dose) * per_day * n_days
	size = pack_size(medication, dose_uom, item_code)
	if not size:
		return None
	return frappe._dict(
		quantity=max(math.ceil(total / size - EPSILON), 1),
		unit=unit,
		total=total,
		dose_uom=dose_uom,
		how="dose",
	)


def compute_row(row):
	"""compute() for a Drug Prescription row (or a dict like one)."""
	return compute(
		medication=row.get("medication"),
		item_code=row.get("drug_code"),
		dose=row.get("ke_dose"),
		dose_uom=row.get("ke_dose_uom"),
		dosage=row.get("dosage"),
		period=row.get("period"),
		interval=row.get("interval"),
		interval_uom=row.get("interval_uom"),
		by_interval=row.get("dosage_by_interval"),
	)


@frappe.whitelist()
def quantity_for(row: str | dict) -> dict | None:
	"""The prescription row's quantity, worked out as the doctor types."""
	frappe.has_permission("Patient Encounter", "write", throw=True)
	row = frappe.parse_json(row) if isinstance(row, str) else row
	result = compute_row(frappe._dict(row))
	if not result:
		return None
	return {
		"quantity": result.quantity,
		"unit": result.unit,
		"total": result.total,
		"dose_uom": result.dose_uom,
	}


def fill_quantities(doc, method=None):
	"""Patient Encounter validate: rows not ordered yet get their quantity and
	dispensing unit when the doctor left them blank."""
	for row in doc.get("drug_prescription") or []:
		if row.get("medication_request") or not (row.get("medication") or row.get("drug_code")):
			continue
		unit = frappe.db.get_value(
			"Item", row.get("drug_code") or item_for(row.get("medication")), "stock_uom"
		)
		if unit:
			row.ke_dispensing_unit = unit
		if flt(row.get("ke_quantity")) > 0:
			continue
		result = compute_row(row)
		if result:
			row.ke_quantity = result.quantity


def instructions_text(dose, dose_uom, dosage, period, route=None, comment=None):
	"""'5 ml TID for 5 Day, oral. After meals' as the label and pharmacist read it."""
	parts = []
	if flt(dose):
		parts.append(f"{flt(dose):g} {dose_uom or ''}".strip())
	if dosage:
		parts.append(dosage)
	if period:
		parts.append(_("for {0}").format(period))
	text = " ".join(parts)
	if route:
		text = f"{text}, {route}" if text else route
	if comment:
		text = f"{text}. {comment}" if text else comment
	return text


class DrugPrescriptionQuantity:
	"""Drug Prescription (extend_doctype_class): Marley's Medication Request
	quantity, in dispensing units."""

	def get_quantity(self):
		if flt(self.get("ke_quantity")) > 0:
			return math.ceil(flt(self.ke_quantity) - EPSILON)
		result = compute_row(self)
		if result:
			return result.quantity
		return math.ceil(flt(super().get_quantity()) - EPSILON) or 1


class EncounterOrders:
	"""Patient Encounter (extend_doctype_class): the dose, route and start go
	on the Medication Request Marley makes from each prescription row. Rows
	saved to draft on the Order Drug panel (prescribing.py) are not ordered."""

	def make_medication_request(self):
		rows = self.get("drug_prescription") or []
		if not any(d.get("ke_draft") for d in rows):
			return super().make_medication_request()
		self.drug_prescription = [d for d in rows if not d.get("ke_draft")]
		try:
			return super().make_medication_request()
		finally:
			self.drug_prescription = rows

	def get_order_details(self, template_doc, line_item, medication_request=False):
		order = super().get_order_details(template_doc, line_item, medication_request)
		if medication_request and line_item.get("doctype") == "Drug Prescription":
			start = None
			if line_item.get("ke_start_date"):
				start = f"{line_item.ke_start_date} {line_item.get('ke_start_time') or '00:00:00'}"
			order.update(
				{
					"ke_dose": line_item.get("ke_dose"),
					"ke_dose_uom": line_item.get("ke_dose_uom"),
					"ke_route": line_item.get("ke_route"),
					"ke_start": start,
				}
			)
			if not order.get("comment") and line_item.get("comment"):
				order.comment = line_item.comment
			order.ke_chronic = cint(line_item.get("ke_chronic"))
			if cint(line_item.get("ke_buy_externally")):
				# on the prescription, neither dispensed nor billed (prescribing.py)
				from royce_health_ke.pharmacy import BUY_OUTSIDE

				order.ke_pharmacy_status = BUY_OUTSIDE
				order.ke_pharmacy_note = _("Prescribed to buy outside")
			# Marley's Medication Request works its quantity out again on
			# validate (strengths x days): keep the one in dispensing units
			order.flags.ke_quantity = order.quantity
		return order


class MedicationRequestQuantity:
	"""Medication Request (extend_doctype_class): a quantity worked out on the
	consultation (in dispensing units) is not recomputed by Marley."""

	def set_medication_qty(self):
		if self.flags.ke_quantity:
			self.quantity = self.flags.ke_quantity
			return
		super().set_medication_qty()
