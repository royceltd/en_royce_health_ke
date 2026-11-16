# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""The pharmacy's worklist: outpatient prescriptions and counter sales to
dispense, on Marley's Medication Requests and ERPNext's Sales Invoice and
Delivery Note.

One row per visit (or consultation, or counter sale), the drugs inside. For
each drug the pharmacist sees the payment state and the stock in the
pharmacy store, and can:

- Bill: put the visit's unbilled drugs on the patient's draft bill, for the
  Cashier (the insurer's bill takes covered drugs on its own).
- Dispense (all or part of the quantity): a Delivery Note from the pharmacy
  store, against the patient's submitted bill when there is one; batches are
  picked by expiry. Cash patients' drugs leave only once paid (the payment
  rule of visit_bill). Medicine labels print from the Delivery Note.
- Buy outside / Send back to the doctor (for a substitute): the drug is
  taken off billing; sending back also returns the patient to the
  prescriber's queue with the pharmacist's note.
- Return: drugs brought back go back into stock (a return Delivery Note);
  any refund is a credit note at the Cashier.

Counter sales (walk-ins, over the counter): the pharmacist makes a draft bill
(the patient's, or the walk-in customer's), the patient pays at the Cashier,
and the pharmacy dispenses against it.

Inpatients' drugs go through Marley's ward medication orders, not here."""

import json

import frappe
from frappe import _
from frappe.utils import add_days, flt, get_datetime, getdate, nowdate

from royce_health_ke import coverage, visit_bill
from royce_health_ke.visits import age_label, open_visit_for

MR = "Medication Request"
PHARMACIST = "Pharmacist"
WAITING, DISPENSED, BUY_OUTSIDE, SENT_BACK, PARTLY = (
	"Waiting",
	"Dispensed",
	"Buy Outside",
	"Sent Back",
	"Partly Dispensed",
)
NOT_DISPENSING = (BUY_OUTSIDE, SENT_BACK)
TABS = {"waiting": (WAITING,), "dispensed": (DISPENSED,), "other": NOT_DISPENSING, "all": None}
CLOSED_MR = (
	"draft-Medication Request Status",
	"cancelled-Medication Request Status",
	"entered-in-error-Medication Request Status",
	"stopped-Medication Request Status",
)
PAY_LABELS = {
	"paid": _("Paid"),
	"insured": _("Insured"),
	"inpatient": _("Inpatient"),
	"casualty": _("Casualty"),
	"approved": _("Credit approved"),
	"billed": _("Billed, not paid"),
	"not_billed": _("Not billed"),
	"draft": _("Bill at the Cashier"),
}
WALK_IN_CUSTOMER = "Walk-in Customer"


def _list(value):
	if not value:
		return []
	if isinstance(value, str):
		value = json.loads(value)
	return value


def default_warehouse():
	return frappe.db.get_single_value("Kenya Health Settings", "pharmacy_warehouse")


def _check_access():
	frappe.has_permission("Delivery Note", "create", throw=True)


# Lines


def _prescriptions(from_date, to_date, company=None):
	conditions = [
		"mr.docstatus = 1",
		"ifnull(mr.inpatient_record, '') = ''",
		"mr.status not in %(closed)s",
		"mr.order_date between %(from)s and %(to)s",
		"ifnull(mr.medication_item, '') != ''",
	]
	values = {"closed": CLOSED_MR, "from": from_date, "to": to_date}
	if company:
		conditions.append("mr.company = %(company)s")
		values["company"] = company
	return frappe.db.sql(
		f"""
		select mr.name, mr.patient, mr.patient_name, mr.patient_gender, mr.company,
			mr.medication, mr.medication_item, mr.quantity, mr.dosage, mr.period, mr.comment,
			mr.order_date, mr.order_time, mr.creation, mr.practitioner, mr.practitioner_name,
			mr.order_group, mr.ke_insurance_coverage, mr.ke_pharmacy_status, mr.ke_dispensed_qty,
			mr.ke_pharmacy_note, enc.ke_patient_visit as visit, i.item_name, i.stock_uom
		from `tabMedication Request` mr
		left join `tabPatient Encounter` enc on enc.name = mr.order_group
		left join `tabItem` i on i.name = mr.medication_item
		where {" and ".join(conditions)}
		""",
		values,
		as_dict=True,
	)


def _sales(from_date, to_date, company=None):
	conditions = [
		"si.ke_pharmacy_sale = 1",
		"si.docstatus < 2",
		"si.is_return = 0",
		"si.posting_date between %(from)s and %(to)s",
	]
	values = {"from": from_date, "to": to_date}
	if company:
		conditions.append("si.company = %(company)s")
		values["company"] = company
	return frappe.db.sql(
		f"""
		select si.name as invoice, si.docstatus, si.outstanding_amount, si.customer, si.customer_name,
			si.patient, si.patient_name, si.ke_walk_in_name, si.ke_patient_visit as visit, si.company,
			si.creation, si.owner, sii.name as si_detail, sii.item_code, sii.item_name, sii.qty,
			sii.delivered_qty, sii.uom, sii.ke_instructions
		from `tabSales Invoice Item` sii
		join `tabSales Invoice` si on si.name = sii.parent
		join `tabItem` i on i.name = sii.item_code and i.is_stock_item = 1
		where {" and ".join(conditions)}
		""",
		values,
		as_dict=True,
	)


def instructions(mr):
	parts = [p for p in (mr.get("dosage"), mr.get("period") and _("for {0}").format(mr.period)) if p]
	text = " ".join(parts)
	if mr.get("comment"):
		text = f"{text}. {mr.comment}" if text else mr.comment
	return text


def _lines(from_date, to_date, company=None):
	lines = []
	for m in _prescriptions(from_date, to_date, company):
		dispensed = flt(m.ke_dispensed_qty)
		remaining = max(flt(m.quantity) - dispensed, 0)
		if m.ke_pharmacy_status in NOT_DISPENSING:
			stage = m.ke_pharmacy_status
		elif remaining <= 0:
			stage = DISPENSED
		else:
			stage = WAITING
		lines.append(
			frappe._dict(
				kind="mr",
				ref=m.name,
				company=m.company,
				patient=m.patient,
				patient_name=m.patient_name,
				sex=m.patient_gender,
				drug=m.item_name or m.medication,
				item_code=m.medication_item,
				uom=m.stock_uom,
				qty=flt(m.quantity),
				dispensed=dispensed,
				remaining=remaining,
				instructions=instructions(m),
				note=m.ke_pharmacy_note,
				ordered_at=get_datetime(f"{m.order_date} {m.order_time}") if m.order_time else m.creation,
				practitioner=m.practitioner,
				practitioner_name=m.practitioner_name,
				visit=m.visit,
				encounter=m.order_group,
				cover=m.ke_insurance_coverage,
				stage=stage,
				partly=stage == WAITING and dispensed > 0,
			)
		)
	for s in _sales(from_date, to_date, company):
		remaining = max(flt(s.qty) - flt(s.delivered_qty), 0)
		lines.append(
			frappe._dict(
				kind="sale",
				ref=s.si_detail,
				invoice=s.invoice,
				invoice_status=s.docstatus,
				outstanding=flt(s.outstanding_amount),
				company=s.company,
				patient=s.patient,
				patient_name=s.patient_name or s.ke_walk_in_name or s.customer_name,
				drug=s.item_name or s.item_code,
				item_code=s.item_code,
				uom=s.uom,
				qty=flt(s.qty),
				dispensed=flt(s.delivered_qty),
				remaining=remaining,
				instructions=s.ke_instructions or "",
				ordered_at=s.creation,
				practitioner_name=_("Counter sale"),
				visit=s.visit,
				stage=DISPENSED if remaining <= 0 else WAITING,
				partly=remaining > 0 and flt(s.delivered_qty) > 0,
			)
		)
	for line in lines:
		line.key = group_key(line)
	return lines


def group_key(line):
	if line.visit:
		return f"visit:{line.visit}"
	if line.kind == "mr":
		return f"enc:{line.encounter}"
	return f"sale:{line.invoice}"


def _pay(line):
	"""(status key, blocked): blocked = may not be dispensed yet."""
	enforced = visit_bill.enforced(visit_bill.PHARMACY)
	if line.kind == "sale":
		if line.invoice_status == 0:
			return "draft", enforced
		if line.outstanding <= 0.005:
			return "paid", False
		why = line.patient and visit_bill.exemption(line.patient, line.visit)
		return (why, False) if why else ("billed", enforced)
	insured = bool(line.cover) and (not coverage.pays_uncovered() or coverage.is_covered(line.cover))
	why = visit_bill.exemption(line.patient, line.visit, None, insured)
	if why:
		return why, False
	if visit_bill.is_paid(MR, line.ref):
		return "paid", False
	billed = frappe.db.exists(
		"Sales Invoice Item", {"reference_dt": MR, "reference_dn": line.ref, "docstatus": ["<", 2]}
	)
	return ("billed" if billed else "not_billed"), enforced


def _stock(items, warehouse):
	if not (items and warehouse):
		return {}
	return dict(
		frappe.get_all(
			"Bin",
			filters={"item_code": ["in", list(items)], "warehouse": warehouse},
			fields=["item_code", "actual_qty"],
			as_list=True,
		)
	)


def _range(from_date, to_date):
	to_date = getdate(to_date or nowdate())
	return getdate(from_date or add_days(to_date, -6)), to_date


@frappe.whitelist()
def worklist(
	tab: str = "waiting",
	from_date: str | None = None,
	to_date: str | None = None,
	company: str | None = None,
	search: str | None = None,
):
	_check_access()
	if tab not in TABS:
		frappe.throw(_("Unknown tab {0}.").format(tab))
	from_date, to_date = _range(from_date, to_date)
	lines = _lines(from_date, to_date, company)
	groups = {}
	dobs = dict(
		frappe.get_all(
			"Patient",
			filters={"name": ["in", list({x.patient for x in lines if x.patient})]},
			fields=["name", "dob"],
			as_list=True,
		)
	)
	for line in lines:
		g = groups.get(line.key)
		if not g:
			g = groups[line.key] = frappe._dict(
				key=line.key,
				visit=line.visit,
				patient=line.patient,
				patient_name=line.patient_name,
				age=age_label(dobs.get(line.patient)),
				sex=line.sex,
				prescriber=line.practitioner_name,
				ordered_at=line.ordered_at,
				counter_sale=line.kind == "sale",
				drugs=[],
				counts={WAITING: 0, DISPENSED: 0, BUY_OUTSIDE: 0, SENT_BACK: 0},
				unpaid=0,
			)
		g.drugs.append(line.drug)
		g.counts[line.stage] += 1
		if get_datetime(line.ordered_at) < get_datetime(g.ordered_at):
			g.ordered_at = line.ordered_at
		if line.stage == WAITING:
			_status, blocked = _pay(line)
			g.unpaid += bool(blocked)
	stages = TABS[tab]
	rows = [g for g in groups.values() if not stages or any(g.counts[s] for s in stages)]
	if search:
		s = search.lower()
		rows = [
			g
			for g in rows
			if s in (g.patient_name or "").lower()
			or s in (g.patient or "").lower()
			or s in (g.visit or "").lower()
		]
	visits = {g.visit for g in rows if g.visit}
	methods = (
		dict(
			frappe.get_all(
				"Patient Visit",
				filters={"name": ["in", list(visits)]},
				fields=["name", "payment_method"],
				as_list=True,
			)
		)
		if visits
		else {}
	)
	for g in rows:
		g.payment_method = _(methods.get(g.visit) or "Cash")
		g.count = len(g.drugs)
	rows.sort(key=lambda g: get_datetime(g.ordered_at))
	return {
		"rows": rows,
		"tab_counts": {
			t: sum(1 for g in groups.values() if not st or any(g.counts[s] for s in st))
			for t, st in TABS.items()
		},
		"warehouse": default_warehouse(),
	}


@frappe.whitelist()
def order(key: str, from_date: str | None = None, to_date: str | None = None, warehouse: str | None = None):
	_check_access()
	from_date, to_date = _range(from_date, to_date)
	lines = [line for line in _lines(from_date, to_date) if line.key == key]
	if not lines:
		frappe.throw(_("Nothing found for this order in these dates."))
	stock = _stock({x.item_code for x in lines}, warehouse)
	out = []
	for line in sorted(lines, key=lambda x: (x.stage != WAITING, x.drug)):
		row = {
			k: line.get(k)
			for k in (
				"kind",
				"ref",
				"drug",
				"item_code",
				"uom",
				"qty",
				"dispensed",
				"remaining",
				"instructions",
				"note",
				"stage",
				"partly",
				"invoice",
				"encounter",
			)
		}
		row["available"] = stock.get(line.item_code, 0) if warehouse else None
		row["returnable"] = _returnable(line) if line.dispensed > 0 else 0
		if line.stage == WAITING:
			status, blocked = _pay(line)
			row.update(pay=status, pay_label=PAY_LABELS.get(status, _(status)), blocked=blocked)
		out.append(row)
	first = lines[0]
	encounters = sorted({x.encounter for x in lines if x.get("encounter")})
	return {
		"key": key,
		"patient": first.patient,
		"patient_name": first.patient_name,
		"sex": first.sex,
		"visit": first.visit,
		"encounters": encounters,
		"lines": out,
		"can_bill": bool(first.visit) and any(r.get("pay") == "not_billed" for r in out),
	}


def _returnable(line):
	field = "ke_medication_request" if line.kind == "mr" else "si_detail"
	rows = frappe.db.sql(
		f"""select sum(dni.stock_qty - (select ifnull(sum(-r.stock_qty), 0) from `tabDelivery Note Item` r
				join `tabDelivery Note` rn on rn.name = r.parent
				where rn.docstatus = 1 and rn.is_return = 1 and r.dn_detail = dni.name))
		from `tabDelivery Note Item` dni join `tabDelivery Note` dn on dn.name = dni.parent
		where dn.docstatus = 1 and dn.is_return = 0 and dni.{field} = %s""",
		line.ref,
	)
	return flt(rows[0][0]) if rows else 0


# Dispensing


def _sales_item_for(mr):
	return frappe.db.get_value(
		"Sales Invoice Item",
		{"reference_dt": MR, "reference_dn": mr, "docstatus": 1},
		["name", "parent", "rate", "uom", "conversion_factor"],
		as_dict=True,
	)


@frappe.whitelist()
def dispense(lines: str | list, warehouse: str):
	"""Delivery Notes (one per patient) for these lines: [{kind, ref, qty,
	instructions}], qty in the line's unit. Returns the Delivery Notes."""
	_check_access()
	if not warehouse:
		frappe.throw(_("Choose the pharmacy store the drugs leave from."))
	notes = {}
	for entry in _list(lines):
		qty = flt(entry.get("qty"))
		if qty <= 0:
			continue
		kind, ref = entry.get("kind"), entry.get("ref")
		if kind == "mr":
			row, head = _mr_row(ref, qty)
		elif kind == "sale":
			row, head = _sale_row(ref, qty)
		else:
			frappe.throw(_("Unknown line."))
		row["warehouse"] = warehouse
		if entry.get("instructions") is not None:
			row["ke_instructions"] = entry.get("instructions")
		notes.setdefault(head, []).append(row)
	if not notes:
		frappe.throw(_("Enter the quantity to dispense."))
	made = []
	for (company, customer, patient, visit, walk_in), rows in notes.items():
		dn = frappe.new_doc("Delivery Note")
		dn.update(
			{
				"company": company,
				"customer": customer,
				"posting_date": nowdate(),
				"set_warehouse": warehouse,
				"ke_patient": patient,
				"ke_patient_visit": visit,
				"ke_walk_in_name": walk_in,
			}
		)
		for row in rows:
			dn.append("items", row)
		dn.set_missing_values()
		dn.insert()
		dn.submit()
		made.append(dn.name)
	return made


