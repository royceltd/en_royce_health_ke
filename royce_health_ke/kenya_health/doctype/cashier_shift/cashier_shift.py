# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""A cashier's shift: open (draft) while taking payments, submitted to close
with the count. See royce_health_ke.cashier."""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, now_datetime

from royce_health_ke import cashier


class CashierShift(Document):
	def validate(self):
		if (
			self.is_new()
			and self.cashier != frappe.session.user
			and not {"Accounts Manager", "System Manager"} & set(frappe.get_roles())
		):
			frappe.throw(_("You can only open a shift for yourself."))
		if self.is_new() or self.docstatus == 0:
			other = frappe.db.get_value(
				"Cashier Shift",
				{
					"cashier": self.cashier,
					"company": self.company,
					"docstatus": 0,
					"name": ["!=", self.name],
				},
			)
			if other:
				frappe.throw(_("{0} already has an open shift: {1}.").format(self.cashier, other))
		if self.cash_account:
			company, account_type, is_group = frappe.db.get_value(
				"Account", self.cash_account, ["company", "account_type", "is_group"]
			)
			if company != self.company or is_group or account_type != "Cash":
				frappe.throw(
					_("Cash Account must be a cash account (not a group) of {0}.").format(self.company)
				)
		self.refresh_totals()

	def refresh_totals(self):
		counted = {r.mode_of_payment: r.counted for r in self.totals}
		taken = cashier.takings(self.name) if not self.is_new() else {}
		modes = list(dict.fromkeys([*taken, *counted]))
		if flt(self.opening_float):
			cash = next((m for m in modes if cashier._is_cash(m)), None) or frappe.db.get_value(
				"Mode of Payment", {"type": "Cash", "enabled": 1}
			)
			if cash and cash not in modes:
				modes.insert(0, cash)
		self.totals = []
		for mode in modes:
			receipts, amount = taken.get(mode, (0, 0))
			if cashier._is_cash(mode):
				amount += flt(self.opening_float)
			row = self.append(
				"totals",
				{
					"mode_of_payment": mode,
					"receipts": receipts,
					"expected": amount,
					"counted": counted.get(mode),
				},
			)
			row.difference = flt(row.counted) - flt(row.expected)
		self.total_expected = sum(flt(r.expected) for r in self.totals)
		self.total_counted = sum(flt(r.counted) for r in self.totals)
		self.total_difference = self.total_counted - self.total_expected

	def before_submit(self):
		self.refresh_totals()
		self.status = "Closed"
		self.closed_at = now_datetime()
		if flt(self.total_difference) and not (self.notes or "").strip():
			frappe.throw(
				_("The count differs from the takings by {0}: explain it in Notes.").format(
					frappe.format_value(self.total_difference, {"fieldtype": "Currency"})
				)
			)

	def on_cancel(self):
		self.db_set("status", "Cancelled")
