# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""One payment status per order, stored on the order and read by every list.

Orders: Service Requests (lab tests, imaging, procedures) and Medication
Requests (drugs). Each carries `ke_payment_status`:

	Not Billed  ordered, on no bill yet
	Billed      on a bill (draft or submitted) not fully paid
	Paid        on a submitted bill, fully paid
	Exempt      served before paying; `ke_payment_exemption` says why:
	            insured, inpatient, casualty, approved (a manager's approval)

`compute` is the one rule (visit_bill.exemption, visit_bill.is_paid and the
insurance cover, as before). The status is refreshed whenever one of its
inputs changes: the order placed, a bill saved, submitted, cancelled or
deleted, a payment or journal entry against a bill, the visit's payment
method, type or manager's approval, an admission or discharge, the insurer's
decision on the cover, the "insured pay uncovered" setting.

Lists (lab, radiology and pharmacy worklists, the consultation, the patient's
routing) read the stored status. Actions that serve the patient (taking the
sample, performing the exam, dispensing) check it live through `refresh`,
which also corrects the stored value, so a missed update can only delay what
a list shows, never let an unpaid patient through. `reconcile` runs hourly,
recomputes the open orders and logs any it had to correct (drift = an input
change this module doesn't hear about yet)."""

import frappe
from frappe.utils import add_days, nowdate

SR, MR = "Service Request", "Medication Request"
NOT_BILLED, BILLED, PAID, EXEMPT = "Not Billed", "Billed", "Paid", "Exempt"
UNPAID = (NOT_BILLED, BILLED)
ORDERS = (SR, MR)
RECONCILE_DAYS = 30


# The rule


def compute(dt, dn):
	"""(status, exemption reason or None) of an order, from the bills and the visit."""
	from royce_health_ke import coverage, visit_bill

	if dt == SR:
		r = frappe.db.get_value(
			SR, dn, ["patient", "inpatient_record", "insurance_policy", "insurance_coverage"], as_dict=True
		)
		if not r:
			return None, None
		insured, _uncovered = visit_bill._cover(r.insurance_policy, r.insurance_coverage)
		why = visit_bill.exemption(r.patient, visit_bill.visit_of_request(dn), r.inpatient_record, insured)
	elif dt == MR:
		m = frappe.db.get_value(MR, dn, ["patient", "order_group", "ke_insurance_coverage"], as_dict=True)
		if not m:
			return None, None
		visit = m.order_group and frappe.db.get_value("Patient Encounter", m.order_group, "ke_patient_visit")
		cover = m.ke_insurance_coverage
		insured = bool(cover) and (not coverage.pays_uncovered() or coverage.is_covered(cover))
		why = visit_bill.exemption(m.patient, visit or None, None, insured)
	else:
		raise ValueError(f"no payment status for {dt}")
	if why:
		return EXEMPT, why
	if visit_bill.is_paid(dt, dn):
		return PAID, None
	billed = frappe.db.exists(
		"Sales Invoice Item", {"reference_dt": dt, "reference_dn": dn, "docstatus": ["<", 2]}
	)
	return (BILLED if billed else NOT_BILLED), None


def refresh(dt, dn):
	"""Compute and store; returns (status, exemption)."""
	status, why = compute(dt, dn)
	if status is None:
		return None, None
	current = frappe.db.get_value(dt, dn, ["ke_payment_status", "ke_payment_exemption"]) or (None, None)
	if (current[0] or None, current[1] or None) != (status, why):
		frappe.db.set_value(
			dt, dn, {"ke_payment_status": status, "ke_payment_exemption": why}, update_modified=False
		)
	return status, why


def refresh_many(pairs):
	for dt, dn in dict.fromkeys(pairs):
		if dt in ORDERS and dn:
			refresh(dt, dn)


def stored(dt, dn):
	"""(status, exemption) as stored; worked out and stored if never set."""
	status, why = frappe.db.get_value(dt, dn, ["ke_payment_status", "ke_payment_exemption"]) or (None, None)
	if not status:
		return refresh(dt, dn)
	return status, why or None


def awaiting(dt, dn):
	"""Not paid and not exempt (the gate itself is the hospital's switch, visit_bill.enforced)."""
	return stored(dt, dn)[0] in UNPAID


# What changed, and which orders it touches


def _invoice_orders(invoice_names):
	if not invoice_names:
		return []
	rows = frappe.get_all(
		"Sales Invoice Item",
		filters={"parent": ["in", list(invoice_names)], "reference_dt": ["in", ORDERS]},
		fields=["reference_dt", "reference_dn"],
	)
	return [(r.reference_dt, r.reference_dn) for r in rows]


def _visit_orders(visit):
	encounters = frappe.get_all(
		"Patient Encounter", filters={"ke_patient_visit": visit, "docstatus": ["<", 2]}, pluck="name"
	)
	pairs = [
		(SR, n) for n in frappe.get_all(SR, filters={"ke_patient_visit": visit, "docstatus": 1}, pluck="name")
	]
	if encounters:
		for dt in ORDERS:
			pairs += [
				(dt, n)
				for n in frappe.get_all(
					dt, filters={"order_group": ["in", encounters], "docstatus": 1}, pluck="name"
				)
			]
	return pairs


def _patient_orders(patient, days=RECONCILE_DAYS):
	since = add_days(nowdate(), -days)
	return [
		(dt, n)
		for dt in ORDERS
		for n in frappe.get_all(
			dt, filters={"patient": patient, "docstatus": 1, "creation": [">=", since]}, pluck="name"
		)
	]


def order_submitted(doc, method=None):
	"""Service Request / Medication Request submitted (after its cover is set)."""
	refresh(doc.doctype, doc.name)


def invoice_changed(doc, method=None):
	"""Sales Invoice saved as draft, submitted, cancelled or deleted."""
	pairs = [
		(r.reference_dt, r.reference_dn) for r in doc.get("items") or [] if r.get("reference_dt") in ORDERS
	]
	if doc.get("return_against"):
		pairs += _invoice_orders([doc.return_against])
	refresh_many(pairs)


def payment_changed(doc, method=None):
	"""Payment Entry submitted or cancelled."""
	refresh_many(
		_invoice_orders(
			[r.reference_name for r in doc.get("references") or [] if r.reference_doctype == "Sales Invoice"]
		)
	)


def journal_changed(doc, method=None):
	"""Journal Entry against a bill (a waiver, an insurer's settlement)."""
	refresh_many(
		_invoice_orders(
			[
				a.reference_name
				for a in doc.get("accounts") or []
				if a.get("reference_type") == "Sales Invoice"
			]
		)
	)


VISIT_INPUTS = ("payment_method", "visit_type", "allow_credit", "insurance_policy", "status")


def visit_changed(doc, method=None):
	"""Patient Visit: payment method, visit type or a manager's approval changed."""
	if doc.is_new() or not any(doc.has_value_changed(f) for f in VISIT_INPUTS):
		return
	refresh_many(_visit_orders(doc.name))


def inpatient_changed(doc, method=None):
	"""Inpatient Record: admitted or discharged (Marley sets the patient's status directly)."""
	if doc.has_value_changed("status") and doc.get("patient"):
		refresh_many(_patient_orders(doc.patient))


def coverage_changed(doc, method=None):
	"""Patient Insurance Coverage: the insurer's decision."""
	pairs = [(SR, n) for n in frappe.get_all(SR, filters={"insurance_coverage": doc.name}, pluck="name")]
	pairs += [(MR, n) for n in frappe.get_all(MR, filters={"ke_insurance_coverage": doc.name}, pluck="name")]
	refresh_many(pairs)


def settings_changed(doc, method=None):
	"""Kenya Health Settings: whether insured patients pay uncovered items first."""
	if doc.has_value_changed("insured_pay_uncovered"):
		frappe.enqueue("royce_health_ke.payment_status.reconcile", queue="long", log_drift=False)


# Safety net


def reconcile(days=RECONCILE_DAYS, log_drift=True):
	"""Recompute the recent orders; store and report any that had drifted."""
	since = add_days(nowdate(), -days)
	drifted = []
	for dt in ORDERS:
		for o in frappe.get_all(
			dt,
			filters={"docstatus": 1, "creation": [">=", since]},
			fields=["name", "ke_payment_status", "ke_payment_exemption"],
		):
			status, why = compute(dt, o.name)
			if status and (o.ke_payment_status or None, o.ke_payment_exemption or None) != (status, why):
				if o.ke_payment_status:
					drifted.append(f"{dt} {o.name}: {o.ke_payment_status} -> {status}")
				frappe.db.set_value(
					dt,
					o.name,
					{"ke_payment_status": status, "ke_payment_exemption": why},
					update_modified=False,
				)
	if drifted and log_drift:
		frappe.log_error(
			title=f"Payment status corrected on {len(drifted)} order(s)",
			message="\n".join(drifted[:200]),
		)
	return drifted


def backfill():
	"""Every submitted order gets its status (the v0.38 patch)."""
	return reconcile(days=100000, log_drift=False)
