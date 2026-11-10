# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""The running bill of a Patient Visit, and payment before service.

Running bill: everything the patient has been given or ordered since they
checked in that is not on an invoice yet (consultation, lab, imaging,
procedures, drugs, bed), priced as the cashier's invoice would price it,
plus the visit's invoices with what is paid and what is still owed. The
cashier turns the unbilled charges into a draft invoice with Create Bill.

Payment before service, for cash patients (Kenya Health Settings, one switch
each): the lab starts a test, and radiology performs an exam, only once its
request is on a paid invoice; drugs leave the store only on a paid invoice.
Insured patients, inpatients and casualty are served first and settle
later, and a manager can approve services before payment on a visit."""

from contextlib import contextmanager

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, nowdate

from royce_health_ke.visits import open_visit_for

LAB, RADIOLOGY, PHARMACY = "lab", "radiology", "pharmacy"
SETTING = {LAB: "pay_before_lab", RADIOLOGY: "pay_before_radiology", PHARMACY: "pay_before_pharmacy"}
CREDIT_ROLES = ("System Manager", "Healthcare Administrator", "Accounts Manager")
INPATIENT_STATUSES = ("Admission Scheduled", "Admitted", "Discharge Scheduled")


@contextmanager
def _as_administrator():
	"""Marley's billing queries go through permission checks meant for the
	cashier; the bill shown on a visit, and its status, are worked out for
	any staff member who can see the visit."""
	user = frappe.session.user
	if user == "Administrator":
		yield
		return
	frappe.set_user("Administrator")
	try:
		yield
	finally:
		frappe.set_user(user)


# The visit's charges


def _window(visit):
	"""From check-in to the patient's next check-in."""
	start = get_datetime(visit.arrival or visit.creation)
	following = frappe.db.get_value(
		"Patient Visit",
		{"patient": visit.patient, "creation": [">", visit.creation], "status": ["!=", "Cancelled"]},
		"arrival",
		order_by="creation asc",
	)
	return start, get_datetime(following) if following else None


def _belongs(visit, window, dt, dn):
	if dt == "Patient Appointment":
		return dn == visit.appointment
	if dt == "Patient Encounter":
		linked = frappe.db.get_value(dt, dn, "ke_patient_visit")
		if linked:
			return linked == visit.name
	created = frappe.db.get_value(dt, dn, "creation")
	if not created:
		return False
	start, end = window
	return get_datetime(created) >= start and (not end or get_datetime(created) < end)


def unbilled_lines(visit):
	"""Marley's 'Get Items from Healthcare Services' lines for this visit,
	drugs from the visit's consultations included, in the form
	Sales Invoice.set_healthcare_services takes."""
	from healthcare.healthcare.utils import get_drugs_to_invoice, get_healthcare_services_to_invoice

	customer = frappe.db.get_value("Patient", visit.patient, "customer")
	window = _window(visit)
	lines = []
	with _as_administrator():
		for s in get_healthcare_services_to_invoice(visit.patient, customer, visit.company) or []:
			if not _belongs(visit, window, s["reference_type"], s["reference_name"]):
				continue
			lines.append(
				{
					**s,
					"dt": s["reference_type"],
					"dn": s["reference_name"],
					"item": s["service"],
					"rate": s.get("rate") or False,
					"income_account": s.get("income_account") or False,
					"qty": s.get("qty") or False,
					"description": s.get("description") or False,
				}
			)
		for encounter in frappe.get_all(
			"Patient Encounter", filters={"ke_patient_visit": visit.name, "docstatus": 1}, pluck="name"
		):
			for d in get_drugs_to_invoice(encounter, customer) or []:
				if flt(d.get("quantity")) <= 0:
					continue
				lines.append(
					{
						"dt": d["reference_type"],
						"dn": d["reference_name"],
						"item": d["drug_code"],
						"qty": d.get("quantity"),
						"rate": False,
						"income_account": False,
						"description": d.get("description") or False,
					}
				)
	return lines


def _invoice(visit, lines):
	si = frappe.new_doc("Sales Invoice")
	si.update(
		{
			"customer": frappe.db.get_value("Patient", visit.patient, "customer"),
			"patient": visit.patient,
			"patient_name": visit.patient_name,
			"company": visit.company,
			"ke_patient_visit": visit.name,
			"posting_date": nowdate(),
			"due_date": nowdate(),
		}
	)
	si.set_healthcare_services(lines)
	return si


