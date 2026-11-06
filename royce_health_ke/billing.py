# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Kenyan billing rules on top of Marley's invoicing."""

import frappe
from frappe.utils import get_datetime, getdate, now_datetime

PER_NIGHT = "Per night"


def bed_charge_basis():
	return frappe.db.get_single_value("Kenya Health Settings", "bed_charge_basis") or PER_NIGHT


def nights(check_in, check_out=None):
	"""Midnights between check-in and check-out (or now), at least one: a
	patient admitted at 13:00 and discharged next morning pays one night."""
	return max(1, (getdate(check_out or now_datetime()) - getdate(get_datetime(check_in))).days)


def apply_bed_charge_basis(doc, method=None):
	"""Sales Invoice before_validate: with 'Per night', set each ward line (an
	Inpatient Occupancy) to the nights stayed. Marley bills hours / 24 as a
	fraction, which whole-number UOMs like Nos refuse and patients don't
	expect. Before validate, so ERPNext's whole-number check and the totals
	(and Marley's insured share) see the corrected quantity."""
	if doc.docstatus != 0 or bed_charge_basis() != PER_NIGHT:
		return
	for row in doc.items:
		if row.get("reference_dt") != "Inpatient Occupancy" or not row.get("reference_dn"):
			continue
		check_in, check_out = frappe.db.get_value(
			"Inpatient Occupancy", row.reference_dn, ["check_in", "check_out"]
		) or (None, None)
		if not check_in:
			continue
		qty = nights(check_in, check_out)
		row.qty = qty
