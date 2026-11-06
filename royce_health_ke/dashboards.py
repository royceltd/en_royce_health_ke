# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Management dashboards: revenue by department, bed occupancy, insurance
claims, practitioner activity and pharmacy stock.

The figures are worked out here; the Dashboard Chart Sources and Number Cards
in kenya_health/ only call these functions. Every function takes the card's or
chart's filters: company (the user's default) and period (see PERIODS).

Revenue departments: Marley leaves the department on invoice lines empty, so
each line's department comes from what was ordered - a consultation, a lab
test, an imaging exam, a procedure, a medicine or a bed. An Item Group's
"Revenue Department" (ke_revenue_department) overrides that for its items.

Bed occupancy is a midnight census: a bed counts as occupied on a day when a
patient was in it at the end of that day."""

from collections import Counter, defaultdict
from datetime import datetime, time, timedelta

import frappe
from frappe import _
from frappe.utils import add_days, add_months, flt, get_first_day, get_quarter_start, getdate, today

from royce_health_ke.radiology import IMAGING

PERIODS = (
	"Today",
	"This Week",
	"This Month",
	"Last Month",
	"This Quarter",
	"This Year",
	"Last 30 Days",
	"Last 12 Months",
)

CONSULTATION = "Consultation"
LABORATORY = "Laboratory"
RADIOLOGY = "Radiology"
PHARMACY = "Pharmacy"
INPATIENT = "Inpatient"
PROCEDURES = "Theatre and Procedures"
PHYSIOTHERAPY = "Physiotherapy"
OTHER = "Other"

STOCK_STATUSES = ("Out of Stock", "Below Reorder Level", "Low Cover", "Expiring", "OK")


# ---------------------------------------------------------------- filters


def period_dates(period=None, on=None):
	"""(from_date, to_date) for a period name, ending today (or `on`)."""
	end = getdate(on or today())
	period = period or "This Month"
	if period == "Today":
		return end, end
	if period == "This Week":
		return add_days(end, -end.weekday()), end
	if period == "Last Month":
		first = get_first_day(add_months(end, -1))
		return first, add_days(get_first_day(end), -1)
	if period == "This Quarter":
		return getdate(get_quarter_start(end)), end
	if period == "This Year":
		return end.replace(month=1, day=1), end
	if period == "Last 30 Days":
		return add_days(end, -29), end
	if period == "Last 12 Months":
		return add_days(add_months(end, -12), 1), end
	return get_first_day(end), end


def _filters(filters):
	filters = frappe._dict(frappe.parse_json(filters) or {})
	if isinstance(filters, list):  # a list-style filter from an older card definition
		filters = frappe._dict()
	filters.company = filters.get("company") or frappe.defaults.get_user_default("Company")
	if filters.get("from_date") and filters.get("to_date"):
		filters.from_date, filters.to_date = getdate(filters.from_date), getdate(filters.to_date)
	else:
		filters.from_date, filters.to_date = period_dates(filters.get("period"))
	return filters


def _chart(chart_name=None, filters=None):
	"""A chart's filters; a chart saved without any uses its stored ones."""
	if not filters and chart_name:
		filters = frappe.db.get_value("Dashboard Chart", chart_name, "filters_json")
	return _filters(filters)


def settings():
	s = frappe.get_cached_doc("Kenya Health Settings")
	return frappe._dict(
		pharmacy_item_group=s.get("pharmacy_item_group") or "Drug",
		pharmacy_warehouse=s.get("pharmacy_warehouse"),
		expiry_warning_days=s.get("expiry_warning_days") or 90,
		min_days_of_cover=s.get("min_days_of_cover") or 14,
	)


def _descendants(doctype, name):
	if not name or not frappe.db.exists(doctype, name):
		return []
	lft, rgt = frappe.db.get_value(doctype, name, ["lft", "rgt"])
	return frappe.get_all(doctype, filters={"lft": [">=", lft], "rgt": ["<=", rgt]}, pluck="name")


# ---------------------------------------------------------------- revenue


