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


# A patient's payment by M-Pesa, card or bank carries its transaction code
# (hospital feedback, 16 Nov 2026: "we need the code from M-Pesa"), so the
# receipt shows it and the cashier's takings can be matched to the statement.


def missing_references(doc):
	"""Modes of payment on this patient payment that need a code and have none."""
	if doc.doctype == "Payment Entry":
		if doc.payment_type != "Receive" or not doc.mode_of_payment or doc.get("reference_no"):
			return []
		return [] if _is_cash(doc.mode_of_payment) else [doc.mode_of_payment]
	if not cint(doc.get("is_pos")):
		return []
	return [
		p.mode_of_payment
		for p in doc.get("payments") or []
		if flt(p.amount)
		and p.mode_of_payment
		and not _is_cash(p.mode_of_payment)
		and not p.get("reference_no")
	]


def require_payment_reference(doc, method=None):
	"""Sales Invoice / Payment Entry validate."""
	if doc.docstatus != 0 or frappe.session.user in ("Administrator", "Guest"):
		return
	if frappe.flags.in_install or frappe.flags.in_migrate or frappe.flags.in_import:
		return
	customer = doc.party if doc.doctype == "Payment Entry" else doc.get("customer")
	if doc.doctype == "Payment Entry" and doc.party_type != "Customer":
		return
	if not is_patient_customer(customer):
		return
	missing = missing_references(doc)
	if missing:
		frappe.throw(
			_(
				"Enter the transaction code (e.g. the M-Pesa code) for the {0} payment in Reference No."
			).format(", ".join(dict.fromkeys(missing))),
			title=_("Transaction code required"),
		)


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


# Take Payment (Bethesda's notes, 17 Nov 2026: "enter amount paid and amount to
# return"): the cashier types what the patient hands over; the system pays the
# bill (or part of it) and shows the change. Change is given only in cash: an
# M-Pesa, card or bank payment is for the amount owed or less.


@frappe.whitelist()
def payment_modes(company: str) -> list[dict]:
	"""The modes of payment set up for the company, cash first."""
	modes = frappe.get_all(
		"Mode of Payment",
		filters={"enabled": 1},
		fields=["name", "type"],
	)
	set_up = set(
		frappe.get_all(
			"Mode of Payment Account",
			filters={"company": company, "default_account": ["is", "set"]},
			pluck="parent",
		)
	)
	modes = [m for m in modes if m.name in set_up]
	return sorted(modes, key=lambda m: (m.type != "Cash", m.name))


@frappe.whitelist()
def take_payment(
	invoice: str, mode_of_payment: str, amount_received: float, reference_no: str | None = None
) -> dict:
	"""Pay a patient's bill: submits a draft bill first, records the payment
	(the outstanding amount at most) and returns the change for cash."""
	from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry
	from frappe.utils import nowdate

	si = frappe.get_doc("Sales Invoice", invoice)
	si.check_permission("read")
	if si.docstatus == 2 or si.get("is_return"):
		frappe.throw(_("Bill {0} is cancelled or a return.").format(si.name))
	received = flt(amount_received, 2)
	if received <= 0:
		frappe.throw(_("Enter the amount received."))
	cash = _is_cash(mode_of_payment)
	reference_no = (reference_no or "").strip()
	if not cash and not reference_no:
		frappe.throw(
			_("Enter the transaction code (e.g. the M-Pesa code) for the {0} payment.").format(
				mode_of_payment
			),
			title=_("Transaction code required"),
		)
	account = frappe.db.get_value(
		"Mode of Payment Account",
		{"parent": mode_of_payment, "company": si.company},
		"default_account",
	)
	if not account:
		frappe.throw(
			_("{0} has no account for {1}: set it on the Mode of Payment.").format(
				mode_of_payment, si.company
			)
		)
	if si.docstatus == 0:
		si.check_permission("submit")
		si.submit()
	due = flt(si.outstanding_amount, 2)
	if due <= 0:
		frappe.throw(_("Bill {0} is already paid.").format(si.name))
	if not cash and received > due:
		frappe.throw(
			_("{0} payment of {1} is more than the {2} owed: change is given only for cash.").format(
				mode_of_payment,
				frappe.format_value(received, {"fieldtype": "Currency", "options": si.currency}),
				frappe.format_value(due, {"fieldtype": "Currency", "options": si.currency}),
			)
		)
	paid = min(received, due)
	frappe.has_permission("Payment Entry", "create", throw=True)
	pe = get_payment_entry("Sales Invoice", si.name, party_amount=paid)
	pe.mode_of_payment = mode_of_payment
	pe.paid_to = account
	pe.paid_to_account_currency = frappe.db.get_value("Account", account, "account_currency")
	pe.paid_amount = pe.received_amount = paid
	for ref in pe.references:
		ref.allocated_amount = paid
	pe.reference_no = reference_no or None
	pe.reference_date = nowdate()
	pe.ke_amount_received = received
	pe.ke_change = flt(received - paid, 2) if cash else 0
	pe.insert()
	pe.submit()
	return {
		"invoice": si.name,
		"payment": pe.name,
		"paid": paid,
		"change": pe.ke_change,
		"balance": flt(due - paid, 2),
		"currency": si.currency,
	}
