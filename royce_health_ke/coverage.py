# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""What an insured patient's scheme covers, item by item.

An insured visit is not covered as a whole: each item is covered when the
scheme lists it (Item Insurance Eligibility) and its Patient Insurance
Coverage is approved. With "Insured: uncovered items paid first" on (Kenya
Health Settings > Payment Before Service), what the scheme doesn't cover is
paid at the cashier before the lab, radiology or pharmacy serves it, and it
stays off the insurer's bill.

Marley gives lab tests, imaging and procedures their cover when they are
ordered, but never covers drugs: a Medication Request has no insurance
fields. Drugs get their cover here, from the same scheme lists, when the
prescription is submitted."""

import frappe
from frappe import _
from frappe.utils import flt, getdate

# Coverage statuses that mean the insurer pays its share
COVERED = ("Approved", "Partly Invoiced", "Invoiced")
# Statuses a coverage can still be billed in (Marley's own rule)
BILLABLE = ("Approved", "Partly Invoiced")


def pays_uncovered():
	return bool(frappe.db.get_single_value("Kenya Health Settings", "insured_pay_uncovered"))


def status_of(coverage):
	return coverage and frappe.db.get_value("Patient Insurance Coverage", coverage, "status")


def is_covered(coverage):
	return status_of(coverage) in COVERED


def eligibility(item_code, template_dt=None, template_dn=None, on_date=None, insurance_plan=None):
	"""The scheme's Item Insurance Eligibility for an item or service.

	Marley's own lookup (get_insurance_eligibility) has a slip: asked about an
	item with no service template (a drug, a maternity package), it also
	matches every eligibility that has no template, and returns whichever
	starts latest, so a drug took the cover of the inpatient nursing fee.
	Here an item matches only its own eligibility, a service its own or its
	item's. FOUND 2026-11-13."""
	from frappe.query_builder import Order
	from frappe.query_builder.functions import Coalesce

	on_date = getdate(on_date) if on_date else getdate()
	E = frappe.qb.DocType("Item Insurance Eligibility")
	match = Coalesce(E.item_code, "") == (item_code or "")
	if template_dt and template_dn:
		match = match | ((E.template_dt == template_dt) & (E.template_dn == template_dn))
	query = (
		frappe.qb.from_(E)
		.select(
			E.name,
			E.template_dt,
			E.code_value,
			E.item_code,
			E.mode_of_approval,
			E.coverage,
			E.discount,
			E.valid_from,
			E.valid_till,
			E.insurance_plan,
		)
		.where(
			(E.is_active == 1)
			& (Coalesce(E.insurance_plan, "") == (insurance_plan or ""))
			& match
			& (E.valid_from <= on_date)
			& (E.valid_till.isnull() | (E.valid_till >= on_date))
		)
		# a dated eligibility before an open-ended one, then the latest start (Marley's order)
		.orderby(E.valid_till.isnull(), order=Order.asc)
		.orderby(E.valid_from, order=Order.desc)
		.limit(1)
	)
	found = query.run(as_dict=True)
	return found[0] if found else None


class CoverageEligibility:
	"""Patient Insurance Coverage (extend_doctype_class): Marley's
	set_insurance_coverage with the corrected eligibility lookup."""

	def set_insurance_coverage(self):
		from healthcare.healthcare.doctype.patient_insurance_coverage.patient_insurance_coverage import (
			CoverageNotFoundError,
		)

		found = eligibility(
			item_code=self.item_code,
			template_dt=self.template_dt,
			template_dn=self.template_dn,
			on_date=self.posting_date,
			insurance_plan=self.insurance_plan,
		)
		if not found:
			frappe.msgprint(
				_("Insurance Eligibility not found for Item {}.").format(self.item_code),
				alert=True,
				indicator="error",
			)
			if self.mode_of_approval == "Automatic":
				raise CoverageNotFoundError
			return
		self.item_eligibility = found.name
		self.insurance_plan = found.insurance_plan
		self.mode_of_approval = found.mode_of_approval
		self.coverage = found.coverage
		self.discount = found.discount
		if found.valid_till and getdate(found.valid_till) < getdate(self.coverage_validity_end_date):
			self.coverage_validity_end_date = found.valid_till


def _quietly(fn, *args, **kwargs):
	"""Marley's coverage alerts (eligibility not found, coverage approved),
	one per drug, would bury the one summary the doctor needs."""
	log = frappe.local.message_log
	before = len(log)
	try:
		return fn(*args, **kwargs)
	finally:
		del log[before:]