def revenue_lines(company, from_date, to_date):
	"""Submitted invoice lines in the period (credit notes included, as
	negative amounts), each with its revenue department and the insurer's
	share."""
	lines = frappe.db.sql(
		"""
		select sii.item_code, sii.item_group, sii.reference_dt, sii.reference_dn,
			sii.base_net_amount as amount,
			coalesce(sii.insurance_coverage_amount, 0) * coalesce(si.conversion_rate, 1) as insurer,
			si.patient, si.posting_date
		from `tabSales Invoice Item` sii
		join `tabSales Invoice` si on si.name = sii.parent
		where si.docstatus = 1 and si.company = %s and si.posting_date between %s and %s
		""",
		(company, from_date, to_date),
		as_dict=True,
	)
	if not lines:
		return lines

	overrides = dict(
		frappe.get_all(
			"Item Group",
			filters={"ke_revenue_department": ["is", "set"]},
			fields=["name", "ke_revenue_department"],
			as_list=True,
		)
	)
	pharmacy_groups = set(_descendants("Item Group", settings().pharmacy_item_group))
	ordered = _ordered_templates(lines)
	inpatients = _inpatients_on({line.patient for line in lines if line.patient}, from_date, to_date)

	for line in lines:
		line.insurer = flt(line.insurer)
		line.department = overrides.get(line.item_group) or _department(
			line, pharmacy_groups, ordered, inpatients
		)
	return lines


def _department(line, pharmacy_groups, ordered, inpatients):
	dt = line.reference_dt
	if dt == "Inpatient Occupancy":
		return INPATIENT
	if dt == "Medication Request" or line.item_group in pharmacy_groups:
		return PHARMACY
	if dt in ("Patient Encounter", "Patient Appointment"):
		return CONSULTATION
	if dt in ("Clinical Procedure", "Theatre Booking"):
		return PROCEDURES
	if dt == "Lab Test":
		return LABORATORY
	if dt == "Therapy Session":
		return PHYSIOTHERAPY
	if dt in ("Service Request", "Observation"):
		kind = ordered.get((dt, line.reference_dn))
		if kind:
			return kind
	# charges added by hand (nursing, admission kits) on an inpatient's invoice
	if line.patient and line.posting_date in inpatients.get(line.patient, ()):
		return INPATIENT
	return OTHER


def _ordered_templates(lines):
	"""(reference doctype, name) -> department, for orders that name a template."""
	result = {}
	requests = {line.reference_dn for line in lines if line.reference_dt == "Service Request"}
	observations = {line.reference_dn for line in lines if line.reference_dt == "Observation"}
	templates = []
	if requests:
		for r in frappe.get_all(
			"Service Request",
			filters={"name": ["in", list(requests)]},
			fields=["name", "template_dt", "template_dn"],
		):
			templates.append(("Service Request", r.name, r.template_dt, r.template_dn))
	if observations:
		for o in frappe.get_all(
			"Observation",
			filters={"name": ["in", list(observations)]},
			fields=["name", "observation_template"],
		):
			templates.append(("Observation", o.name, "Observation Template", o.observation_template))

	imaging = set(
		frappe.get_all(
			"Observation Template",
			filters={
				"name": ["in", [t[3] for t in templates if t[2] == "Observation Template"] or [""]],
				"observation_category": IMAGING,
			},
			pluck="name",
		)
	)
	kinds = {
		"Lab Test Template": LABORATORY,
		"Clinical Procedure Template": PROCEDURES,
		"Therapy Type": PHYSIOTHERAPY,
	}
	for dt, name, template_dt, template_dn in templates:
		if template_dt == "Observation Template":
			result[(dt, name)] = RADIOLOGY if template_dn in imaging else LABORATORY
		elif template_dt in kinds:
			result[(dt, name)] = kinds[template_dt]
	return result


def _inpatients_on(patients, from_date, to_date):
	"""patient -> set of dates in the period on which they were admitted."""
	days = defaultdict(set)
	if not patients:
		return days
	for ip in frappe.get_all(
		"Inpatient Record",
		filters={
			"patient": ["in", list(patients)],
			"admitted_datetime": ["is", "set"],
			"status": ["!=", "Cancelled"],
		},
		fields=["patient", "admitted_datetime", "discharge_datetime"],
	):
		start = max(getdate(ip.admitted_datetime), from_date)
		end = min(getdate(ip.discharge_datetime) if ip.discharge_datetime else to_date, to_date)
		while start <= end:
			days[ip.patient].add(start)
			start = add_days(start, 1)
	return days