def _apply_billing_rules(si):
	"""What saving the invoice will add or change (the Sales Invoice
	before_validate rules: bed nights, meals, a pending maternity package),
	so the bill shown on the visit is the bill the cashier gets."""
	from royce_health_ke.billing import apply_bed_charge_basis
	from royce_health_ke.kitchen import apply_meal_charges
	from royce_health_ke.packages import apply_maternity_package

	for rule in (apply_bed_charge_basis, apply_meal_charges, apply_maternity_package):
		rule(si)
	si.calculate_taxes_and_totals()
	si.calculate_patient_insurance_coverage()


def invoices(visit_name):
	return frappe.get_all(
		"Sales Invoice",
		filters={"ke_patient_visit": visit_name, "docstatus": ["<", 2]},
		fields=[
			"name",
			"docstatus",
			"status",
			"posting_date",
			"is_return",
			"grand_total",
			"outstanding_amount",
			"total_insurance_coverage_amount",
		],
		order_by="creation asc",
	)


def bill_status(unbilled, raised):
	submitted = [i for i in raised if i.docstatus == 1]
	if unbilled:
		return "To Bill"
	if any(flt(i.outstanding_amount) > 0 for i in submitted):
		return "Unpaid"
	return "Paid" if submitted else ""


@frappe.whitelist()
def visit_bill(visit: str) -> dict:
	"""The visit's running bill: unbilled charges priced, its invoices, totals."""
	doc = frappe.get_doc("Patient Visit", visit)
	doc.check_permission("read")
	try:
		lines = unbilled_lines(doc)
	except frappe.ValidationError as e:
		# Marley stops at a missing price setup, e.g. a doctor with no consultation charge.
		frappe.clear_last_message()
		return {"error": _("The bill can't be worked out yet: {0}").format(frappe.utils.strip_html(str(e)))}
	charges, unbilled_total, currency = [], 0, None
	if lines:
		if not frappe.db.get_value("Patient", doc.patient, "customer"):
			return {"error": _("The patient has no customer record, so nothing can be priced or billed.")}
		with _as_administrator():
			si = _invoice(doc, lines)
			_apply_billing_rules(si)
		currency = si.currency
		unbilled_total = si.grand_total
		charges = [
			{
				"item": row.item_name or row.item_code,
				"reference_dt": row.reference_dt,
				"reference_dn": row.reference_dn,
				"qty": row.qty,
				"rate": row.rate,
				"amount": row.amount,
				"insurance": flt(row.get("insurance_coverage_amount")),
			}
			for row in si.items
		]
	raised = invoices(doc.name)
	submitted = [i for i in raised if i.docstatus == 1]
	billed = sum(flt(i.grand_total) for i in submitted)
	insurance = sum(flt(i.total_insurance_coverage_amount) for i in submitted)
	balance = sum(flt(i.outstanding_amount) for i in submitted)
	status = bill_status(lines, raised)
	if status != (doc.bill_status or ""):
		doc.db_set("bill_status", status, update_modified=False)
	return {
		"currency": currency or frappe.db.get_value("Company", doc.company, "default_currency"),
		"charges": charges,
		"unbilled_total": unbilled_total,
		"invoices": raised,
		"billed": billed,
		"insurance": insurance,
		"paid": billed - insurance - balance,
		"balance": balance,
		"to_pay": balance + unbilled_total,
		"status": status,
		"can_bill": bool(frappe.has_permission("Sales Invoice", "create")),
		"can_approve_credit": bool(set(CREDIT_ROLES) & set(frappe.get_roles())),
	}


def refresh_bill_status(visit_name):
	if not visit_name or not frappe.db.exists("Patient Visit", visit_name):
		return
	visit = frappe.get_doc("Patient Visit", visit_name)
	try:
		status = bill_status(unbilled_lines(visit), invoices(visit_name))
	except Exception:
		# A bill status must never stop the lab, the pharmacy or the cashier.
		frappe.log_error(title=f"Bill status of {visit_name}")
		return
	if status != (visit.bill_status or ""):
		frappe.db.set_value("Patient Visit", visit_name, "bill_status", status, update_modified=False)


