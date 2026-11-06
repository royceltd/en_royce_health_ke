# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""What happens to a rejected insurance claim line - the gap in Marley, which
marks the line Rejected but leaves the amount on the insurer's account
forever.

Two settlements, each one journal entry per rejected line, closing the line's
amount on the insurer's claims receivable (against the journal entry that put
it there):

- Bill Patient: the amount moves to the patient's account, to be collected
  like any balance. No new eTIMS invoice: the patient's invoice already
  carried the full amount.
- Write Off: the amount goes to the insurer's Rejected Claims expense account."""

import frappe
from frappe import _
from frappe.utils import flt, today

BILL_PATIENT = "Bill Patient"
WRITE_OFF = "Write Off"


def unsettled_rejections(claim):
	return [
		row
		for row in claim.coverages
		if row.status == "Rejected" and flt(row.rejected_amount) > 0 and not row.get("ke_settlement_entry")
	]


@frappe.whitelist()
def settle_rejected(claim: str, action: str, rows: str | list | None = None):
	"""Settle the claim's rejected, unsettled lines (or only `rows`, a list of
	child row names). Returns the journal entries made."""
	if action not in (BILL_PATIENT, WRITE_OFF):
		frappe.throw(_("Action must be {0} or {1}.").format(BILL_PATIENT, WRITE_OFF))
	claim = frappe.get_doc("Insurance Claim", claim)
	claim.check_permission("write")
	if claim.docstatus != 1:
		frappe.throw(_("Submit the claim and record the insurer's decision first."))
	if isinstance(rows, str):
		rows = frappe.parse_json(rows)

	payor = frappe.get_doc("Insurance Payor", claim.insurance_payor)
	receivable = _company_account(payor.claims_receivable_accounts, claim.company, _("Claims Receivable"))
	patient_customer = frappe.db.get_value("Patient", claim.patient, "customer")

	entries = []
	for row in unsettled_rejections(claim):
		if rows and row.name not in rows:
			continue
		amount = flt(row.rejected_amount)
		if action == BILL_PATIENT:
			debit = {
				"account": frappe.db.get_value("Sales Invoice", row.sales_invoice, "debit_to")
				or frappe.db.get_value("Company", claim.company, "default_receivable_account"),
				"party_type": "Customer",
				"party": patient_customer,
			}
		else:
			debit = {
				"account": _company_account(
					payor.rejected_claims_expense_accounts, claim.company, _("Rejected Claims Expense")
				),
				"cost_center": frappe.db.get_value("Company", claim.company, "cost_center"),
			}
		je = frappe.get_doc(
			{
				"doctype": "Journal Entry",
				"company": claim.company,
				"posting_date": today(),
				"user_remark": _("{0}: {1} rejected by {2} on claim {3} ({4})").format(
					action, row.item_code, claim.insurance_payor, claim.name, row.payment_error_reason
				),
				"accounts": [
					{**debit, "debit_in_account_currency": amount},
					{
						"account": receivable,
						"party_type": "Customer",
						"party": payor.customer,
						"credit_in_account_currency": amount,
						"reference_type": "Journal Entry",
						"reference_name": row.journal_entry,
					},
				],
			}
		)
		je.insert(ignore_permissions=True)
		je.submit()
		frappe.db.set_value(
			row.doctype, row.name, {"ke_rejection_settlement": action, "ke_settlement_entry": je.name}
		)
		entries.append(je.name)
	if not entries:
		frappe.throw(_("No rejected lines left to settle on {0}.").format(claim.name))
	return entries


def _company_account(rows, company, label):
	account = next((r.account for r in rows if r.company == company and r.account), None)
	if not account:
		frappe.throw(_("Set the insurer's {0} account for {1}.").format(label, company))
	return account


def on_settlement_cancel(doc, method=None):
	"""Journal Entry on_cancel: a cancelled settlement reopens its claim line."""
	for name in frappe.get_all(
		"Insurance Claim Coverage", filters={"ke_settlement_entry": doc.name}, pluck="name"
	):
		frappe.db.set_value(
			"Insurance Claim Coverage", name, {"ke_rejection_settlement": None, "ke_settlement_entry": None}
		)
