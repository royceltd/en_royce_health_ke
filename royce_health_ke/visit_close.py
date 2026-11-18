# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""When a Patient Visit is finished, and closing it (IT demo, 18 Nov 2026).

One rule says what is still open on a visit (`open_items`):
	- a consultation not completed, or none completed yet (a consultation
	  visit), or nothing done yet (a lab, radiology or pharmacy only visit);
	- a lab test or imaging exam without its result (not cancelled);
	- a medicine not dispensed (nor marked Buy Outside, nor sent back to the
	  doctor), or drugs paid at the counter not handed over;
	- for the patient's own money (cash, or what insurance doesn't cover):
	  charges not billed, a draft bill, or a bill not fully paid.
The insurer's bill is not "open": it is submitted when the visit closes.

Used three ways:
	- automatically: after anything that can be a visit's last step (a
	  payment, a dispense, a result, a completed consultation) the visit
	  closes by itself once nothing is open (Kenya Health Settings > Close
	  visits automatically when finished);
	- Complete Visit (visit or patient record) is refused while anything is
	  open, listing it; a manager (Healthcare Administrator) can close it
	  anyway with a reason, kept on the visit (an absconded patient, a death);
	- Cancel Visit only while nothing has happened (no consultation, request,
	  medicine or submitted bill); its draft bills are deleted.
Visits still open after a day are on the Visits to Close report."""

import frappe
from frappe import _
from frappe.utils import cint, flt

CONSULTATION_TYPES = ("Outpatient", "Review", "Casualty")
MANAGERS = ("Healthcare Administrator", "System Manager")
DONE_DRUG = ("Dispensed", "Buy Outside", "Sent Back")


def _encounters(visit_name):
	return frappe.get_all(
		"Patient Encounter",
		filters={"ke_patient_visit": visit_name, "docstatus": ["<", 2]},
		fields=["name", "docstatus"],
	)


def _requests(encounters):
	if not encounters:
		return []
	return frappe.get_all(
		"Service Request",
		filters={"order_group": ["in", encounters], "docstatus": 1},
		fields=["name", "template_dt", "template_dn", "status"],
	)


def _drugs(encounters):
	if not encounters:
		return []
	from royce_health_ke.pharmacy import CLOSED_MR

	return frappe.get_all(
		"Medication Request",
		filters={"order_group": ["in", encounters], "docstatus": 1, "status": ["not in", CLOSED_MR]},
		fields=["name", "medication", "ke_pharmacy_status"],
	)


def _bills(visit):
	"""The patient's own open money: charges not billed, drafts, balances."""
	from royce_health_ke import visit_bill

	insured = visit_bill._insured(visit)
	split = visit_bill.splits(visit)
	items = []
	for si in frappe.get_all(
		"Sales Invoice",
		filters={"ke_patient_visit": visit.name, "docstatus": ["<", 2], "is_return": 0},
		fields=["name", "docstatus", "outstanding_amount", "ke_bill_for", "total_insurance_coverage_amount"],
	):
		if insured and si.ke_bill_for != "Patient":
			continue  # the insurer's bill: submitted at closing
		if si.docstatus == 0:
			items.append(_("Bill {0} is a draft: take the payment").format(si.name))
		elif flt(si.outstanding_amount) > 0.005:
			items.append(_("Bill {0}: {1} still owed").format(si.name, flt(si.outstanding_amount)))
	if insured and not split:
		return items
	try:
		drafted = visit_bill.on_drafts(visit.name)
		with visit_bill._as_administrator():
			lines = [
				line for line in visit_bill.unbilled_lines(visit) if (line["dt"], line["dn"]) not in drafted
			]
	except Exception:
		frappe.clear_last_message()
		return items
	if split:
		lines = [line for line in lines if not visit_bill._covered(line)]
	if lines:
		items.append(_("{0} charge(s) not billed yet").format(len(lines)))
	return items