def _mr_row(ref, qty):
	m = frappe.db.get_value(
		MR,
		ref,
		[
			"name",
			"patient",
			"company",
			"medication",
			"medication_item",
			"quantity",
			"dosage",
			"period",
			"comment",
			"order_group",
			"inpatient_record",
			"ke_insurance_coverage",
			"ke_pharmacy_status",
			"ke_dispensed_qty",
			"docstatus",
		],
		as_dict=True,
	)
	if not m or m.docstatus != 1 or m.inpatient_record:
		frappe.throw(_("{0} is not an outpatient prescription.").format(ref))
	if m.ke_pharmacy_status in NOT_DISPENSING:
		frappe.throw(_("{0} is marked {1}.").format(m.medication, _(m.ke_pharmacy_status)))
	if qty > flt(m.quantity) - flt(m.ke_dispensed_qty) + 1e-9:
		frappe.throw(
			_("{0}: only {1} left to dispense.").format(
				m.medication, flt(m.quantity) - flt(m.ke_dispensed_qty)
			)
		)
	visit = m.order_group and frappe.db.get_value("Patient Encounter", m.order_group, "ke_patient_visit")
	line = frappe._dict(kind="mr", ref=ref, patient=m.patient, visit=visit, cover=m.ke_insurance_coverage)
	status, blocked = _pay(line)
	if blocked:
		frappe.throw(
			_("{0} is {1}. Drugs leave the store only when paid.").format(
				m.medication, PAY_LABELS[status].lower()
			),
			title=_("Payment required"),
		)
	customer = frappe.db.get_value("Patient", m.patient, "customer")
	if not customer:
		frappe.throw(_("Link a customer to patient {0} first.").format(m.patient))
	row = {
		"item_code": m.medication_item,
		"qty": qty,
		"ke_medication_request": ref,
		"ke_instructions": instructions(m),
	}
	sii = _sales_item_for(ref)
	if sii:
		cf = flt(sii.conversion_factor) or 1
		row.update(
			against_sales_invoice=sii.parent,
			si_detail=sii.name,
			rate=sii.rate,
			uom=sii.uom,
			conversion_factor=cf,
			qty=qty / cf,
		)
	return row, (m.company, customer, m.patient, visit, None)