def revenue_by_department_data(company, from_date, to_date):
	patient, insurer = Counter(), Counter()
	for line in revenue_lines(company, from_date, to_date):
		insurer[line.department] += line.insurer
		patient[line.department] += flt(line.amount) - line.insurer
	departments = sorted(set(patient) | set(insurer), key=lambda d: -(patient[d] + insurer[d]))
	return {
		"labels": [_(d) for d in departments],
		"datasets": [
			{"name": _("Patients"), "values": [flt(patient[d], 2) for d in departments]},
			{"name": _("Insurers"), "values": [flt(insurer[d], 2) for d in departments]},
		],
		"type": "bar",
	}


@frappe.whitelist()
def revenue_by_department(chart_name=None, filters=None, **kwargs):
	_allow("Sales Invoice")
	f = _chart(chart_name, filters)
	return revenue_by_department_data(f.company, f.from_date, f.to_date)


@frappe.whitelist()
def revenue_card(filters=None):
	_allow("Sales Invoice")
	f = _filters(filters)
	total = sum(flt(line.amount) for line in revenue_lines(f.company, f.from_date, f.to_date))
	return _card(total, "Currency", "query-report/Sales Register", {"company": f.company, **_dates(f)})


# ---------------------------------------------------------------- beds


def beds(company):
	"""Bookable beds: leaf service units that take inpatient occupancy."""
	return frappe.get_all(
		"Healthcare Service Unit",
		filters={"company": company, "inpatient_occupancy": 1, "is_group": 0},
		fields=["name", "parent_healthcare_service_unit as ward", "occupancy_status"],
	)


def bed_occupancy_by_ward_data(company):
	occupied, vacant = Counter(), Counter()
	for bed in beds(company):
		ward = bed.ward or _("No ward")
		if bed.occupancy_status == "Occupied":
			occupied[ward] += 1
		else:
			vacant[ward] += 1
	wards = sorted(set(occupied) | set(vacant))
	return {
		"labels": wards,
		"datasets": [
			{"name": _("Occupied"), "values": [occupied[w] for w in wards]},
			{"name": _("Vacant"), "values": [vacant[w] for w in wards]},
		],
		"type": "bar",
	}


@frappe.whitelist()
def bed_occupancy_by_ward(chart_name=None, filters=None, **kwargs):
	_allow("Inpatient Record")
	f = _chart(chart_name, filters)
	return bed_occupancy_by_ward_data(f.company)


def midnight_census(company, from_date, to_date):
	"""date -> beds occupied at the end of that day."""
	bed_names = [b.name for b in beds(company)]
	census = Counter()
	if not bed_names:
		return census
	stays = frappe.get_all(
		"Inpatient Occupancy",
		filters={
			"service_unit": ["in", bed_names],
			"check_in": ["<=", datetime.combine(to_date, time.max)],
		},
		fields=["check_in", "check_out"],
	)
	for stay in stays:
		if stay.check_out and getdate(stay.check_out) < from_date:
			continue
		day = max(getdate(stay.check_in), from_date)
		# out before midnight on the check-out day: the last night is the day before
		last = getdate(stay.check_out) - timedelta(days=1) if stay.check_out else to_date
		while day <= min(last, to_date):
			census[day] += 1
			day = add_days(day, 1)
	return census


def occupancy_trend_data(company, from_date, to_date):
	total = len(beds(company))
	census = midnight_census(company, from_date, to_date)
	labels, values = [], []
	day = from_date
	while day <= to_date:
		labels.append(frappe.format(day, "Date"))
		values.append(flt(100.0 * census[day] / total, 1) if total else 0)
		day = add_days(day, 1)
	return {
		"labels": labels,
		"datasets": [{"name": _("Occupancy %"), "values": values}],
		"type": "line",
	}


@frappe.whitelist()
def bed_occupancy_trend(chart_name=None, filters=None, **kwargs):
	_allow("Inpatient Record")
	f = _chart(chart_name, filters)
	return occupancy_trend_data(f.company, f.from_date, f.to_date)


@frappe.whitelist()
def bed_occupancy_card(filters=None):
	_allow("Inpatient Record")
	f = _filters(filters)
	all_beds = beds(f.company)
	occupied = sum(1 for b in all_beds if b.occupancy_status == "Occupied")
	value = flt(100.0 * occupied / len(all_beds), 1) if all_beds else 0
	return _card(
		value,
		"Percent",
		"List/Healthcare Service Unit",
		{"inpatient_occupancy": 1, "is_group": 0, "company": f.company},
	)