@frappe.whitelist()
def make_bill(visit: str):
	"""A draft invoice of the visit's unbilled charges, for the cashier."""
	frappe.has_permission("Sales Invoice", "create", throw=True)
	doc = frappe.get_doc("Patient Visit", visit)
	doc.check_permission("read")
	draft = frappe.db.get_value("Sales Invoice", {"ke_patient_visit": visit, "docstatus": 0}, "name")
	if draft:
		return {"existing": draft}
	if not frappe.db.get_value("Patient", doc.patient, "customer"):
		frappe.throw(_("Link a customer to patient {0} first.").format(doc.patient_name))
	lines = unbilled_lines(doc)
	if not lines:
		frappe.throw(_("Nothing on this visit is waiting to be billed."))
	bill = _invoice(doc, lines).as_dict()
	bill["__islocal"] = 1  # the form names it and opens it unsaved
	return bill


@frappe.whitelist()
def approve_credit(visit: str, reason: str):
	"""Let the lab, radiology and pharmacy serve the visit before payment."""
	if not set(CREDIT_ROLES) & set(frappe.get_roles()):
		frappe.throw(_("Only a manager can approve services before payment."), frappe.PermissionError)
	if not (reason or "").strip():
		frappe.throw(_("Give a reason."))
	doc = frappe.get_doc("Patient Visit", visit)
	doc.update(
		{"allow_credit": 1, "credit_reason": reason.strip(), "credit_approved_by": frappe.session.user}
	)
	doc.flags.ignore_permissions = True
	doc.save()


# Hooks keeping the visit's bill status current


def link_invoice(doc, method=None):
	"""Sales Invoice before_validate: a patient's invoice belongs to the day's open visit."""
	if doc.get("patient") and not doc.get("ke_patient_visit") and not doc.get("is_return"):
		doc.ke_patient_visit = open_visit_for(doc.patient, doc.get("posting_date"))
	elif doc.get("is_return") and doc.get("return_against") and not doc.get("ke_patient_visit"):
		doc.ke_patient_visit = frappe.db.get_value("Sales Invoice", doc.return_against, "ke_patient_visit")


def invoice_changed(doc, method=None):
	refresh_bill_status(doc.get("ke_patient_visit"))


def payment_changed(doc, method=None):
	for ref in doc.get("references") or []:
		if ref.reference_doctype == "Sales Invoice":
			refresh_bill_status(frappe.db.get_value("Sales Invoice", ref.reference_name, "ke_patient_visit"))


def orders_changed(doc, method=None):
	"""Encounter submitted (orders placed), or a lab test or exam added."""
	visit = doc.get("ke_patient_visit") or open_visit_for(doc.get("patient"))
	refresh_bill_status(visit)


# Payment before service


def enforced(kind):
	if frappe.flags.in_import or frappe.flags.in_install or frappe.flags.in_migrate:
		return False
	if frappe.flags.in_test and not frappe.flags.ke_test_payment_gate:
		return False
	return bool(frappe.db.get_single_value("Kenya Health Settings", SETTING[kind]))


def is_paid(dt, dn):
	"""On a submitted invoice, and every such invoice fully paid (an insurer's
	share is moved off the patient's balance when the invoice is submitted)."""
	parents = frappe.get_all(
		"Sales Invoice Item",
		filters={"reference_dt": dt, "reference_dn": dn, "docstatus": 1},
		pluck="parent",
		distinct=True,
	)
	if not parents:
		return False
	outstanding = frappe.get_all(
		"Sales Invoice",
		filters={"name": ["in", parents], "docstatus": 1, "is_return": 0},
		pluck="outstanding_amount",
	)
	return bool(outstanding) and all(flt(o) <= 0.005 for o in outstanding)


def visit_of_request(service_request):
	encounter = frappe.db.get_value("Service Request", service_request, "order_group")
	return encounter and frappe.db.get_value("Patient Encounter", encounter, "ke_patient_visit")