def _sale_row(ref, qty):
	s = frappe.db.get_value(
		"Sales Invoice Item",
		ref,
		[
			"name",
			"parent",
			"item_code",
			"item_name",
			"qty",
			"delivered_qty",
			"rate",
			"uom",
			"conversion_factor",
			"ke_instructions",
		],
		as_dict=True,
	)
	if not s:
		frappe.throw(_("Unknown sale line {0}.").format(ref))
	si = frappe.db.get_value(
		"Sales Invoice",
		s.parent,
		[
			"docstatus",
			"outstanding_amount",
			"customer",
			"patient",
			"company",
			"ke_patient_visit",
			"ke_walk_in_name",
		],
		as_dict=True,
	)
	if si.docstatus != 1:
		frappe.throw(
			_("{0}: the bill {1} is not submitted at the Cashier yet.").format(s.item_name, s.parent)
		)
	line = frappe._dict(
		kind="sale",
		invoice_status=1,
		outstanding=flt(si.outstanding_amount),
		patient=si.patient,
		visit=si.ke_patient_visit,
	)
	_status, blocked = _pay(line)
	if blocked:
		frappe.throw(
			_("{0}: bill {1} is not paid. Drugs leave the store only when paid.").format(
				s.item_name, s.parent
			),
			title=_("Payment required"),
		)
	if qty > flt(s.qty) - flt(s.delivered_qty) + 1e-9:
		frappe.throw(
			_("{0}: only {1} left to dispense.").format(s.item_name, flt(s.qty) - flt(s.delivered_qty))
		)
	row = {
		"item_code": s.item_code,
		"qty": qty,
		"uom": s.uom,
		"conversion_factor": s.conversion_factor,
		"rate": s.rate,
		"against_sales_invoice": s.parent,
		"si_detail": s.name,
		"ke_instructions": s.ke_instructions,
	}
	return row, (si.company, si.customer, si.patient, si.ke_patient_visit, si.ke_walk_in_name)