@frappe.whitelist()
def average_occupancy_card(filters=None):
	_allow("Inpatient Record")
	"""Average midnight-census occupancy over the period (bed days used /
	bed days available)."""
	f = _filters(filters)
	total = len(beds(f.company))
	days = (f.to_date - f.from_date).days + 1
	used = sum(midnight_census(f.company, f.from_date, f.to_date).values())
	value = flt(100.0 * used / (total * days), 1) if total else 0
	return _card(value, "Percent", "List/Inpatient Record", {"company": f.company})


# ---------------------------------------------------------------- claims


def claims_by_payor_data(company, from_date, to_date):
	"""Insured billing by payor and stage: not yet claimed (invoiced coverage
	not on a submitted claim), claimed and awaiting payment, paid, rejected."""
	stages = defaultdict(Counter)
	for c in frappe.db.sql(
		"""
		select insurance_payor, sum(outstanding_amount) as outstanding, sum(paid_amount) as paid,
			sum(rejected_amount) as rejected
		from `tabInsurance Claim`
		where docstatus = 1 and company = %s and posting_date between %s and %s
		group by insurance_payor
		""",
		(company, from_date, to_date),
		as_dict=True,
	):
		stages[c.insurance_payor]["outstanding"] += flt(c.outstanding)
		stages[c.insurance_payor]["paid"] += flt(c.paid)
		stages[c.insurance_payor]["rejected"] += flt(c.rejected)
	for u in unclaimed(company, from_date, to_date):
		stages[u.insurance_payor]["unclaimed"] += flt(u.amount)

	payors = sorted(stages, key=lambda p: -sum(stages[p].values()))
	series = (
		("unclaimed", _("Not Claimed")),
		("outstanding", _("Awaiting Payment")),
		("paid", _("Paid")),
		("rejected", _("Rejected")),
	)
	return {
		"labels": payors,
		"datasets": [
			{"name": label, "values": [flt(stages[p][key], 2) for p in payors]} for key, label in series
		],
		"type": "bar",
	}


def unclaimed(company, from_date, to_date):
	"""Invoiced insurance coverage that no submitted claim includes yet."""
	return frappe.db.sql(
		"""
		select pic.name, pic.insurance_payor, pic.coverage_amount_invoiced as amount
		from `tabPatient Insurance Coverage` pic
		where pic.docstatus = 1 and pic.company = %s and pic.posting_date between %s and %s
			and pic.status in ('Invoiced', 'Partly Invoiced')
			and not exists (
				select 1 from `tabInsurance Claim Coverage` icc
				join `tabInsurance Claim` ic on ic.name = icc.parent
				where icc.insurance_coverage = pic.name and ic.docstatus = 1
			)
		""",
		(company, from_date, to_date),
		as_dict=True,
	)


@frappe.whitelist()
def claims_by_payor(chart_name=None, filters=None, **kwargs):
	_allow("Insurance Claim")
	f = _chart(chart_name, filters)
	return claims_by_payor_data(f.company, f.from_date, f.to_date)


@frappe.whitelist()
def claims_awaiting_payment_card(filters=None):
	_allow("Insurance Claim")
	f = _filters(filters)
	value = frappe.db.sql(
		"""select coalesce(sum(outstanding_amount), 0) from `tabInsurance Claim`
		where docstatus = 1 and company = %s and outstanding_amount > 0""",
		f.company,
	)[0][0]
	return _card(
		value, "Currency", "List/Insurance Claim", {"company": f.company, "outstanding_amount": [">", 0]}
	)


@frappe.whitelist()
def unclaimed_card(filters=None):
	_allow("Insurance Claim")
	f = _filters(filters)
	rows = unclaimed(f.company, getdate("2000-01-01"), getdate(today()))
	return _card(
		sum(flt(r.amount) for r in rows),
		"Currency",
		"List/Patient Insurance Coverage",
		{"name": ["in", [r.name for r in rows] or [""]]},
	)


@frappe.whitelist()
def rejected_claims_card(filters=None):
	_allow("Insurance Claim")
	f = _filters(filters)
	value = frappe.db.sql(
		"""select coalesce(sum(rejected_amount), 0) from `tabInsurance Claim`
		where docstatus = 1 and company = %s and posting_date between %s and %s""",
		(f.company, f.from_date, f.to_date),
	)[0][0]
	return _card(
		value, "Currency", "List/Insurance Claim", {"company": f.company, "rejected_amount": [">", 0]}
	)


# ---------------------------------------------------------------- practitioners


