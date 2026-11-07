# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Maternity packages: one price for a delivery (SHA's case rates for normal
delivery and caesarean section, an insurer's, or the hospital's own cash
package) instead of itemised charges.

- Each Delivery Record gets a Maternity Package when it's saved: the one for
  its delivery type and the admission's insurer, else the cash one for that
  type. Staff can change it, also after submitting.
- The discharge bill (the patient's first invoice dated on or after the
  delivery, not a return) gets the package line, referenced to the Delivery
  Record so Marley marks it invoiced and it can't be billed twice. Lines for
  what the package covers stay on the bill at zero ("Included in ...") so
  the services are still marked invoiced and the patient sees what the
  price included. Ward nights after the included ones are billed as usual.
- With an insurer, the package line carries a Patient Insurance Coverage
  (from the insurer's eligibility for the package item), so Marley moves the
  insurer's share to its receivable and it goes on the claim like any other
  covered line. Covered lines that had their own coverage lose it: the
  insurer pays the package, not the parts."""

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, getdate

VAGINAL = "Vaginal delivery"
CAESAREAN = "Caesarean section"
INCLUDED = "Included in {0}"


def delivery_type(mode_of_delivery):
	return CAESAREAN if mode_of_delivery == "Caesarean section" else VAGINAL


def validate_package(doc):
	if not doc.covered and not doc.included_nights:
		frappe.msgprint(
			_("The package includes no charges or nights, so everything will be billed on top of it."),
			alert=True,
		)
	for row in doc.covered:
		if bool(row.item_group) == bool(row.item_code):
			frappe.throw(_("Row {0}: choose either an item group or an item.").format(row.idx))
	if frappe.db.get_value("Item", doc.item, "is_stock_item"):
		frappe.throw(_("The billing item {0} must be a service (non-stock) item.").format(doc.item))


def admission_policy(delivery):
	"""(insurance payor, policy) of the delivery's admission, if insured."""
	if delivery.get("inpatient_record"):
		payor, policy = frappe.db.get_value(
			"Inpatient Record", delivery.inpatient_record, ["insurance_payor", "insurance_policy"]
		) or (None, None)
		if policy:
			return payor or frappe.db.get_value("Patient Insurance Policy", policy, "insurance_payor"), policy
	return None, None


def choose_package(delivery):
	"""The insurer's package for this delivery type, else the cash one."""
	if delivery.maternity_package or not delivery.mode_of_delivery:
		return
	payor, _policy = admission_policy(delivery)
	kind = delivery_type(delivery.mode_of_delivery)
	for insurer in ([payor] if payor else []) + [None]:
		name = frappe.db.get_value(
			"Maternity Package",
			{"delivery_type": kind, "insurance_payor": insurer or ["is", "not set"], "disabled": 0},
		)
		if name:
			delivery.maternity_package = name
			return


def pending_delivery(invoice):
	"""The patient's submitted, not yet invoiced delivery with a package that
	this invoice is the discharge bill for."""
	if not invoice.get("patient") or invoice.get("is_return"):
		return None
	for d in frappe.get_all(
		"Delivery Record",
		filters={
			"patient": invoice.patient,
			"company": invoice.company,
			"docstatus": 1,
			"invoiced": 0,
			"maternity_package": ["is", "set"],
		},
		fields=["name", "delivery_datetime", "inpatient_record", "maternity_package", "package_coverage"],
		order_by="delivery_datetime asc",
	):
		if getdate(invoice.posting_date) >= getdate(get_datetime(d.delivery_datetime)):
			return d
	return None


def apply_maternity_package(doc, method=None):
	"""Sales Invoice before_validate (after the bed-night rule)."""
	if doc.docstatus != 0:
		return
	delivery = pending_delivery(doc)
	if not delivery:
		return
	package = frappe.get_cached_doc("Maternity Package", delivery.maternity_package)
	line = next(
		(r for r in doc.items if r.reference_dt == "Delivery Record" and r.reference_dn == delivery.name),
		None,
	)
	if not line:
		line = _package_line(doc, delivery, package)
	_include_covered(doc, delivery, package, line)
	if package.insurance_payor:
		_insure(doc, delivery, package, line)


def _package_line(doc, delivery, package):
	from royce_health_ke.billing import add_invoice_line

	return add_invoice_line(
		doc,
		package.item,
		1,
		rate=package.rate,
		description=_("{0} - {1}").format(package.package_name, delivery.name),
		reference_dt="Delivery Record",
		reference_dn=delivery.name,
	)


def _covered_items(package):
	groups, items = set(), set()
	for row in package.covered:
		if row.item_code:
			items.add(row.item_code)
		elif row.item_group and frappe.db.exists("Item Group", row.item_group):
			lft, rgt = frappe.db.get_value("Item Group", row.item_group, ["lft", "rgt"])
			groups.update(
				frappe.get_all("Item Group", filters={"lft": [">=", lft], "rgt": ["<=", rgt]}, pluck="name")
			)
	return groups, items


def _include_covered(doc, delivery, package, package_line):
	groups, items = _covered_items(package)
	nights_left = package.included_nights or 0
	note = INCLUDED.format(package.package_name)
	for row in doc.items:
		if row is package_line or (row.description or "").startswith(note):
			continue
		if row.reference_dt == "Inpatient Occupancy":
			if nights_left <= 0 or not _same_stay(row.reference_dn, delivery):
				continue
			if flt(row.qty) <= nights_left:
				nights_left -= flt(row.qty)
				_zero(row, note)
			else:  # nights beyond the package stay billed on this line
				row.qty = flt(row.qty) - nights_left
				row.description = _("{0} (after {1} night(s) {2})").format(
					row.item_name, package.included_nights, note.lower()
				)
				nights_left = 0
		elif row.item_code in items or row.item_group in groups:
			_zero(row, note)


def _same_stay(occupancy, delivery):
	"""A ward stay of the delivery's admission (or any stay of the patient's
	when the delivery isn't linked to one)."""
	if not delivery.inpatient_record:
		return True
	return frappe.db.get_value("Inpatient Occupancy", occupancy, "parent") == delivery.inpatient_record


def _zero(row, note):
	row.description = f"{row.item_name} ({note})"
	row.discount_percentage = 100
	row.discount_amount = flt(row.price_list_rate) or flt(row.rate)
	row.rate = 0
	row.amount = 0
	for field in ("insurance_coverage", "patient_insurance_policy", "insurance_payor"):
		row.set(field, None)
	for field in ("coverage_percentage", "coverage_rate", "coverage_qty", "insurance_coverage_amount"):
		row.set(field, 0)


def _insure(doc, delivery, package, line):
	payor, policy = admission_policy(delivery)
	if not policy:
		policy = frappe.db.get_value(
			"Patient Insurance Policy",
			{
				"patient": doc.patient,
				"insurance_payor": package.insurance_payor,
				"docstatus": 1,
				"policy_expiry_date": [">=", doc.posting_date],
			},
		)
		payor = package.insurance_payor if policy else None
	if not policy or payor != package.insurance_payor:
		frappe.msgprint(
			_(
				"{0} is {1}'s package, but the patient has no active policy with them: billed to the patient."
			).format(package.package_name, package.insurance_payor),
			alert=True,
		)
		return

	coverage = delivery.package_coverage
	if not coverage:
		from healthcare.healthcare.doctype.patient_insurance_coverage.patient_insurance_coverage import (
			make_insurance_coverage,
		)

		made = make_insurance_coverage(
			doc.patient, policy, doc.company, item_code=package.item, qty=1, rate=package.rate
		)
		coverage = made and made.get("coverage")
		if not coverage:
			frappe.msgprint(
				_("{0} has no insurance eligibility for {1}: the package is billed to the patient.").format(
					package.insurance_payor, package.item
				),
				alert=True,
			)
			return
		frappe.db.set_value("Delivery Record", delivery.name, "package_coverage", coverage)
		delivery.package_coverage = coverage

	c = frappe.db.get_value(
		"Patient Insurance Coverage",
		coverage,
		["status", "coverage", "price_list_rate", "policy_number", "insurance_payor"],
		as_dict=True,
	)
	if c.status not in ("Approved", "Partly Invoiced"):
		frappe.msgprint(
			_(
				"Insurance coverage {0} for the package is {1}: approve it, then save the invoice again."
			).format(coverage, c.status),
			alert=True,
		)
		return
	line.update(
		{
			"insurance_coverage": coverage,
			"patient_insurance_policy": c.policy_number,
			"insurance_payor": c.insurance_payor,
			"coverage_percentage": c.coverage,
			"coverage_rate": line.rate,
			"coverage_qty": 1,
		}
	)