def delivery_changed(doc, method=None):
	"""Delivery Note on_submit / on_cancel: the prescriptions' dispensed quantity."""
	for mr in {row.get("ke_medication_request") for row in doc.items if row.get("ke_medication_request")}:
		refresh_dispensed(mr)


def invoice_changed(doc, method=None):
	"""Sales Invoice on_submit / on_cancel: a bill with Update Stock issues the
	drugs itself (the way before the worklist, and still allowed)."""
	if not doc.get("update_stock"):
		return
	for mr in {r.reference_dn for r in doc.items if r.get("reference_dt") == MR and r.get("reference_dn")}:
		refresh_dispensed(mr)


def refresh_dispensed(mr):
	"""Delivered on Delivery Notes, or on bills with Update Stock (returns
	count negative on both)."""
	total = flt(
		frappe.db.sql(
			"""select sum(dni.stock_qty) from `tabDelivery Note Item` dni
			join `tabDelivery Note` dn on dn.name = dni.parent
			where dn.docstatus = 1 and dni.ke_medication_request = %s""",
			mr,
		)[0][0]
	) + flt(
		frappe.db.sql(
			"""select sum(sii.stock_qty) from `tabSales Invoice Item` sii
			join `tabSales Invoice` si on si.name = sii.parent
			where si.docstatus = 1 and si.update_stock = 1
				and sii.reference_dt = 'Medication Request' and sii.reference_dn = %s""",
			mr,
		)[0][0]
	)
	quantity, status = frappe.db.get_value(MR, mr, ["quantity", "ke_pharmacy_status"])
	if status not in NOT_DISPENSING:
		status = DISPENSED if total >= flt(quantity) - 1e-9 else (PARTLY if total > 0 else "")
	frappe.db.set_value(
		MR, mr, {"ke_dispensed_qty": total, "ke_pharmacy_status": status}, update_modified=False
	)


