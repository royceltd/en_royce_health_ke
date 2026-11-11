# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Cashiers (Kenya Health Settings > Cashiers; both off by default).

- Only cashiers take payments: a patient's payment (a Payment Entry with a
  patient's customer, or payment taken on a POS invoice) is refused for
  users without the Cashier, Accounts Manager or System Manager role, so
  the lab, pharmacy and other service points can bill but not receive money.
- Payments need an open cashier shift: each cashier opens a Cashier Shift;
  their payments are recorded on it (and cash goes to the shift's own cash
  account when it has one); closing the shift compares the takings per
  mode of payment with what was counted.

Payments posted by the system (Administrator: M-Pesa callbacks, the demo)
and insurers' payments are not affected."""

import frappe
from frappe import _
from frappe.utils import cint, flt

CASHIER = "Cashier"
TAKERS = (CASHIER, "Accounts Manager", "System Manager")


def setting(field):
	return cint(frappe.db.get_single_value("Kenya Health Settings", field))


def _system_posting():
	if frappe.flags.in_test and not frappe.flags.ke_test_cashier:
		return True
	return (
		frappe.session.user in ("Administrator", "Guest")
		or frappe.flags.in_install
		or frappe.flags.in_migrate
		or frappe.flags.in_import
	)


def is_patient_customer(customer):
	return bool(customer) and bool(frappe.db.exists("Patient", {"customer": customer}))


def may_take_payment(user=None):
	return bool(set(TAKERS) & set(frappe.get_roles(user)))


def open_shift(company, user=None):
	return frappe.db.get_value(
		"Cashier Shift",
		{"cashier": user or frappe.session.user, "company": company, "docstatus": 0, "status": "Open"},
		["name", "cash_account"],
		as_dict=True,
	)


def _check(company, what):
	"""Refuse the payment, or return the user's open shift (or None)."""
	if setting("only_cashiers_take_payment") and not may_take_payment():
		frappe.throw(
			_("Only cashiers take payments ({0}). Send the patient to the Cashier.").format(what),
			frappe.PermissionError,
			title=_("Not a cashier"),
		)
	if not setting("require_cashier_shift"):
		return None
	shift = open_shift(company)
	if not shift:
		frappe.throw(
			_("Open your cashier shift first: Kenya Health > Cashier Shift > Add (or ask a manager)."),
			title=_("No open shift"),
		)
	return shift


def _is_cash(mode_of_payment):
	return (
		bool(mode_of_payment)
		and frappe.get_cached_value("Mode of Payment", mode_of_payment, "type") == "Cash"
	)


def payment_entry_before_validate(doc, method=None):
	if doc.docstatus != 0 or doc.party_type != "Customer" or doc.payment_type not in ("Receive", "Pay"):
		return
	if _system_posting() or not is_patient_customer(doc.party):
		return
	shift = _check(doc.company, _("payment {0}").format(doc.name if not doc.is_new() else ""))
	if not shift:
		return
	doc.ke_cashier_shift = shift.name
	if shift.cash_account and _is_cash(doc.mode_of_payment):
		from erpnext.accounts.utils import get_account_currency

		if doc.payment_type == "Receive":
			doc.paid_to = shift.cash_account
			doc.paid_to_account_currency = get_account_currency(shift.cash_account)
		else:
			doc.paid_from = shift.cash_account
			doc.paid_from_account_currency = get_account_currency(shift.cash_account)


def invoice_before_validate(doc, method=None):
	"""Payment taken on the invoice itself (POS, Include Payment)."""
	if doc.docstatus != 0 or not cint(doc.get("is_pos")):
		return
	if not any(flt(p.amount) for p in doc.get("payments") or []):
		return
	if _system_posting() or not is_patient_customer(doc.customer):
		return
	shift = _check(doc.company, _("payment on invoice"))
	if not shift:
		return
	doc.ke_cashier_shift = shift.name
	if shift.cash_account:
		for p in doc.payments:
			if _is_cash(p.mode_of_payment):
				p.account = shift.cash_account


def takings(shift):
	"""{mode of payment: (payments, amount)} on a shift: payments received
	less refunds, and payments on its POS invoices less change given."""
	out = {}

	def add(mode, amount):
		count, total = out.get(mode, (0, 0))
		out[mode] = (count + 1, total + flt(amount))

	for pe in frappe.get_all(
		"Payment Entry",
		filters={"ke_cashier_shift": shift, "docstatus": 1},
		fields=["mode_of_payment", "payment_type", "paid_amount", "received_amount"],
	):
		if pe.payment_type == "Receive":
			add(pe.mode_of_payment, pe.received_amount)
		else:
			add(pe.mode_of_payment, -flt(pe.paid_amount))
	invoices = frappe.get_all(
		"Sales Invoice",
		filters={"ke_cashier_shift": shift, "docstatus": 1},
		fields=["name", "change_amount"],
	)
	for inv in invoices:
		rows = frappe.get_all(
			"Sales Invoice Payment",
			filters={"parent": inv.name, "parenttype": "Sales Invoice"},
			fields=["mode_of_payment", "amount"],
		)
		for row in rows:
			if flt(row.amount):
				add(row.mode_of_payment, row.amount)
		if flt(inv.change_amount):
			cash = next((r.mode_of_payment for r in rows if _is_cash(r.mode_of_payment)), None)
			if cash:
				count, total = out[cash]
				out[cash] = (count, total - flt(inv.change_amount))
	return out


def extend_bootinfo(bootinfo):
	try:
		bootinfo.ke_payment_blocked = cint(setting("only_cashiers_take_payment") and not may_take_payment())
	except Exception:
		bootinfo.ke_payment_blocked = 0