def cover_drug(doc, method=None):
	"""Medication Request on_submit: insurance cover for a drug prescribed in
	an insured consultation, when the scheme lists it."""
	from healthcare.healthcare.doctype.patient_insurance_coverage.patient_insurance_coverage import (
		make_insurance_coverage,
	)

	if doc.get("ke_insurance_coverage") or not doc.get("medication_item") or not doc.get("order_group"):
		return
	policy = frappe.db.get_value("Patient Encounter", doc.order_group, "insurance_policy")
	if not policy:
		return
	try:
		made = _quietly(
			make_insurance_coverage,
			patient=doc.patient,
			policy=policy,
			company=doc.company,
			item_code=doc.medication_item,
			qty=doc.quantity or 1,
		)
	except frappe.ValidationError:
		# no contract, expired policy, no price: the drug is the patient's to pay
		frappe.log_error(title=f"Insurance cover for {doc.name}")
		return
	if made and made.get("coverage"):
		doc.db_set("ke_insurance_coverage", made["coverage"])


def drug_lines(line, coverage):
	"""A drug's bill line, with its insurance cover the way Marley bills a
	covered service: the covered quantity at the scheme's price, any
	quantity beyond the cover as a line of its own for the patient."""
	c = coverage and frappe.db.get_value(
		"Patient Insurance Coverage",
		coverage,
		[
			"status",
			"coverage",
			"discount",
			"price_list_rate",
			"qty",
			"qty_invoiced",
			"policy_number",
			"insurance_payor",
			"coverage_validity_end_date",
		],
		as_dict=True,
	)
	if not (
		c
		and c.status in BILLABLE
		and (not c.coverage_validity_end_date or getdate() <= getdate(c.coverage_validity_end_date))
	):
		return [line]
	qty = flt(line["qty"])
	covered_qty = min(qty, flt(c.qty) - flt(c.qty_invoiced))
	if covered_qty <= 0:
		return [line]
	lines = [
		{
			**line,
			"qty": covered_qty,
			"rate": c.price_list_rate or False,
			"insurance_coverage": coverage,
			"patient_insurance_policy": c.policy_number,
			"insurance_payor": c.insurance_payor,
			"coverage_percentage": c.coverage,
			"discount_percentage": c.discount,
			"coverage_rate": c.price_list_rate,
			"coverage_qty": c.qty,
		}
	]
	if qty > covered_qty:
		lines.append({**line, "qty": qty - covered_qty})
	return lines


def uncovered_orders(encounter):
	"""(item, reason) for each of the consultation's orders the scheme
	doesn't cover, or whose cover waits for the insurer's approval."""
	out = []
	for r in frappe.get_all(
		"Service Request",
		filters={"order_group": encounter, "docstatus": 1},
		fields=["template_dt", "template_dn", "insurance_coverage", "billing_status"],
	):
		if r.billing_status == "Invoiced" or not r.template_dt:
			continue
		if not frappe.get_cached_value(r.template_dt, r.template_dn, "is_billable"):
			continue
		reason = reason_for(r.insurance_coverage)
		if reason:
			out.append((r.template_dn, reason))
	for m in frappe.get_all(
		"Medication Request",
		filters={"order_group": encounter, "docstatus": 1},
		fields=["medication_item", "medication", "ke_insurance_coverage", "billing_status"],
	):
		if m.billing_status == "Invoiced" or not m.medication_item:
			continue
		reason = reason_for(m.ke_insurance_coverage)
		if reason:
			out.append((m.medication or m.medication_item, reason))
	return out


def reason_for(coverage):
	status = status_of(coverage)
	if status in COVERED:
		return None
	if status == "Draft":
		return _("still waiting for the insurer's approval")
	if status == "Rejected":
		return _("rejected by the insurer")
	return _("not covered by the patient's insurance")


def warn_uncovered(doc, method=None):
	"""Patient Encounter on_submit: tell the doctor which orders the patient
	pays for before they are done."""
	if not doc.get("insurance_policy") or not pays_uncovered():
		return
	orders = uncovered_orders(doc.name)
	if not orders:
		return
	plan = frappe.db.get_value("Patient Insurance Policy", doc.insurance_policy, "insurance_plan")
	plain = reason_for(None)
	rows = "".join(
		f"<li>{frappe.utils.escape_html(item)}"
		+ (f" <span class='text-muted'>({reason})</span>" if reason != plain else "")
		+ "</li>"
		for item, reason in orders
	)
	frappe.msgprint(
		_("{0}<ul>{1}</ul>The patient pays for these at the cashier before they are done.").format(
			_("Not covered by {0}:").format(frappe.bold(plan or doc.insurance_policy)), rows
		),
		title=_("Patient pays first"),
		indicator="orange",
	)