def practitioner_activity_data(company, from_date, to_date, limit=15):
	"""Per practitioner: consultations (submitted encounters), procedures
	completed and patients admitted, busiest first."""
	consultations = Counter(
		dict(
			frappe.db.sql(
				"""select practitioner, count(*) from `tabPatient Encounter`
				where docstatus = 1 and company = %s and encounter_date between %s and %s
				group by practitioner""",
				(company, from_date, to_date),
			)
		)
	)
	procedures = Counter(
		dict(
			frappe.db.sql(
				"""select practitioner, count(*) from `tabClinical Procedure`
				where status = 'Completed' and company = %s
					and date(coalesce(actual_end_datetime, start_date)) between %s and %s
				group by practitioner""",
				(company, from_date, to_date),
			)
		)
	)
	admissions = Counter(
		dict(
			frappe.db.sql(
				"""select coalesce(primary_practitioner, admission_practitioner), count(*)
				from `tabInpatient Record`
				where status != 'Cancelled' and company = %s and date(admitted_datetime) between %s and %s
				group by coalesce(primary_practitioner, admission_practitioner)""",
				(company, from_date, to_date),
			)
		)
	)
	practitioners = [p for p in set(consultations) | set(procedures) | set(admissions) if p]
	practitioners.sort(key=lambda p: -(consultations[p] + procedures[p] + admissions[p]))
	practitioners = practitioners[:limit]
	names = dict(
		frappe.get_all(
			"Healthcare Practitioner",
			filters={"name": ["in", practitioners or [""]]},
			fields=["name", "practitioner_name"],
			as_list=True,
		)
	)
	return {
		"labels": [names.get(p) or p for p in practitioners],
		"datasets": [
			{"name": _("Consultations"), "values": [consultations[p] for p in practitioners]},
			{"name": _("Procedures"), "values": [procedures[p] for p in practitioners]},
			{"name": _("Admissions"), "values": [admissions[p] for p in practitioners]},
		],
		"type": "bar",
	}


@frappe.whitelist()
def practitioner_activity(chart_name=None, filters=None, **kwargs):
	_allow("Patient Encounter")
	f = _chart(chart_name, filters)
	return practitioner_activity_data(f.company, f.from_date, f.to_date)


@frappe.whitelist()
def patients_seen_card(filters=None):
	_allow("Patient Encounter")
	f = _filters(filters)
	value = frappe.db.sql(
		"""select count(distinct patient) from `tabPatient Encounter`
		where docstatus = 1 and company = %s and encounter_date between %s and %s""",
		(f.company, f.from_date, f.to_date),
	)[0][0]
	return _card(
		value,
		"Int",
		"List/Patient Encounter",
		{"company": f.company, "docstatus": 1, **_dates(f, "encounter_date")},
	)


# ---------------------------------------------------------------- pharmacy