def _undelivered_counter_drugs(visit_name):
	rows = frappe.db.sql(
		"""select si.name from `tabSales Invoice Item` sii
		join `tabSales Invoice` si on si.name = sii.parent
		join `tabItem` i on i.name = sii.item_code
		where si.ke_patient_visit = %s and si.docstatus = 1 and si.is_return = 0
			and ifnull(si.update_stock, 0) = 0 and i.is_stock_item = 1
			and ifnull(sii.reference_dt, '') != 'Medication Request'
			and ifnull(sii.delivered_qty, 0) < sii.qty""",
		visit_name,
	)
	return sorted({r[0] for r in rows})


def open_items(visit):
	"""What is still open on the visit, in words, for the person closing it."""
	from royce_health_ke.consultation import LAB_TEMPLATE, OBS_TEMPLATE, _closed, investigation_result

	if isinstance(visit, str):
		visit = frappe.get_doc("Patient Visit", visit)
	items = []
	encounters = _encounters(visit.name)
	for e in encounters:
		if e.docstatus == 0:
			items.append(_("Consultation {0} is not completed").format(e.name))
	names = [e.name for e in encounters]
	requests = _requests(names)
	drugs = _drugs(names)
	if visit.visit_type in CONSULTATION_TYPES and not any(e.docstatus == 1 for e in encounters):
		items.append(_("No consultation completed yet"))
	elif visit.visit_type not in CONSULTATION_TYPES and not (requests or drugs or _has_activity(visit.name)):
		items.append(_("Nothing done on this visit yet"))
	for r in requests:
		if r.template_dt not in (LAB_TEMPLATE, OBS_TEMPLATE) or _closed(r.status):
			continue
		done, what = investigation_result(r)
		if not done:
			items.append(_("{0}: no {1} yet").format(r.template_dn, what))
	from royce_health_ke.routing import open_nursing_items

	for name in open_nursing_items([r.name for r in requests]):
		items.append(_("{0}: not done at Nursing yet").format(name))
	for t in frappe.get_all(
		"Lab Test",
		filters={"ke_patient_visit": visit.name, "docstatus": 0, "service_request": ["is", "not set"]},
		pluck="lab_test_name",
	):
		items.append(_("{0}: no lab result yet").format(t))
	for d in drugs:
		if d.ke_pharmacy_status not in DONE_DRUG:
			items.append(_("{0}: not dispensed").format(d.medication))
	for si in _undelivered_counter_drugs(visit.name):
		items.append(_("Drugs on bill {0} not handed over").format(si))
	items.extend(_bills(visit))
	return items


def _has_activity(visit_name):
	return bool(
		frappe.db.exists("Lab Test", {"ke_patient_visit": visit_name, "docstatus": ["<", 2]})
		or frappe.db.exists("Sales Invoice", {"ke_patient_visit": visit_name, "docstatus": 1})
	)


def has_started(visit_name):
	"""Anything done on the visit beyond checking in (Cancel Visit is refused)."""
	encounters = [e.name for e in _encounters(visit_name)]
	return bool(
		encounters
		or frappe.db.exists("Sales Invoice", {"ke_patient_visit": visit_name, "docstatus": 1})
		or frappe.db.exists("Lab Test", {"ke_patient_visit": visit_name, "docstatus": ["<", 2]})
		or frappe.db.exists("Service Request", {"ke_patient_visit": visit_name, "docstatus": 1})
	)


# Closing


def _rules_on():
	"""Closing and cancelling follow the rules, except while importing,
	installing or loading the demo; tests switch them on (ke_test_visit_rules)."""
	f = frappe.flags
	if f.in_import or f.in_install or f.in_migrate or f.ke_demo:
		return False
	return not f.in_test or bool(f.ke_test_visit_rules)


def is_manager(user=None):
	return bool(set(MANAGERS) & set(frappe.get_roles(user)))


@frappe.whitelist()
def visit_open_items(visit: str) -> dict:
	"""For Complete Visit: what is open, and whether this user may close anyway."""
	doc = frappe.get_doc("Patient Visit", visit)
	doc.check_permission("read")
	return {"items": open_items(doc), "can_override": is_manager(), "status": doc.status}