def exemption(patient, visit=None, inpatient_record=None, insured=False):
	"""Why this patient is served before paying, or None."""
	if insured:
		return "insured"
	if inpatient_record or frappe.db.get_value("Patient", patient, "inpatient_status") in INPATIENT_STATUSES:
		return "inpatient"
	visit = visit or open_visit_for(patient)
	if visit:
		v = frappe.db.get_value(
			"Patient Visit", visit, ["payment_method", "visit_type", "allow_credit"], as_dict=True
		)
		if v and v.payment_method == "Insurance":
			return "insured"
		if v and v.visit_type == "Casualty":
			return "casualty"
		if v and v.allow_credit:
			return "approved"
	return None


def require_payment(kind, patient, dt, dn, what, visit=None, inpatient_record=None, insured=False):
	if not enforced(kind) or exemption(patient, visit, inpatient_record, insured) or is_paid(dt, dn):
		return
	frappe.throw(
		_(
			"{0} for {1} is not paid yet. Send the patient to the Cashier, or ask a manager to approve "
			"services before payment on the visit."
		).format(what, frappe.db.get_value("Patient", patient, "patient_name") or patient),
		title=_("Payment required"),
	)


def _request_gate(kind, request, what):
	r = frappe.db.get_value(
		"Service Request", request, ["patient", "inpatient_record", "insurance_policy"], as_dict=True
	)
	if r:
		require_payment(
			kind,
			r.patient,
			"Service Request",
			request,
			what,
			visit=visit_of_request(request),
			inpatient_record=r.inpatient_record,
			insured=bool(r.insurance_policy),
		)


def lab_test_before_insert(doc, method=None):
	"""A requested test is started only once its request is paid."""
	if doc.get("service_request"):
		_request_gate(
			LAB, doc.service_request, _("Lab test {0}").format(doc.get("lab_test_name") or doc.template)
		)


def lab_test_before_submit(doc, method=None):
	"""A test done without a request: its results are released once it is paid."""
	if not doc.get("service_request"):
		require_payment(
			LAB,
			doc.patient,
			"Lab Test",
			doc.name,
			_("Lab test {0}").format(doc.get("lab_test_name") or doc.template),
			inpatient_record=doc.get("inpatient_record"),
		)


def imaging_gate(observation):
	"""Before radiology performs an exam."""
	if observation.get("service_request"):
		_request_gate(
			RADIOLOGY,
			observation.service_request,
			_("Imaging exam {0}").format(observation.observation_template),
		)
	else:
		require_payment(
			RADIOLOGY,
			observation.patient,
			"Observation",
			observation.name,
			_("Imaging exam {0}").format(observation.observation_template),
		)


def _stock_lines(items):
	codes = {row.item_code for row in items if row.item_code}
	return codes and frappe.get_all(
		"Item", filters={"name": ["in", list(codes)], "is_stock_item": 1}, pluck="name"
	)


def invoice_before_submit(doc, method=None):
	"""An invoice that issues drugs from the store (Update Stock) is paid on the spot."""
	if (
		not doc.get("patient")
		or not doc.get("update_stock")
		or doc.get("is_return")
		or flt(doc.outstanding_amount) <= 0.005
		or not enforced(PHARMACY)
		or not _stock_lines(doc.items)
	):
		return
	insured = any(row.get("insurance_coverage") for row in doc.items)
	if exemption(doc.patient, doc.get("ke_patient_visit"), insured=insured):
		return
	frappe.throw(
		_(
			"Drugs leave the store only when paid. Take the payment on this invoice (Include Payment), or "
			"untick Update Stock and dispense with a Delivery Note once the invoice is paid."
		),
		title=_("Payment required"),
	)


def delivery_before_submit(doc, method=None):
	"""Dispensing against a patient's invoice: the invoice is paid first."""
	if not enforced(PHARMACY) or doc.get("is_return"):
		return
	for invoice in {row.against_sales_invoice for row in doc.items if row.get("against_sales_invoice")}:
		si = frappe.db.get_value(
			"Sales Invoice", invoice, ["patient", "outstanding_amount", "ke_patient_visit"], as_dict=True
		)
		if not si or not si.patient or flt(si.outstanding_amount) <= 0.005:
			continue
		if exemption(si.patient, si.ke_patient_visit):
			continue
		frappe.throw(
			_("Invoice {0} has {1} unpaid. Drugs leave the store only when paid.").format(
				invoice, frappe.format(si.outstanding_amount, "Currency")
			),
			title=_("Payment required"),
		)
