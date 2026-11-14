# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Billing approvals: the Cashier (or reception, or the accounts office) asks,
a manager decides, and the approval applies itself.

- Discount: off the visit's draft bill (a percentage, or an amount off the
  grand total). The bill must still be a draft when approved; once
  submitted, ask for a waiver instead.
- Waiver: what the patient can't pay on a submitted bill is written off: a
  Journal Entry debits the waiver account (Kenya Health Settings > Waiver
  Account, else the company's write-off account) and credits the patient's
  balance on that bill.
- Pay Later: the visit is served before payment (the same switch as the
  manager's "Allow Services Before Payment").

Managers are the roles that approve services before payment
(visit_bill.CREDIT_ROLES). Nobody decides their own request."""

import frappe
from frappe import _
from frappe.utils import flt, now_datetime, nowdate

from royce_health_ke.visit_bill import CREDIT_ROLES, _as_administrator, refresh_bill_status

DISCOUNT, WAIVER, PAY_LATER = "Discount", "Waiver", "Pay Later"


def is_manager(user=None):
	return bool(set(CREDIT_ROLES) & set(frappe.get_roles(user or frappe.session.user)))


def validate_request(doc):
	if doc.is_new():
		doc.status = "Pending"
		doc.requested_by = frappe.session.user
		doc.requested_on = now_datetime()
	elif doc.status != "Pending" and doc.has_value_changed("amount"):
		frappe.throw(_("A decided request can't be changed. Make a new one."))
	visit = frappe.db.get_value(
		"Patient Visit", doc.patient_visit, ["patient", "status", "allow_credit"], as_dict=True
	)
	if not visit:
		frappe.throw(_("Unknown visit {0}.").format(doc.patient_visit))
	if doc.request_type == PAY_LATER:
		doc.sales_invoice = doc.amount = doc.discount_percentage = None
		if doc.status == "Pending" and visit.allow_credit:
			frappe.throw(_("This visit is already served before payment."))
		return
	if not doc.sales_invoice:
		frappe.throw(_("Choose the bill."))
	si = frappe.db.get_value(
		"Sales Invoice",
		doc.sales_invoice,
		["docstatus", "ke_patient_visit", "grand_total", "outstanding_amount", "is_return"],
		as_dict=True,
	)
	if not si or si.ke_patient_visit != doc.patient_visit or si.is_return:
		frappe.throw(_("{0} is not a bill of visit {1}.").format(doc.sales_invoice, doc.patient_visit))
	doc.invoice_total = si.grand_total
	doc.invoice_balance = si.outstanding_amount if si.docstatus == 1 else None
	if doc.status != "Pending":
		return
	if doc.request_type == DISCOUNT:
		if si.docstatus != 0:
			frappe.throw(
				_("{0} is already submitted. Ask for a waiver of what the patient can't pay instead.").format(
					doc.sales_invoice
				)
			)
		pct, amount = flt(doc.discount_percentage), flt(doc.amount)
		if not (0 < pct <= 100) and not (0 < amount <= flt(si.grand_total)):
			frappe.throw(_("Enter a discount percentage (up to 100) or an amount up to the bill's total."))
		if pct:
			doc.amount = None
	elif doc.request_type == WAIVER:
		if si.docstatus != 1 or flt(si.outstanding_amount) <= 0:
			frappe.throw(_("{0} has no balance to waive.").format(doc.sales_invoice))
		doc.discount_percentage = None
		doc.amount = flt(doc.amount) or flt(si.outstanding_amount)
		if doc.amount > flt(si.outstanding_amount) + 0.005:
			frappe.throw(
				_("The bill's balance is {0}.").format(frappe.format(si.outstanding_amount, "Currency"))
			)


def _pending(name):
	if not is_manager():
		frappe.throw(_("Only a manager decides discounts, waivers and pay-later."), frappe.PermissionError)
	doc = frappe.get_doc("Bill Approval Request", name)
	if doc.status != "Pending":
		frappe.throw(_("{0} is already {1}.").format(doc.name, _(doc.status).lower()))
	if frappe.session.user in (doc.requested_by, doc.owner):
		frappe.throw(_("You can't decide your own request. Another manager does."))
	return doc


@frappe.whitelist()
def request(
	visit: str,
	request_type: str,
	reason: str,
	sales_invoice: str | None = None,
	discount_percentage: float | None = None,
	amount: float | None = None,
):
	doc = frappe.get_doc(
		{
			"doctype": "Bill Approval Request",
			"patient_visit": visit,
			"request_type": request_type,
			"reason": reason,
			"sales_invoice": sales_invoice,
			"discount_percentage": discount_percentage,
			"amount": amount,
		}
	).insert()
	return doc.name


@frappe.whitelist()
def approve(name: str, remarks: str | None = None):
	doc = _pending(name)
	approver = frappe.session.user
	# The manager's authority is checked above; the change itself (a bill, a
	# journal entry) is made with system rights, as a manager without
	# accounting roles can't otherwise touch the accounts it uses.
	with _as_administrator():
		if doc.request_type == DISCOUNT:
			_apply_discount(doc, approver)
		elif doc.request_type == WAIVER:
			doc.journal_entry = _waive(doc)
		else:
			_pay_later(doc, approver)
	doc.status, doc.approved_by, doc.approved_on, doc.approver_remarks = (
		"Approved",
		frappe.session.user,
		now_datetime(),
		remarks,
	)
	doc.flags.ignore_permissions = True
	doc.save()
	refresh_bill_status(doc.patient_visit)
	return doc.name


@frappe.whitelist()
def reject(name: str, remarks: str):
	if not (remarks or "").strip():
		frappe.throw(_("Say why."))
	doc = _pending(name)
	doc.status, doc.approved_by, doc.approved_on, doc.approver_remarks = (
		"Rejected",
		frappe.session.user,
		now_datetime(),
		remarks,
	)
	doc.flags.ignore_permissions = True
	doc.save()
	return doc.name


def _apply_discount(doc, approver):
	si = frappe.get_doc("Sales Invoice", doc.sales_invoice)
	if si.docstatus != 0:
		frappe.throw(_("{0} was submitted in the meantime. Ask for a waiver instead.").format(si.name))
	si.apply_discount_on = "Grand Total"
	if flt(doc.discount_percentage):
		si.additional_discount_percentage = flt(doc.discount_percentage)
		si.discount_amount = 0
	else:
		si.additional_discount_percentage = 0
		si.discount_amount = flt(doc.amount)
	si.add_comment(
		"Comment",
		_("Discount approved by {0} ({1}): {2}").format(
			frappe.utils.get_fullname(approver), doc.name, doc.reason
		),
	)
	si.flags.ignore_permissions = True
	si.save()


def waiver_account(company):
	return frappe.db.get_single_value("Kenya Health Settings", "waiver_account") or frappe.get_cached_value(
		"Company", company, "write_off_account"
	)


def _waive(doc):
	si = frappe.db.get_value(
		"Sales Invoice",
		doc.sales_invoice,
		["company", "customer", "debit_to", "outstanding_amount", "cost_center", "docstatus"],
		as_dict=True,
	)
	if si.docstatus != 1 or flt(si.outstanding_amount) + 0.005 < flt(doc.amount):
		frappe.throw(_("{0}'s balance changed. Make a new request.").format(doc.sales_invoice))
	account = waiver_account(si.company)
	if not account:
		frappe.throw(
			_("Set the Waiver Account in Kenya Health Settings (or the company's write-off account).")
		)
	cost_center = si.cost_center or frappe.get_cached_value("Company", si.company, "cost_center")
	je = frappe.get_doc(
		{
			"doctype": "Journal Entry",
			"voucher_type": "Write Off Entry",
			"company": si.company,
			"posting_date": nowdate(),
			"user_remark": _("Waiver {0} on {1}: {2}").format(doc.name, doc.sales_invoice, doc.reason),
			"accounts": [
				{
					"account": account,
					"debit_in_account_currency": flt(doc.amount),
					"cost_center": cost_center,
				},
				{
					"account": si.debit_to,
					"party_type": "Customer",
					"party": si.customer,
					"credit_in_account_currency": flt(doc.amount),
					"reference_type": "Sales Invoice",
					"reference_name": doc.sales_invoice,
					"cost_center": cost_center,
				},
			],
		}
	)
	je.flags.ignore_permissions = True
	je.insert()
	je.submit()
	return je.name


def _pay_later(doc, approver):
	visit = frappe.get_doc("Patient Visit", doc.patient_visit)
	visit.update({"allow_credit": 1, "credit_reason": doc.reason, "credit_approved_by": approver})
	visit.flags.ignore_permissions = True
	visit.save()


@frappe.whitelist()
def for_visit(visit: str):
	"""The visit's requests, newest first, for its Bill section."""
	frappe.has_permission("Patient Visit", "read", visit, throw=True)
	return frappe.get_all(
		"Bill Approval Request",
		filters={"patient_visit": visit},
		fields=["name", "request_type", "status", "sales_invoice", "discount_percentage", "amount", "reason"],
		order_by="creation desc",
	)


def journal_entry_cancelled(doc, method=None):
	"""A cancelled waiver entry: the request no longer stands."""
	for name in frappe.get_all("Bill Approval Request", filters={"journal_entry": doc.name}, pluck="name"):
		frappe.db.set_value(
			"Bill Approval Request",
			name,
			{"status": "Rejected", "approver_remarks": _("Waiver entry {0} cancelled.").format(doc.name)},
		)