@frappe.whitelist()
def return_lines(lines: str | list):
	"""Drugs brought back: [{kind, ref, qty}] in stock units, from the latest
	Delivery Notes first. Returns the return Delivery Notes."""
	from erpnext.stock.doctype.delivery_note.delivery_note import make_sales_return

	_check_access()
	wanted = {}  # delivery note -> {dn item: qty in its unit}
	for entry in _list(lines):
		left = flt(entry.get("qty"))
		if left <= 0:
			continue
		field = "ke_medication_request" if entry.get("kind") == "mr" else "si_detail"
		rows = frappe.db.sql(
			f"""select dni.name, dni.parent, dni.stock_qty, (select ifnull(sum(-r.stock_qty), 0) from `tabDelivery Note Item` r
				join `tabDelivery Note` rn on rn.name = r.parent
				where rn.docstatus = 1 and rn.is_return = 1 and r.dn_detail = dni.name) as returned_stock_qty,
				dni.conversion_factor
			from `tabDelivery Note Item` dni join `tabDelivery Note` dn on dn.name = dni.parent
			where dn.docstatus = 1 and dn.is_return = 0 and dni.{field} = %s
			order by dn.posting_date desc, dn.creation desc""",
			entry.get("ref"),
			as_dict=True,
		)
		for r in rows:
			cf = flt(r.conversion_factor) or 1
			can = flt(r.stock_qty) - flt(r.returned_stock_qty)
			take = min(can, left)
			if take <= 0:
				continue
			wanted.setdefault(r.parent, {})[r.name] = take / cf
			left -= take
			if left <= 1e-9:
				break
		if left > 1e-9:
			frappe.throw(_("More is being returned than was dispensed."))
	made = []
	for dn_name, items in wanted.items():
		ret = make_sales_return(dn_name)
		ret.items = [row for row in ret.items if row.dn_detail in items]
		for row in ret.items:
			row.qty = -flt(items[row.dn_detail])
			row.stock_qty = row.qty * (flt(row.conversion_factor) or 1)
		ret.insert()
		ret.submit()
		made.append(ret.name)
	return made