def close(doc, reason=None):
	"""Complete the visit: refused while anything is open, unless a manager
	gives a reason. The caller has checked write permission."""
	from royce_health_ke.visits import _acknowledge

	if doc.status != "Open":
		frappe.throw(_("Visit {0} is {1}.").format(doc.name, _(doc.status)))
	items = open_items(doc) if _rules_on() else []
	if items:
		if not is_manager():
			frappe.throw(
				_(
					"This visit still has open items:<br>{0}<br>Finish them first, or ask a manager to close it."
				).format("<br>".join(f"• {frappe.utils.escape_html(i)}" for i in items)),
				title=_("Visit not finished"),
			)
		if not (reason or "").strip():
			frappe.throw(_("Give the reason for closing with open items."), title=_("Reason needed"))
		doc.status_reason = _("Closed by {0} with open items ({1}): {2}").format(
			frappe.utils.get_fullname(), "; ".join(items), reason.strip()
		)[:1000]
	elif reason:
		doc.status_reason = reason.strip()
	_acknowledge(doc)
	doc.status = "Completed"
	doc.save()


def cancel(doc, reason):
	if _rules_on() and has_started(doc.name):
		frappe.throw(
			_(
				"Work has started on this visit (a consultation, request or paid bill): it can't be cancelled. "
				"Complete it instead."
			),
			title=_("Can't cancel"),
		)
	for draft in frappe.get_all(
		"Sales Invoice", filters={"ke_patient_visit": doc.name, "docstatus": 0}, pluck="name"
	):
		frappe.delete_doc("Sales Invoice", draft, ignore_permissions=True)
	doc.status = "Cancelled"
	doc.status_reason = reason
	doc.save()


# Automatic closing


def _auto_on():
	f = frappe.flags
	if f.in_import or f.in_install or f.in_migrate or f.ke_demo or f.ke_closing_visit:
		return False
	if f.in_test and not f.ke_test_auto_close:
		return False
	return bool(cint(frappe.db.get_single_value("Kenya Health Settings", "auto_close_visits")))


def maybe_finish(visit_name):
	"""Close the visit by itself when nothing is open. Never stops the work
	that triggered it."""
	if not visit_name or not _auto_on():
		return False
	try:
		visit = frappe.get_doc("Patient Visit", visit_name)
	except frappe.DoesNotExistError:
		return False
	if visit.status != "Open" or visit.current_station == "Admission":
		return False
	if frappe.db.get_value("Patient", visit.patient, "inpatient_status"):
		return False
	frappe.flags.ke_closing_visit = True
	frappe.db.savepoint("ke_auto_close")
	try:
		if open_items(visit):
			return False
		from royce_health_ke.visits import _acknowledge

		_acknowledge(visit)
		visit.status = "Completed"
		visit.status_reason = _("Closed by itself: every service done and paid")
		visit.flags.ignore_permissions = True
		visit.save()
		return True
	except Exception:
		frappe.db.rollback(save_point="ke_auto_close")
		frappe.log_error(title=f"Closing visit {visit_name} automatically")
		return False
	finally:
		frappe.flags.ke_closing_visit = False


def _visit_of(doc):
	from royce_health_ke.visits import open_visit_for

	return doc.get("ke_patient_visit") or open_visit_for(doc.get("patient"))


def lab_test_done(doc, method=None):
	"""Lab Test on_submit: the result may be the visit's last step."""
	maybe_finish(_visit_of(doc))


def delivery_done(doc, method=None):
	"""Delivery Note on_submit: the dispense may be the visit's last step."""
	visits = {
		frappe.db.get_value("Sales Invoice", r.against_sales_invoice, "ke_patient_visit")
		for r in doc.items
		if r.get("against_sales_invoice")
	}
	for mr in {r.get("ke_medication_request") for r in doc.items if r.get("ke_medication_request")}:
		group = frappe.db.get_value("Medication Request", mr, "order_group")
		visits.add(group and frappe.db.get_value("Patient Encounter", group, "ke_patient_visit"))
	for v in visits - {None, ""}:
		maybe_finish(v)
