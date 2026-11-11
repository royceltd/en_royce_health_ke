# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""The post-operative Treatment Sheet: drug orders written in theatre (the
hospital's paper treatment sheet). Regular drugs every N hours for N days,
PRN drugs, and once-only doses. Submitting the sheet makes the ward's Marley
Inpatient Medication Order with every scheduled dose, so the ward gives,
issues and bills them as for any inpatient order. PRN drugs are on the sheet
for the ward but not scheduled."""

import frappe
from frappe import _
from frappe.utils import add_to_date, cint, flt, get_datetime, getdate, now_datetime

MAX_DOSES = 200  # per drug: a guard against a mistyped interval


def dosage_form_of(item):
	"""From the Marley Medication the drug item is linked to."""
	medication = frappe.db.get_value("Medication Linked Item", {"item": item}, "parent")
	return medication and frappe.db.get_value("Medication", medication, "dosage_form")


def validate(doc):
	for row in [*doc.drugs, *doc.once_only]:
		if row.drug and not row.dosage_form:
			row.dosage_form = dosage_form_of(row.drug)
		if doc.inpatient_record and not row.dosage_form:
			frappe.throw(
				_("Row {0} ({1}): choose the dosage form (tablet, injection...).").format(
					row.idx, row.drug_name or row.drug
				)
			)
	if not (doc.drugs or doc.once_only):
		frappe.throw(_("Add at least one drug."))
	if (
		doc.inpatient_record
		and frappe.db.get_value("Inpatient Record", doc.inpatient_record, "patient") != doc.patient
	):
		frappe.throw(_("Inpatient Record {0} is not this patient's.").format(doc.inpatient_record))
	for row in doc.drugs:
		if flt(row.qty_per_dose) <= 0:
			row.qty_per_dose = 1
		if row.prn:
			continue
		if not cint(row.every_hours) or not 1 <= cint(row.every_hours) <= 72:
			frappe.throw(
				_("Row {0} ({1}): give how often (every 1 to 72 hours), or tick PRN.").format(
					row.idx, row.drug_name or row.drug
				)
			)
		row.duration_days = max(cint(row.duration_days), 1)
		if len(dose_times(row, get_datetime(doc.written_at or now_datetime()))) > MAX_DOSES:
			frappe.throw(
				_("Row {0}: more than {1} doses. Check the interval and days.").format(row.idx, MAX_DOSES)
			)
	for row in doc.once_only:
		if flt(row.qty_per_dose) <= 0:
			row.qty_per_dose = 1


def dose_times(row, default_start):
	"""Every dose of a regular drug: from its first dose, every N hours, for
	N days."""
	if row.get("prn") or not cint(row.get("every_hours")):
		return []
	start = get_datetime(row.get("first_dose_at") or default_start).replace(second=0, microsecond=0)
	end = add_to_date(start, days=max(cint(row.get("duration_days")), 1))
	times, t = [], start
	while t < end and len(times) <= MAX_DOSES:
		times.append(t)
		t = add_to_date(t, hours=cint(row.every_hours))
	return times


def frequency(row):
	if row.get("prn"):
		return _("PRN") + (
			_(" (max every {0} h)").format(row.every_hours) if cint(row.get("every_hours")) else ""
		)
	return _("Every {0} h").format(row.every_hours)


def before_submit(doc):
	signed = get_datetime(doc.written_at or now_datetime()).replace(second=0, microsecond=0)
	for row in doc.drugs:
		if not row.prn and not row.first_dose_at:
			row.first_dose_at = signed
	for row in doc.once_only:
		row.give_at = row.give_at or signed


def on_submit(doc):
	if not doc.inpatient_record:
		frappe.msgprint(
			_("No admission on this sheet: it is kept as a record, and no ward medication order is made."),
			indicator="orange",
			alert=True,
		)
		return
	order = medication_order(doc)
	if order:
		doc.db_set("medication_order", order.name)
		frappe.msgprint(
			_("Ward medication order {0}: {1} doses scheduled.").format(
				frappe.utils.get_link_to_form("Inpatient Medication Order", order.name),
				len(order.medication_orders),
			),
			alert=True,
			indicator="green",
		)


def _instructions(row):
	text = f"{row.dose} {row.route}"
	if row.get("instructions"):
		text += f" - {row.instructions}"
	return text


def medication_order(doc):
	entries = []
	for row in doc.drugs:
		for t in dose_times(row, doc.written_at):
			entries.append((row, t))
	for row in doc.once_only:
		entries.append((row, get_datetime(row.give_at).replace(second=0, microsecond=0)))
	if not entries:
		return None
	entries.sort(key=lambda e: e[1])
	order = frappe.new_doc("Inpatient Medication Order")
	order.update(
		{
			"patient": doc.patient,
			"inpatient_record": doc.inpatient_record,
			"practitioner": doc.practitioner,
			"company": doc.company,
			"start_date": getdate(entries[0][1]),
			"end_date": getdate(entries[-1][1]),
		}
	)
	for row, t in entries:
		order.append(
			"medication_orders",
			{
				"drug": row.drug,
				"drug_name": row.drug_name,
				"dosage": row.qty_per_dose,
				"dosage_form": row.dosage_form,
				"date": getdate(t),
				"time": t.strftime("%H:%M:%S"),
				"instructions": _instructions(row),
			},
		)
	order.flags.ignore_permissions = True
	order.insert()
	order.submit()
	return order


def on_cancel(doc):
	if not doc.medication_order:
		return
	order = frappe.get_doc("Inpatient Medication Order", doc.medication_order)
	if order.docstatus != 1:
		return
	started = [e for e in order.medication_orders if e.is_completed or e.status not in (None, "", "Pending")]
	if started:
		frappe.throw(
			_(
				"The ward has already handled {0} dose(s) of order {1}. Stop the remaining doses on the order instead of cancelling the sheet."
			).format(len(started), doc.medication_order)
		)
	order.flags.ignore_permissions = True
	order.flags.ignore_links = True
	order.cancel()


def sheet_details(doc):
	"""For the print: each drug with its frequency and the times given."""
	given = {}
	if doc.get("medication_order"):
		for e in frappe.get_all(
			"Inpatient Medication Order Entry",
			filters={"parent": doc.medication_order},
			fields=["drug", "date", "time", "status", "is_completed", "modified_by", "modified"],
			order_by="date, time",
		):
			given.setdefault(e.drug, []).append(e)
	return frappe._dict(
		drugs=[
			frappe._dict(row=r, frequency=frequency(r), doses=len(dose_times(r, doc.written_at)))
			for r in doc.drugs
		],
		given=given,
	)