# Billing, buying outside, sending back


@frappe.whitelist()
def bill_drugs(visit: str):
	"""The visit's unbilled drugs on the patient's draft bill for the Cashier
	(added to the visit's existing draft, if there is one)."""
	_check_access()
	doc = frappe.get_doc("Patient Visit", visit)
	split = visit_bill.splits(doc)
	drafted = visit_bill.on_drafts(visit)
	lines = [
		line
		for line in visit_bill.unbilled_lines(doc)
		if line["dt"] == MR and (line["dt"], line["dn"]) not in drafted
	]
	if split:
		lines = [line for line in lines if not visit_bill._covered(line)]
	if not lines:
		frappe.throw(_("No drugs on this visit are waiting to be billed."))
	bill_for = "Patient" if split else None
	draft = visit_bill._draft(visit, bill_for)
	if draft:
		si = frappe.get_doc("Sales Invoice", draft)
		si.set_healthcare_services(lines)
	else:
		if not frappe.db.get_value("Patient", doc.patient, "customer"):
			frappe.throw(_("Link a customer to patient {0} first.").format(doc.patient_name))
		si = visit_bill._invoice(doc, lines, bill_for)
	si.flags.ignore_permissions = True
	si.save()
	visit_bill.refresh_bill_status(visit)
	return si.name


