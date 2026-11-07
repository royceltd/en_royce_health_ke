# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Kitchen: diet orders for admitted patients, the ward diet list the
kitchen cooks from, and meal charges on inpatient bills.

- A Diet Order belongs to an admission. Submitting a new one ends the
  earlier open order on the new one's start date; on a day two orders
  overlap, the later one counts (for the kitchen and for billing).
- Meal billing (Kenya Health Settings): Included in bed charge (nothing is
  added), Per day (one charge per day on a diet), or Per meal (meals per day
  x days). Nil by mouth days are free.
- An inpatient bill (an invoice with a ward line) gets one meal line per run
  of days on the same diet, from admission to discharge or the invoice date,
  skipping days already on a submitted invoice - so interim and final bills
  never charge a day twice, and cancelling a bill frees its days again."""

import frappe
from frappe import _
from frappe.utils import add_days, getdate

INCLUDED = "Included in bed charge"
PER_DAY = "Per day"
PER_MEAL = "Per meal"
ADMITTED = ("Admitted", "Discharge Scheduled")


def validate_diet_order(doc):
	ip = frappe.db.get_value(
		"Inpatient Record",
		doc.inpatient_record,
		["status", "admitted_datetime", "discharge_datetime"],
		as_dict=True,
	)
	if doc.is_new() and ip.status not in ADMITTED:
		frappe.throw(
			_("{0} is {1}: diet orders are for admitted patients.").format(doc.inpatient_record, ip.status)
		)
	if ip.admitted_datetime and getdate(doc.start_date) < getdate(ip.admitted_datetime):
		frappe.throw(
			_("The diet can't start before the admission ({0}).").format(
				frappe.format(ip.admitted_datetime, "Datetime")
			)
		)
	if doc.end_date and getdate(doc.end_date) < getdate(doc.start_date):
		frappe.throw(_("The diet can't end before it starts."))
	if frappe.db.get_value("Diet Type", doc.diet_type, "nil_by_mouth"):
		doc.meals_per_day = 0
	elif not doc.meals_per_day or doc.meals_per_day < 1:
		frappe.throw(_("Meals per day must be at least 1 (use a nil by mouth diet for none)."))


def on_submit_diet_order(doc):
	"""End the admission's earlier open orders on this one's start date."""
	for other in frappe.get_all(
		"Diet Order",
		filters={
			"inpatient_record": doc.inpatient_record,
			"docstatus": 1,
			"name": ["!=", doc.name],
			"start_date": ["<=", doc.start_date],
		},
		fields=["name", "end_date"],
	):
		if not other.end_date or getdate(other.end_date) > getdate(doc.start_date):
			frappe.db.set_value("Diet Order", other.name, "end_date", doc.start_date)


def orders_of(inpatient_records):
	return frappe.get_all(
		"Diet Order",
		filters={"inpatient_record": ["in", list(inpatient_records) or [""]], "docstatus": 1},
		fields=[
			"name",
			"inpatient_record",
			"patient",
			"patient_name",
			"diet_type",
			"start_date",
			"end_date",
			"meals_per_day",
			"instructions",
			"allergies",
			"creation",
		],
		order_by="start_date asc, creation asc",
	)


def active_order(orders, day):
	"""The order that counts on `day`: the latest started one still running."""
	day = getdate(day)
	current = None
	for o in orders:
		if getdate(o.start_date) <= day and (not o.end_date or getdate(o.end_date) >= day):
			current = o
	return current


# ---------------------------------------------------------------- billing


def meal_billing():
	return frappe.db.get_single_value("Kenya Health Settings", "meal_billing") or INCLUDED


def apply_meal_charges(doc, method=None):
	"""Sales Invoice before_validate: meal lines on inpatient bills."""
	if doc.docstatus != 0 or doc.get("is_return") or not doc.get("patient"):
		return
	mode = meal_billing()
	# recompute on every save: drop the lines added last time
	doc.items = [r for r in doc.items if not r.get("ke_diet_order")]
	for i, row in enumerate(doc.items, 1):
		row.idx = i
	if mode == INCLUDED:
		return
	stays = {
		frappe.db.get_value("Inpatient Occupancy", r.reference_dn, "parent")
		for r in doc.items
		if r.get("reference_dt") == "Inpatient Occupancy" and r.get("reference_dn")
	}
	stays.discard(None)
	if not stays:
		return
	from royce_health_ke.billing import add_invoice_line

	for run in unbilled_runs(stays, doc.posting_date, exclude_invoice=doc.name):
		item = frappe.db.get_value("Diet Type", run.order.diet_type, "item") or frappe.db.get_single_value(
			"Kenya Health Settings", "meal_item"
		)
		if not item:
			frappe.throw(
				_("Set a Meal Charge Item in Kenya Health Settings (or on Diet Type {0}).").format(
					run.order.diet_type
				)
			)
		qty = run.days * (run.order.meals_per_day if mode == PER_MEAL else 1)
		add_invoice_line(
			doc,
			item,
			qty,
			description=_("Meals: {0} diet, {1} to {2}").format(
				run.order.diet_type, frappe.format(run.start, "Date"), frappe.format(run.end, "Date")
			),
			ke_diet_order=run.order.name,
			ke_meal_from=run.start,
			ke_meal_to=run.end,
		)


def unbilled_runs(inpatient_records, until, exclude_invoice=None):
	"""Runs of consecutive unbilled days on the same (not nil by mouth) diet,
	from admission to discharge or `until`, whichever is first."""
	until = getdate(until)
	orders = orders_of(inpatient_records)
	billed = billed_days([o.name for o in orders], exclude_invoice)
	nbm = set(frappe.get_all("Diet Type", filters={"nil_by_mouth": 1}, pluck="name"))
	runs = []
	for ip in frappe.get_all(
		"Inpatient Record",
		filters={"name": ["in", list(inpatient_records)]},
		fields=["name", "admitted_datetime", "discharge_datetime"],
	):
		if not ip.admitted_datetime:
			continue
		mine = [o for o in orders if o.inpatient_record == ip.name]
		day = getdate(ip.admitted_datetime)
		last = min(getdate(ip.discharge_datetime), until) if ip.discharge_datetime else until
		run = None
		while day <= last:
			order = active_order(mine, day)
			if order and order.diet_type not in nbm and (order.name, day) not in billed:
				if run and run.order.name == order.name and add_days(run.end, 1) == day:
					run.end = day
					run.days += 1
				else:
					run = frappe._dict(order=order, start=day, end=day, days=1)
					runs.append(run)
			else:
				run = None
			day = add_days(day, 1)
	return runs


def billed_days(order_names, exclude_invoice=None):
	"""(order, date) pairs already on a submitted invoice."""
	days = set()
	if not order_names:
		return days
	for line in frappe.get_all(
		"Sales Invoice Item",
		filters={
			"ke_diet_order": ["in", order_names],
			"docstatus": 1,
			"parent": ["!=", exclude_invoice or ""],
		},
		fields=["ke_diet_order", "ke_meal_from", "ke_meal_to", "qty"],
	):
		if not (line.ke_meal_from and line.ke_meal_to) or line.qty < 0:
			continue
		day = getdate(line.ke_meal_from)
		while day <= getdate(line.ke_meal_to):
			days.add((line.ke_diet_order, day))
			day = add_days(day, 1)
	return days


# ---------------------------------------------------------------- ward diet list


def ward_diet_list(company, on_date, ward=None):
	"""Admitted patients on `on_date` with their bed and diet; patients with
	no diet order are listed so the ward notices."""
	on_date = getdate(on_date)
	records = frappe.get_all(
		"Inpatient Record",
		filters={
			"company": company,
			"status": ["in", ADMITTED],
			"admitted_datetime": ["<=", f"{on_date} 23:59:59"],
		},
		fields=["name", "patient", "patient_name"],
	)
	beds = {}
	for occ in frappe.get_all(
		"Inpatient Occupancy",
		filters={"parent": ["in", [r.name for r in records] or [""]], "left": 0},
		fields=["parent", "service_unit"],
	):
		beds[occ.parent] = occ.service_unit
	wards = dict(
		frappe.get_all(
			"Healthcare Service Unit",
			filters={"name": ["in", list(beds.values()) or [""]]},
			fields=["name", "parent_healthcare_service_unit"],
			as_list=True,
		)
	)
	allergies = dict(
		frappe.get_all(
			"Patient",
			filters={"name": ["in", [r.patient for r in records] or [""]]},
			fields=["name", "allergies"],
			as_list=True,
		)
	)
	orders = orders_of([r.name for r in records])
	rows = []
	for r in records:
		bed = beds.get(r.name)
		row_ward = wards.get(bed)
		if ward and row_ward != ward and bed != ward:
			continue
		order = active_order([o for o in orders if o.inpatient_record == r.name], on_date)
		rows.append(
			frappe._dict(
				ward=row_ward,
				bed=bed,
				patient=r.patient,
				patient_name=r.patient_name,
				inpatient_record=r.name,
				diet_type=order.diet_type if order else None,
				meals_per_day=order.meals_per_day if order else None,
				instructions=order.instructions if order else _("No diet order"),
				allergies=allergies.get(r.patient),
				diet_order=order.name if order else None,
			)
		)
	rows.sort(key=lambda x: (x.ward or "", x.bed or ""))
	return rows
