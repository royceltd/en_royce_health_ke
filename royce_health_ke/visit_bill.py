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
later, and a manager can approve services before payment on a visit. With
"Insured: uncovered items paid first" on, an insured patient is served first
only for what the scheme covers (coverage.py): the rest is billed to the
patient on an invoice of its own and paid before it is done."""

from contextlib import contextmanager

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, nowdate

from royce_health_ke import coverage
from royce_health_ke.visits import open_visit_for

LAB, RADIOLOGY, PHARMACY, TRIAGE = "lab", "radiology", "pharmacy", "triage"
SETTING = {
	LAB: "pay_before_lab",
	RADIOLOGY: "pay_before_radiology",
	PHARMACY: "pay_before_pharmacy",
	TRIAGE: "pay_before_triage",
}
FEE_VISIT_TYPES = ("Outpatient", "Review")
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
	fee = visit_fee_line(visit)
	if fee:
		lines.append(fee)
	from royce_health_ke.fees import marley_rule

	with _as_administrator(), marley_rule():
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
				# bought outside, or sent back to the doctor: not billed
				if frappe.db.get_value("Medication Request", d["reference_name"], "ke_pharmacy_status") in (
					"Buy Outside",
					"Sent Back",
				):
					continue
				line = {
					"dt": d["reference_type"],
					"dn": d["reference_name"],
					"item": d["drug_code"],
					"qty": d.get("quantity"),
					"rate": False,
					"income_account": False,
					"description": d.get("description") or False,
				}
				cover = frappe.db.get_value(
					"Medication Request", d["reference_name"], "ke_insurance_coverage"
				)
				lines.extend(coverage.drug_lines(line, cover))
	return lines


# The consultation fee before triage (Kenya Health Settings > Consultation fee
# before triage). A walk-in's fee is billed on the visit itself, the way
# Marley bills an appointment: from the doctor's consultation charge when the
# doctor is already chosen, else from the Service Type's charge for the
# department. The visit's first consultation is then not billed again
# (visits.link_encounter). A booked appointment carries its own fee.


def consultation_fee(visit):
	"""(item, rate) of the visit's consultation fee; rate 0 when none is set
	(the hospital's fee rule: royce_health_ke.fees)."""
	from royce_health_ke import fees

	return fees.consultation_fee(
		frappe._dict(
			practitioner=visit.get("practitioner"),
			appointment_type=visit.get("appointment_type"),
			department=visit.get("department"),
			service_unit=visit.get("consultation_room"),
			company=visit.get("company"),
			payment_method=visit.get("payment_method"),
			insurance_policy=visit.get("insurance_policy"),
		)
	)


def fee_reference(visit):
	"""Where the consultation fee is billed: the booked appointment, or the visit."""
	if visit.get("appointment"):
		return "Patient Appointment", visit.appointment
	return "Patient Visit", visit.name


def visit_fee_line(visit):
	if not visit.get("fee_first") or visit.get("appointment") or visit.get("invoiced"):
		return None
	item, rate = consultation_fee(visit)
	if not item or not rate:
		return None
	return {
		"dt": "Patient Visit",
		"dn": visit.name,
		"item": item,
		"qty": 1,
		"rate": rate,
		"income_account": False,
		"description": _("Consultation fee"),
	}


def needs_fee_first(visit):
	"""A cash consultation pays its fee before triage."""
	if (
		visit.get("payment_method") != "Cash"
		or visit.get("visit_type") not in FEE_VISIT_TYPES
		or visit.get("allow_credit")
		or not enforced(TRIAGE)
	):
		return False
	if visit.get("appointment"):
		return not is_paid("Patient Appointment", visit.appointment)
	_item, rate = consultation_fee(visit)
	return rate > 0


def fee_due(visit):
	"""The patient has a consultation fee to pay before triage or the doctor."""
	return bool(
		visit.get("fee_first")
		and not visit.get("fee_paid")
		and not visit.get("allow_credit")
		and not is_paid(*fee_reference(visit))
	)


def _fee_paid(visit):
	"""Once the fee is paid, the patient waiting at the Cashier joins the triage list."""
	if not visit.get("fee_first") or visit.get("fee_paid") or not is_paid(*fee_reference(visit)):
		return
	from royce_health_ke.visits import FIRST_STATION, _move

	visit.fee_paid = 1
	if visit.status == "Open" and visit.current_station == "Cashier":
		_move(
			visit, "Cashier", FIRST_STATION.get(visit.visit_type, "Triage"), note=_("Consultation fee paid")
		)
	visit.flags.ignore_permissions = True
	visit.save()


# Cash patients pay at the Cashier between the doctor and the service points
# (Bethesda's notes, 17 Nov 2026: "if cash, return to billing; in all cases").
# A cash patient sent to the lab, radiology or pharmacy with requests there not
# paid goes to the Cashier instead; the visit remembers where they were going
# (after_payment), and once paid they join that service point's list.

SERVICE_STATIONS = {LAB: "Laboratory", RADIOLOGY: "Radiology", PHARMACY: "Pharmacy"}


def drug_awaiting_payment(medication_request):
	"""A cash patient's prescription not paid yet (drugs leave only once paid)."""
	if not enforced(PHARMACY):
		return False
	m = frappe.db.get_value(
		"Medication Request",
		medication_request,
		["patient", "order_group", "ke_insurance_coverage", "ke_pharmacy_status"],
		as_dict=True,
	)
	if not m or m.ke_pharmacy_status in ("Buy Outside", "Sent Back"):
		return False
	visit = m.order_group and frappe.db.get_value("Patient Encounter", m.order_group, "ke_patient_visit")
	cover = m.ke_insurance_coverage
	insured = bool(cover) and (not coverage.pays_uncovered() or coverage.is_covered(cover))
	if exemption(m.patient, visit or None, None, insured):
		return False
	return not is_paid("Medication Request", medication_request)


def awaiting_stations(visit_name):
	"""The service points with this visit's requests waiting for payment, in
	the order the patient goes: Laboratory, Radiology, Pharmacy."""
	from royce_health_ke.consultation import _kind
	from royce_health_ke.lab import CLOSED_REQUEST
	from royce_health_ke.pharmacy import CLOSED_MR

	encounters = frappe.get_all(
		"Patient Encounter", filters={"ke_patient_visit": visit_name, "docstatus": ["<", 2]}, pluck="name"
	)
	if not encounters:
		return []
	found = set()
	for r in frappe.get_all(
		"Service Request",
		filters={"order_group": ["in", encounters], "docstatus": 1, "status": ["not in", CLOSED_REQUEST]},
		fields=["name", "template_dt", "template_dn"],
	):
		kind = _kind(r)
		if kind in (LAB, RADIOLOGY) and request_awaiting_payment(kind, r.name):
			found.add(SERVICE_STATIONS[kind])
	for mr in frappe.get_all(
		"Medication Request",
		filters={"order_group": ["in", encounters], "docstatus": 1, "status": ["not in", CLOSED_MR]},
		pluck="name",
	):
		if drug_awaiting_payment(mr):
			found.add(SERVICE_STATIONS[PHARMACY])
			break
	return [s for s in SERVICE_STATIONS.values() if s in found]


def _requests_paid(visit):
	"""Paid at the Cashier: the patient joins the list of the first service
	point they were going to whose requests are now paid."""
	if visit.status != "Open" or visit.current_station != "Cashier" or not visit.get("after_payment"):
		return
	if fee_due(visit):
		return
	from royce_health_ke.visits import _move

	planned = [s.strip() for s in visit.after_payment.split(",") if s.strip()]
	waiting = set(awaiting_stations(visit.name))
	ready = [s for s in planned if s not in waiting]
	if not ready:
		return
	_move(visit, "Cashier", ready[0], note=_("Paid at the Cashier"))
	visit.after_payment = ", ".join(s for s in planned if s != ready[0])
	visit.flags.ignore_permissions = True
	visit.save()


def _invoice(visit, lines, bill_for=None):
	si = frappe.new_doc("Sales Invoice")
	si.update(
		{
			"customer": frappe.db.get_value("Patient", visit.patient, "customer"),
			"patient": visit.patient,
			"patient_name": visit.patient_name,
			"company": visit.company,
			"ke_patient_visit": visit.name,
			"ke_bill_for": bill_for,
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
	if unbilled or any(i.docstatus == 0 for i in raised):
		return "To Bill"
	if any(flt(i.outstanding_amount) > 0 for i in submitted):
		return "Unpaid"
	return "Paid" if submitted else ""


def on_drafts(visit_name):
	"""(reference doctype, name) of every line already on one of the visit's
	draft invoices: Marley still counts those as unbilled."""
	drafts = frappe.get_all(
		"Sales Invoice", filters={"ke_patient_visit": visit_name, "docstatus": 0}, pluck="name"
	)
	if not drafts:
		return set()
	return {
		(r.reference_dt, r.reference_dn)
		for r in frappe.get_all(
			"Sales Invoice Item",
			filters={"parent": ["in", drafts], "reference_dn": ["is", "set"]},
			fields=["reference_dt", "reference_dn"],
		)
	}


@frappe.whitelist()
def visit_bill(visit: str) -> dict:
	"""The visit's running bill: unbilled charges priced, its invoices, totals."""
	doc = frappe.get_doc("Patient Visit", visit)
	doc.check_permission("read")
	try:
		drafted = on_drafts(doc.name)
		all_lines = unbilled_lines(doc)
		lines = [line for line in all_lines if (line["dt"], line["dn"]) not in drafted]
	except frappe.ValidationError as e:
		# Marley stops at a missing price setup, e.g. a doctor with no consultation charge.
		frappe.clear_last_message()
		return {"error": _("The bill can't be worked out yet: {0}").format(frappe.utils.strip_html(str(e)))}
	charges, unbilled_total, currency = [], 0, None
	if all_lines:
		if not frappe.db.get_value("Patient", doc.patient, "customer"):
			return {"error": _("The patient has no customer record, so nothing can be priced or billed.")}
		with _as_administrator():
			si = _invoice(doc, all_lines)
			_apply_billing_rules(si)
		currency = si.currency
		charges = [
			{
				"item": row.item_name or row.item_code,
				"reference_dt": row.reference_dt,
				"reference_dn": row.reference_dn,
				"qty": row.qty,
				"rate": row.rate,
				"amount": row.amount,
				"insurance": flt(row.get("insurance_coverage_amount")),
				"covered": bool(row.get("insurance_coverage")),
				# already on one of the visit's draft bills (Marley still counts it unbilled)
				"on_draft": (row.reference_dt, row.reference_dn) in drafted,
			}
			for row in si.items
		]
		on_draft = sum(c["amount"] for c in charges if c["on_draft"])
		unbilled_total = max(flt(si.grand_total) - on_draft, 0)
	split = splits(doc)
	patient_now = sum(c["amount"] for c in charges if not c["covered"] and not c["on_draft"]) if split else 0
	raised = invoices(doc.name)
	submitted = [i for i in raised if i.docstatus == 1]
	billed = sum(flt(i.grand_total) for i in submitted)
	insurance = sum(flt(i.total_insurance_coverage_amount) for i in submitted)
	balance = sum(flt(i.outstanding_amount) for i in submitted)
	draft_total = sum(flt(i.grand_total) for i in raised if i.docstatus == 0 and not i.is_return)
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
		"to_pay": balance + draft_total + unbilled_total,
		"draft_total": draft_total,
		"status": status,
		"split": split,
		"patient_now": patient_now,
		"can_bill": bool(frappe.has_permission("Sales Invoice", "create")),
		"can_approve_credit": bool(set(CREDIT_ROLES) & set(frappe.get_roles())),
		"approvals": _approvals(doc.name),
		"can_request": bool(frappe.has_permission("Bill Approval Request", "create")),
	}


def _approvals(visit):
	from royce_health_ke.approvals import for_visit

	return for_visit(visit)


def refresh_bill_status(visit_name):
	if not visit_name or not frappe.db.exists("Patient Visit", visit_name):
		return
	visit = frappe.get_doc("Patient Visit", visit_name)
	auto_bill(visit)
	try:
		_fee_paid(visit)
		_requests_paid(visit)
	except Exception:
		# Moving the patient on must never stop the payment.
		frappe.log_error(title=f"Moving {visit_name} on after payment")
	try:
		status = bill_status(unbilled_lines(visit), invoices(visit_name))
	except Exception:
		# A bill status must never stop the lab, the pharmacy or the cashier.
		frappe.log_error(title=f"Bill status of {visit_name}")
		return
	if status != (visit.bill_status or ""):
		frappe.db.set_value("Patient Visit", visit_name, "bill_status", status, update_modified=False)


# Insured visits are billed automatically (Kenya Health Settings > Billing)


def auto_bills_insured():
	return bool(frappe.db.get_single_value("Kenya Health Settings", "auto_bill_insured"))


def _insured(visit):
	return visit.payment_method == "Insurance" and visit.insurance_policy


def splits(visit):
	"""An insured visit billed on two invoices: the insurer's (covered
	charges, made and submitted automatically) and the patient's (what the
	scheme doesn't cover, made by the cashier and paid first)."""
	return bool(_insured(visit)) and coverage.pays_uncovered() and auto_bills_insured()


def _covered(line):
	return bool(line.get("insurance_coverage"))


def _draft(visit_name, bill_for=None):
	"""The visit's draft invoice; 'Insurer' or 'Patient' picks one of an
	insured visit's two (an untagged draft is the insurer's)."""
	for d in frappe.get_all(
		"Sales Invoice",
		filters={"ke_patient_visit": visit_name, "docstatus": 0},
		fields=["name", "ke_bill_for"],
		order_by="creation asc",
	):
		patients = d.ke_bill_for == "Patient"
		if not bill_for or (bill_for == "Patient") == patients:
			return d.name
	return None


def auto_bill(visit, closing=False):
	"""Keep an insured visit's draft invoice current: whatever was ordered or
	given and is not billed yet is added to it (the draft is made with the
	first charge). Never stops the clinical work that triggered it."""
	if frappe.flags.ke_auto_billing or not auto_bills_insured():
		return None
	if (visit.status != "Open" and not closing) or not _insured(visit):
		return None
	if not frappe.db.get_value("Patient", visit.patient, "customer"):
		return None
	frappe.flags.ke_auto_billing = True
	frappe.db.savepoint("ke_auto_bill")
	try:
		with _as_administrator():
			lines = unbilled_lines(visit)
			if coverage.pays_uncovered():
				# what the scheme doesn't cover is the patient's own bill
				lines = [line for line in lines if _covered(line)]
			draft = _draft(visit.name, "Insurer")
			if draft:
				si = frappe.get_doc("Sales Invoice", draft)
				on_bill = {(r.reference_dt, r.reference_dn) for r in si.items}
				new = [line for line in lines if (line["dt"], line["dn"]) not in on_bill]
				if new:
					si.set_healthcare_services(new)
					si.flags.ignore_permissions = True
					si.save()
			elif lines:
				si = _invoice(visit, lines, "Insurer")
				si.flags.ignore_permissions = True
				si.insert()
			else:
				si = None
		return si
	except Exception:
		frappe.db.rollback(save_point="ke_auto_bill")
		frappe.log_error(title=f"Automatic bill of {visit.name}")
		return None
	finally:
		frappe.flags.ke_auto_billing = False


def finalize_insured_bill(visit):
	"""Patient Visit closed: bring the insured visit's draft invoice up to date
	and submit it, so the insurer's share goes to its claim and KRA signs it.
	A copay stays on the invoice for the cashier. If it can't be submitted,
	the visit still closes and the bill waits in draft for the cashier."""
	if not auto_bills_insured() or not _insured(visit):
		return
	auto_bill(visit, closing=True)
	draft = _draft(visit.name, "Insurer")
	if not draft:
		return
	frappe.db.savepoint("ke_insured_submit")
	try:
		with _as_administrator():
			si = frappe.get_doc("Sales Invoice", draft)
			si.flags.ignore_permissions = True
			si.submit()
		frappe.msgprint(
			_("Insured bill {0} submitted.").format(frappe.utils.get_link_to_form("Sales Invoice", draft)),
			alert=True,
			indicator="green",
		)
	except Exception as e:
		frappe.db.rollback(save_point="ke_insured_submit")
		frappe.clear_last_message()
		frappe.log_error(title=f"Submit insured bill of {visit.name}")
		frappe.msgprint(
			_(
				"The visit is closed, but its bill {0} could not be submitted and waits in draft for the cashier: {1}"
			).format(frappe.utils.get_link_to_form("Sales Invoice", draft), frappe.utils.strip_html(str(e))),
			title=_("Bill not submitted"),
			indicator="orange",
		)


@frappe.whitelist()
def make_bill(visit: str, lines: str | list | None = None):
	"""A draft invoice of the visit's unbilled charges, for the cashier.
	`lines`: the charges ticked, as [reference doctype, reference name] pairs
	(all of them when not given). What isn't ticked stays to bill later, and
	a request not paid stays off its service point's worklist."""
	ticked = None
	if isinstance(lines, str):
		# the browser sends an empty value (or "null") when every charge is ticked
		lines = frappe.parse_json(lines) if lines.strip() not in ("", "null") else None
	if lines is not None:
		ticked = {tuple(x) for x in lines}
		if not ticked:
			frappe.throw(_("Tick at least one charge to bill."))
	frappe.has_permission("Sales Invoice", "create", throw=True)
	doc = frappe.get_doc("Patient Visit", visit)
	doc.check_permission("read")
	split = splits(doc)
	draft = _draft(visit, "Patient" if split else None)
	if draft:
		return {"existing": draft}
	if not frappe.db.get_value("Patient", doc.patient, "customer"):
		frappe.throw(_("Link a customer to patient {0} first.").format(doc.patient_name))
	lines = unbilled_lines(doc)
	if ticked is not None:
		lines = [line for line in lines if (line["dt"], line["dn"]) in ticked]
	if split:
		# the covered charges are on the insurer's bill, submitted when the visit closes
		lines = [line for line in lines if not _covered(line)]
		if not lines:
			frappe.throw(
				_(
					"Everything left to bill on this visit is covered by insurance. It is on the insurer's "
					"bill, which is submitted when the visit is closed."
				)
			)
	if not lines:
		frappe.throw(_("Nothing on this visit is waiting to be billed."))
	bill = _invoice(doc, lines, "Patient" if split else None).as_dict()
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
	r = frappe.db.get_value(
		"Service Request", service_request, ["order_group", "ke_patient_visit"], as_dict=True
	)
	if not r:
		return None
	return r.ke_patient_visit or (
		r.order_group and frappe.db.get_value("Patient Encounter", r.order_group, "ke_patient_visit")
	)


def exemption(patient, visit=None, inpatient_record=None, insured=False):
	"""Why this patient is served before paying, or None. `insured`: the
	item itself is covered by the patient's insurance. An insured visit
	covers everything on it only while uncovered items aren't paid first."""
	if insured:
		return "insured"
	if inpatient_record or frappe.db.get_value("Patient", patient, "inpatient_status") in INPATIENT_STATUSES:
		return "inpatient"
	visit = visit or open_visit_for(patient)
	if visit:
		v = frappe.db.get_value(
			"Patient Visit", visit, ["payment_method", "visit_type", "allow_credit"], as_dict=True
		)
		if v and v.payment_method == "Insurance" and not coverage.pays_uncovered():
			return "insured"
		if v and v.visit_type == "Casualty":
			return "casualty"
		if v and v.allow_credit:
			return "approved"
	return None


def require_payment(
	kind, patient, dt, dn, what, visit=None, inpatient_record=None, insured=False, uncovered=None
):
	"""`uncovered`: why the patient's insurance doesn't pay for it, if insured."""
	if not enforced(kind) or exemption(patient, visit, inpatient_record, insured) or is_paid(dt, dn):
		return
	name = frappe.db.get_value("Patient", patient, "patient_name") or patient
	if uncovered:
		message = _(
			"{0} for {1} is {2}, so it is paid first. Send the patient to the "
			"Cashier, or ask a manager to approve services before payment on the visit."
		).format(what, name, uncovered)
	else:
		message = _(
			"{0} for {1} is not paid yet. Send the patient to the Cashier, or ask a manager to approve "
			"services before payment on the visit."
		).format(what, name)
	frappe.throw(message, title=_("Payment required"))


def _cover(policy, cover):
	"""(insured, uncovered reason) of an item ordered with this policy and cover."""
	if not policy:
		return False, None
	if not coverage.pays_uncovered():
		return True, None
	if coverage.is_covered(cover):
		return True, None
	return False, coverage.reason_for(cover)


def _request_gate(kind, request, what):
	r = frappe.db.get_value(
		"Service Request",
		request,
		["patient", "inpatient_record", "insurance_policy", "insurance_coverage"],
		as_dict=True,
	)
	if r:
		insured, uncovered = _cover(r.insurance_policy, r.insurance_coverage)
		require_payment(
			kind,
			r.patient,
			"Service Request",
			request,
			what,
			visit=visit_of_request(request),
			inpatient_record=r.inpatient_record,
			insured=insured,
			uncovered=uncovered,
		)


def request_awaiting_payment(kind, request):
	"""A service point's worklist leaves out a cash request not paid yet
	(the patient is at the Cashier): it is listed once paid."""
	if not enforced(kind):
		return False
	r = frappe.db.get_value(
		"Service Request",
		request,
		["patient", "inpatient_record", "insurance_policy", "insurance_coverage"],
		as_dict=True,
	)
	if not r:
		return False
	insured, _uncovered = _cover(r.insurance_policy, r.insurance_coverage)
	if exemption(r.patient, visit_of_request(request), r.inpatient_record, insured):
		return False
	return not is_paid("Service Request", request)


def lab_test_before_insert(doc, method=None):
	"""A requested test is started only once its request is paid."""
	if doc.get("service_request"):
		_request_gate(
			LAB, doc.service_request, _("Lab test {0}").format(doc.get("lab_test_name") or doc.template)
		)


def lab_test_before_submit(doc, method=None):
	"""A test done without a request: its results are released once it is paid."""
	if not doc.get("service_request"):
		insured = coverage.pays_uncovered() and coverage.is_covered(doc.get("insurance_coverage"))
		require_payment(
			LAB,
			doc.patient,
			"Lab Test",
			doc.name,
			_("Lab test {0}").format(doc.get("lab_test_name") or doc.template),
			inpatient_record=doc.get("inpatient_record"),
			insured=insured,
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


def _drugs_insured(items):
	"""The invoice's drugs are the insurer's to pay: every one covered (any
	one, while uncovered items aren't paid first)."""
	if not coverage.pays_uncovered():
		return any(row.get("insurance_coverage") for row in items)
	stock = set(_stock_lines(items) or [])
	return all(row.get("insurance_coverage") for row in items if row.item_code in stock)


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
	if exemption(doc.patient, doc.get("ke_patient_visit"), insured=_drugs_insured(doc.items)):
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
		rows = frappe.get_all(
			"Sales Invoice Item", filters={"parent": invoice}, fields=["item_code", "insurance_coverage"]
		)
		if exemption(si.patient, si.ke_patient_visit, insured=_drugs_insured(rows)):
			continue
		frappe.throw(
			_("Invoice {0} has {1} unpaid. Drugs leave the store only when paid.").format(
				invoice, frappe.format(si.outstanding_amount, "Currency")
			),
			title=_("Payment required"),
		)