def pharmacy_stock(company, on=None):
	"""One row per stocked medicine: quantity in the pharmacy warehouse(s),
	reorder level, average daily use over the last 30 days, days of cover,
	the nearest batch expiry and a status (STOCK_STATUSES, worst first)."""
	s = settings()
	on = getdate(on or today())
	groups = _descendants("Item Group", s.pharmacy_item_group)
	if not groups:
		return []
	if s.pharmacy_warehouse:
		warehouses = _descendants("Warehouse", s.pharmacy_warehouse)
	else:
		warehouses = frappe.get_all("Warehouse", filters={"company": company, "is_group": 0}, pluck="name")
	if not warehouses:
		return []

	items = frappe.get_all(
		"Item",
		filters={"item_group": ["in", groups], "is_stock_item": 1, "disabled": 0},
		fields=["name", "item_name", "stock_uom"],
	)
	if not items:
		return []
	codes = [i.name for i in items]
	args = {"items": codes, "warehouses": warehouses, "since": add_days(on, -30), "on": on}

	qty = dict(
		frappe.db.sql(
			"""select item_code, sum(actual_qty) from tabBin
			where item_code in %(items)s and warehouse in %(warehouses)s group by item_code""",
			args,
		)
	)
	value = dict(
		frappe.db.sql(
			"""select item_code, sum(stock_value) from tabBin
			where item_code in %(items)s and warehouse in %(warehouses)s group by item_code""",
			args,
		)
	)
	reorder = dict(
		frappe.db.sql(
			"""select parent, sum(warehouse_reorder_level) from `tabItem Reorder`
			where parent in %(items)s and warehouse in %(warehouses)s group by parent""",
			args,
		)
	)
	# issues to patients and departments, not transfers between pharmacy stores
	used = dict(
		frappe.db.sql(
			"""select item_code, -sum(actual_qty) from `tabStock Ledger Entry`
			where item_code in %(items)s and warehouse in %(warehouses)s and is_cancelled = 0
				and actual_qty < 0 and posting_date between %(since)s and %(on)s
				and voucher_type in ('Sales Invoice', 'Delivery Note', 'Stock Entry')
				and not exists (
					select 1 from `tabStock Entry` se where se.name = voucher_no
						and se.purpose = 'Material Transfer'
						and voucher_type = 'Stock Entry'
				)
			group by item_code""",
			args,
		)
	)
	expiry = {}
	for item_code, expiry_date in frappe.db.sql(
		"""select sle.item_code, b.expiry_date
			from `tabStock Ledger Entry` sle
			join `tabSerial and Batch Entry` sbe on sbe.parent = sle.serial_and_batch_bundle
			join `tabBatch` b on b.name = sbe.batch_no
			where sle.item_code in %(items)s and sle.warehouse in %(warehouses)s
				and sle.is_cancelled = 0 and b.expiry_date is not null
			group by sle.item_code, b.name
			having sum(sbe.qty) > 0""",
		args,
	):
		if item_code not in expiry or expiry_date < expiry[item_code]:
			expiry[item_code] = expiry_date
	rows = []
	for item in items:
		q = flt(qty.get(item.name))
		daily = flt(used.get(item.name)) / 30
		level = flt(reorder.get(item.name))
		nearest = expiry.get(item.name)
		cover = flt(q / daily, 1) if daily else None
		status = stock_status(q, level, cover, nearest, on, s)
		rows.append(
			frappe._dict(
				item_code=item.name,
				item_name=item.item_name,
				uom=item.stock_uom,
				qty=q,
				reorder_level=level,
				daily_use=flt(daily, 2),
				days_of_cover=cover,
				nearest_expiry=nearest,
				stock_value=flt(value.get(item.name), 2),
				status=status,
			)
		)
	rows.sort(key=lambda r: (STOCK_STATUSES.index(r.status), r.item_name))
	return rows


def stock_status(qty, reorder_level, days_of_cover, nearest_expiry, on, s):
	"""The worst that applies, in STOCK_STATUSES order."""
	if qty <= 0:
		return "Out of Stock"
	if reorder_level and qty <= reorder_level:
		return "Below Reorder Level"
	if days_of_cover is not None and days_of_cover < s.min_days_of_cover:
		return "Low Cover"
	if nearest_expiry and (getdate(nearest_expiry) - getdate(on)).days <= s.expiry_warning_days:
		return "Expiring"
	return "OK"


def _stock_card(status, filters):
	f = _filters(filters)
	rows = pharmacy_stock(f.company)
	return _card(
		sum(1 for r in rows if r.status == status),
		"Int",
		"query-report/Pharmacy Stock Status",
		{"company": f.company, "status": status},
	)


@frappe.whitelist()
def out_of_stock_card(filters=None):
	_allow("Bin")
	return _stock_card("Out of Stock", filters)


@frappe.whitelist()
def below_reorder_card(filters=None):
	_allow("Bin")
	return _stock_card("Below Reorder Level", filters)


@frappe.whitelist()
def expiring_card(filters=None):
	_allow("Bin")
	return _stock_card("Expiring", filters)


@frappe.whitelist()
def pharmacy_stock_value_card(filters=None):
	_allow("Bin")
	f = _filters(filters)
	value = sum(r.stock_value for r in pharmacy_stock(f.company))
	return _card(value, "Currency", "query-report/Pharmacy Stock Status", {"company": f.company})


# ---------------------------------------------------------------- helpers


def _allow(doctype):
	"""The dashboards show what the underlying records show: refuse users who
	can't read them."""
	if not frappe.has_permission(doctype, "read"):
		frappe.throw(_("Not permitted to read {0}").format(_(doctype)), frappe.PermissionError)


def _dates(f, field=None):
	if field:
		return {field: ["between", [str(f.from_date), str(f.to_date)]]}
	return {"from_date": str(f.from_date), "to_date": str(f.to_date)}


def _card(value, fieldtype, route, route_options=None):
	return {
		"value": value,
		"fieldtype": fieldtype,
		"route": route.split("/"),
		"route_options": route_options or {},
	}
