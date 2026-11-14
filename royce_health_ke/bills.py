# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Patient Bills: one row per visit with what was billed, paid, discounted,
covered by insurance and still owed, for the Cashier and the accounts office.
Cash and insurance visits on their own tabs (the hospital's "non-credit" and
"credit" bills), with the approvals waiting for a manager."""

import frappe
from frappe import _
from frappe.utils import add_days, flt, getdate, nowdate

from royce_health_ke.approvals import is_manager

READERS = ("Cashier", "Accounts User", "Accounts Manager", "Healthcare Administrator", "System Manager")


@frappe.whitelist()
def board(
	payment_method: str = "Cash",
	from_date: str | None = None,
	to_date: str | None = None,
	balance: str | None = None,
	search: str | None = None,
	company: str | None = None,
):
	if not set(READERS) & set(frappe.get_roles()):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	to_date = getdate(to_date or nowdate())
	from_date = getdate(from_date or add_days(to_date, -6))
	filters = {"visit_date": ["between", [from_date, to_date]], "status": ["!=", "Cancelled"]}
	if payment_method in ("Cash", "Insurance"):
		filters["payment_method"] = payment_method
	if company:
		filters["company"] = company
	visits = frappe.get_all(
		"Patient Visit",
		filters=filters,
		fields=[
			"name",
			"visit_date",
			"patient",
			"patient_name",
			"visit_type",
			"payment_method",
			"insurance_payor",
			"status",
			"bill_status",
			"allow_credit",
			"current_station",
		],
		order_by="visit_date desc, creation desc",
		limit=1000,
	)
	if search:
		s = search.lower()
		visits = [
			v
			for v in visits
			if s in (v.patient_name or "").lower() or s in v.name.lower() or s in (v.patient or "").lower()
		]
	names = [v.name for v in visits]
	money = {}
	pending = {}
	if names:
		for r in frappe.db.sql(
			"""select ke_patient_visit as visit,
				sum(case when docstatus = 1 then grand_total else 0 end) as billed,
				sum(case when docstatus = 1 then outstanding_amount else 0 end) as balance,
				sum(case when docstatus = 1 then ifnull(total_insurance_coverage_amount, 0) else 0 end) as insurance,
				sum(case when docstatus = 1 then ifnull(discount_amount, 0) else 0 end) as discount,
				sum(case when docstatus = 0 then grand_total else 0 end) as draft
			from `tabSales Invoice` where ke_patient_visit in %(v)s and docstatus < 2
			group by ke_patient_visit""",
			{"v": tuple(names)},
			as_dict=True,
		):
			money[r.visit] = r
		pending = dict(
			frappe.db.sql(
				"""select patient_visit, count(*) from `tabBill Approval Request`
				where patient_visit in %(v)s and status = 'Pending' group by patient_visit""",
				{"v": tuple(names)},
			)
		)
		# Waivers written off reduce the balance but aren't payments.
		waived = dict(
			frappe.db.sql(
				"""select bar.patient_visit, sum(bar.amount) from `tabBill Approval Request` bar
				where bar.patient_visit in %(v)s and bar.request_type = 'Waiver' and bar.status = 'Approved'
				group by bar.patient_visit""",
				{"v": tuple(names)},
			)
		)
	rows = []
	for v in visits:
		m = money.get(v.name) or frappe._dict()
		billed, balance_amt, insurance = flt(m.billed), flt(m.balance), flt(m.insurance)
		waiver = flt(waived.get(v.name)) if names else 0
		row = {
			**v,
			"billed": billed,
			"insurance": insurance,
			"discount": flt(m.discount) + waiver,
			"paid": billed - insurance - balance_amt - waiver,
			"balance": balance_amt,
			"draft": flt(m.draft),
			"pending_approvals": pending.get(v.name, 0),
		}
		if balance == "Has balance" and not (
			row["balance"] > 0.005 or row["draft"] > 0 or v.bill_status == "To Bill"
		):
			continue
		if balance == "Cleared" and (
			row["balance"] > 0.005 or row["draft"] > 0 or v.bill_status == "To Bill"
		):
			continue
		rows.append(row)
	totals = {
		k: sum(r[k] for r in rows) for k in ("billed", "insurance", "discount", "paid", "balance", "draft")
	}
	return {
		"rows": rows,
		"totals": totals,
		"approvals_waiting": frappe.db.count("Bill Approval Request", {"status": "Pending"}),
		"is_manager": is_manager(),
	}