def _mark(refs, status, note=None):
	done = []
	for ref in _list(refs):
		m = frappe.db.get_value(
			MR, ref, ["medication", "ke_dispensed_qty", "ke_pharmacy_status", "docstatus"], as_dict=True
		)
		if not m or m.docstatus != 1:
			continue
		if status and frappe.db.exists(
			"Sales Invoice Item", {"reference_dt": MR, "reference_dn": ref, "docstatus": ["<", 2]}
		):
			frappe.throw(
				_(
					"{0} is already on a bill. The Cashier removes it from the bill (or credits it) first."
				).format(m.medication),
				title=_("Already billed"),
			)
		if status and flt(m.ke_dispensed_qty) > 0:
			frappe.throw(_("{0} has already been dispensed.").format(m.medication))
		frappe.db.set_value(
			MR, ref, {"ke_pharmacy_status": status, "ke_pharmacy_note": note}, update_modified=False
		)
		if not status:
			refresh_dispensed(ref)
		done.append(ref)
	return done


@frappe.whitelist()
def buy_outside(requests: str | list, reason: str | None = None):
	"""The patient buys these drugs elsewhere: not billed, not dispensed."""
	_check_access()
	return _mark(requests, BUY_OUTSIDE, reason)


@frappe.whitelist()
def back_to_waiting(requests: str | list):
	_check_access()
	return _mark(requests, "")


@frappe.whitelist()
def send_back(requests: str | list, note: str):
	"""Back to the prescriber to change the prescription (a substitute): the
	drugs come off billing and the patient returns to the doctor's queue."""
	_check_access()
	if not note:
		frappe.throw(_("Say what the doctor should change."))
	done = _mark(requests, SENT_BACK, note)
	visits = {}
	for ref in done:
		m = frappe.db.get_value(MR, ref, ["order_group", "practitioner", "medication"], as_dict=True)
		visit = m.order_group and frappe.db.get_value("Patient Encounter", m.order_group, "ke_patient_visit")
		if visit:
			visits.setdefault(visit, (m.practitioner, []))[1].append(m.medication)
	from royce_health_ke.visits import _move

	for visit, (practitioner, drugs) in visits.items():
		v = frappe.get_doc("Patient Visit", visit)
		if v.status != "Open":
			continue
		_move(
			v,
			v.current_station,
			"Consultation",
			practitioner,
			_("Pharmacy: {0} ({1})").format(note, ", ".join(drugs)),
			v.consultation_room,
		)
		v.practitioner = practitioner or v.practitioner
		v.flags.ignore_permissions = True
		v.save()
	return done


# Substitution lock (outpatient feedback, 16 Nov 2026): the drug the clinician
# prescribed is the drug billed and dispensed. Nobody changes it on the bill or
# the delivery, prescribers included: the prescriber changes the prescription
# itself, so prescription, bill and dispensing record always agree. The
# pharmacist's route is Send back to the doctor.


def _prescribed(rows):
	"""[(row, medication request)] for the rows that carry a prescription."""
	out = []
	for row in rows:
		ref = row.get("ke_medication_request")
		if not ref and row.get("reference_dt") == MR:
			ref = row.get("reference_dn")
		if not ref and row.get("si_detail"):
			r = frappe.db.get_value("Sales Invoice Item", row.si_detail, ["reference_dt", "reference_dn"])
			ref = r and r[0] == MR and r[1]
		if ref:
			out.append((row, ref))
	return out


def lock_substitution(doc, method=None):
	"""Sales Invoice / Delivery Note validate: a prescribed drug can't be swapped."""
	if doc.get("is_return"):
		return
	for row, ref in _prescribed(doc.get("items") or []):
		m = frappe.db.get_value(MR, ref, ["medication_item", "medication", "practitioner_name"], as_dict=True)
		if not m or not m.medication_item or row.item_code == m.medication_item:
			continue
		frappe.throw(
			_(
				"Row {0}: {1} was prescribed{2}, not {3}. A prescribed medicine is not changed on the bill or "
				"at dispensing: to give a different one (e.g. out of stock), use Send back to the doctor "
				"on the Pharmacy Worklist, and the doctor changes the prescription."
			).format(
				row.idx,
				frappe.bold(m.medication or m.medication_item),
				_(" by {0}").format(m.practitioner_name) if m.practitioner_name else "",
				frappe.bold(row.item_code),
			),
			title=_("Prescribed medicine can't be substituted"),
		)


# Counter sales


def walk_in_customer():
	name = frappe.db.get_single_value("Kenya Health Settings", "pharmacy_walk_in_customer")
	if name:
		return name
	if frappe.db.exists("Customer", WALK_IN_CUSTOMER):
		return WALK_IN_CUSTOMER
	customer = frappe.get_doc(
		{"doctype": "Customer", "customer_name": WALK_IN_CUSTOMER, "customer_type": "Individual"}
	)
	customer.insert(ignore_permissions=True)
	return customer.name


@frappe.whitelist()
def counter_sale(
	items: str | list,
	patient: str | None = None,
	walk_in_name: str | None = None,
	discount_percentage: float | None = None,
	company: str | None = None,
):
	"""A draft bill for over-the-counter drugs, for the Cashier; dispensed
	from the worklist once paid. A registered patient's bill goes on their
	visit today (a new Pharmacy only visit if they have none)."""
	_check_access()
	items = [i for i in _list(items) if i.get("item_code") and flt(i.get("qty")) > 0]
	if not items:
		frappe.throw(_("Add the drugs and their quantities."))
	company = (
		company
		or frappe.defaults.get_user_default("Company")
		or frappe.db.get_single_value("Global Defaults", "default_company")
	)
	visit = None
	if patient:
		customer = frappe.db.get_value("Patient", patient, "customer")
		if not customer:
			frappe.throw(_("Link a customer to patient {0} first.").format(patient))
		visit = open_visit_for(patient)
		if not visit:
			v = frappe.get_doc(
				{
					"doctype": "Patient Visit",
					"patient": patient,
					"company": company,
					"visit_type": "Pharmacy only",
					"payment_method": "Cash",
				}
			)
			v.insert(ignore_permissions=True)
			visit = v.name
	else:
		customer = walk_in_customer()
	si = frappe.new_doc("Sales Invoice")
	si.update(
		{
			"customer": customer,
			"patient": patient,
			"company": company,
			"posting_date": nowdate(),
			"due_date": nowdate(),
			"ke_patient_visit": visit,
			"ke_pharmacy_sale": 1,
			"ke_walk_in_name": None if patient else walk_in_name,
			"additional_discount_percentage": flt(discount_percentage),
		}
	)
	for i in items:
		si.append(
			"items",
			{"item_code": i["item_code"], "qty": flt(i["qty"]), "ke_instructions": i.get("instructions")},
		)
	si.set_missing_values()
	si.flags.ignore_permissions = True
	si.insert()
	if visit:
		visit_bill.refresh_bill_status(visit)
	return {
		"invoice": si.name,
		"key": f"visit:{visit}" if visit else f"sale:{si.name}",
		"total": si.grand_total,
	}


# Labels


def health_medicine_labels(doc):
	"""Jinja: one label per dispensed drug on a Delivery Note."""
	patient = (
		frappe.db.get_value("Patient", doc.get("ke_patient"), "patient_name")
		if doc.get("ke_patient")
		else None
	)
	who = patient or doc.get("ke_walk_in_name") or doc.customer_name
	labels = []
	for row in doc.items:
		batches = []
		if row.get("serial_and_batch_bundle"):
			batches = frappe.get_all(
				"Serial and Batch Entry",
				filters={"parent": row.serial_and_batch_bundle},
				pluck="batch_no",
			)
		elif row.get("batch_no"):
			batches = [row.batch_no]
		expiry = [
			frappe.utils.formatdate(e, "MMM yyyy")
			for e in frappe.get_all("Batch", filters={"name": ["in", batches or [""]]}, pluck="expiry_date")
			if e
		]
		labels.append(
			frappe._dict(
				patient=who,
				drug=row.item_name or row.item_code,
				qty=f"{flt(row.qty):g} {row.uom or ''}".strip(),
				instructions=row.get("ke_instructions") or "",
				batch=", ".join(b for b in batches if b),
				expiry=", ".join(expiry),
			)
		)
	return labels
