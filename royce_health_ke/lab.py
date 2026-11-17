# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""The laboratory's worklist and the consultants' results inbox, on Marley's
Service Requests and Lab Tests.

Marley keeps one Service Request and one Lab Test per test. The lab works per
patient order: the worklist shows one row per visit (or consultation) with
its tests counted, and opening it lists the tests. A test moves through:

- Requested: the doctor's request, no lab test yet. The lab sees whether it
  is paid (or insured, inpatient, approved for credit) before collecting.
- Collected: Collect Sample creates the lab test (the payment rule applies)
  and records who collected the sample and when.
- Entered: results typed in, not yet validated. The person who typed them
  last is kept on the lab test.
- Completed: Validate submits the lab test, recording who validated and when
  (Marley's Verified By and approval date, which the Laboratory Report
  prints). By default whoever entered the results may validate them; with
  Kenya Health Settings > Laboratory > "A second person validates" on, it
  must be someone else.

A walk-in (a patient sent by an outside doctor) gets the same requests,
on the day's open visit or a new "Lab only" visit, so the cashier bills
them the usual way.

Results inbox: each consultant's completed lab tests and reported imaging
exams, unread until opened from the inbox."""

import json

import frappe
from frappe import _
from frappe.utils import add_days, cint, get_datetime, getdate, now_datetime, nowdate

from royce_health_ke import coverage, visit_bill
from royce_health_ke.printing import flag
from royce_health_ke.visits import age_label, open_visit_for

LAB_TEMPLATE = "Lab Test Template"
CLOSED_REQUEST = ("revoked-Request Status", "entered-in-error-Request Status", "draft-Request Status")
REQUESTED, COLLECTED, ENTERED, COMPLETED = "Requested", "Collected", "Entered", "Completed"
STAGES = (REQUESTED, COLLECTED, ENTERED, COMPLETED)
TABS = {
	"requests": REQUESTED,
	"entry": COLLECTED,
	"validate": ENTERED,
	"completed": COMPLETED,
	"register": None,
}
PRIORITY_RANK = {"STAT": 4, "ASAP": 3, "Urgent": 2, "Routine": 1}
PAY_LABELS = {
	"paid": _("Paid"),
	"insured": _("Insured"),
	"inpatient": _("Inpatient"),
	"casualty": _("Casualty"),
	"approved": _("Credit approved"),
	"unpaid": _("Not paid"),
}


def _list(value):
	if not value:
		return []
	if isinstance(value, str):
		value = json.loads(value) if value.strip().startswith("[") else [value]
	return [v for v in value if v]


def _priority(value):
	"""'Urgent' from Marley's code value name 'Urgent-Priority'."""
	return (value or "").split("-")[0] or "Routine"


# Document events


def link_request_visit(doc, method=None):
	"""Service Request before_insert: the visit of the consultation that ordered it."""
	if not doc.get("ke_patient_visit") and doc.get("order_group"):
		doc.ke_patient_visit = frappe.db.get_value("Patient Encounter", doc.order_group, "ke_patient_visit")


def lab_test_before_insert(doc, method=None):
	if not doc.get("ke_patient_visit"):
		visit = None
		if doc.get("service_request"):
			visit = frappe.db.get_value("Service Request", doc.service_request, "ke_patient_visit")
			visit = visit or visit_bill.visit_of_request(doc.service_request)
		doc.ke_patient_visit = visit or (None if doc.get("inpatient_record") else open_visit_for(doc.patient))


def _result_values(doc):
	return tuple(
		(r.idx, r.get("result_value") or "")
		for field in ("normal_test_items", "descriptive_test_items")
		for r in doc.get(field) or []
	)


def has_results(doc):
	return any(value for _idx, value in _result_values(doc))


def lab_test_validate(doc, method=None):
	"""Who entered the results: whoever last changed them."""
	if doc.docstatus != 0 or not has_results(doc):
		return
	before = doc.get_doc_before_save()
	if not doc.get("ke_results_by") or before is None or _result_values(before) != _result_values(doc):
		doc.ke_results_by = frappe.session.user


def lab_test_before_submit(doc, method=None):
	"""Validating the results."""
	user = frappe.session.user
	if (
		frappe.db.get_single_value("Kenya Health Settings", "lab_second_validator")
		and doc.get("ke_results_by") == user
	):
		frappe.throw(
			_("You entered these results. Another person validates them."),
			title=_("Second person validates"),
		)
	doc.user = user
	doc.approved_date = now_datetime()


# Worklist


def _requests(from_date, to_date, company=None, patient=None):
	conditions, values = (
		["sr.template_dt = %(dt)s", "sr.docstatus = 1", "sr.status not in %(closed)s"],
		{
			"dt": LAB_TEMPLATE,
			"closed": CLOSED_REQUEST,
			"from": from_date,
			"to": to_date,
		},
	)
	conditions.append("sr.order_date between %(from)s and %(to)s")
	if company:
		conditions.append("sr.company = %(company)s")
		values["company"] = company
	if patient:
		conditions.append("sr.patient = %(patient)s")
		values["patient"] = patient
	return frappe.db.sql(
		f"""
		select sr.name, sr.patient, sr.patient_name, sr.patient_gender, sr.patient_age_data,
			sr.template_dn, sr.order_date, sr.order_time, sr.creation, sr.priority,
			sr.practitioner, sr.practitioner_name, sr.order_group, sr.inpatient_record,
			sr.insurance_policy, sr.insurance_coverage, sr.status,
			sr.ke_payment_status, sr.ke_payment_exemption,
			coalesce(nullif(sr.ke_patient_visit, ''), enc.ke_patient_visit) as visit
		from `tabService Request` sr
		left join `tabPatient Encounter` enc on enc.name = sr.order_group
		where {" and ".join(conditions)}
		""",
		values,
		as_dict=True,
	)


def _lab_tests(requests, from_date, to_date, company=None, patient=None):
	"""Lab tests of these requests, and tests made without a request in the period."""
	conditions = ["lt.docstatus < 2"]
	values = {"from": f"{from_date} 00:00:00", "to": f"{to_date} 23:59:59"}
	own = "(ifnull(lt.service_request, '') = '' and lt.creation between %(from)s and %(to)s)"
	if requests:
		values["requests"] = tuple(requests)
		conditions.append(f"(lt.service_request in %(requests)s or {own})")
	else:
		conditions.append(own)
	if company:
		conditions.append("lt.company = %(company)s")
		values["company"] = company
	if patient:
		conditions.append("lt.patient = %(patient)s")
		values["patient"] = patient
	return frappe.db.sql(
		f"""
		select lt.name, lt.service_request, lt.patient, lt.patient_name, lt.patient_sex,
			lt.patient_age, lt.template, lt.lab_test_name, lt.docstatus, lt.creation,
			lt.practitioner, lt.practitioner_name, lt.inpatient_record, null as insurance_coverage,
			lt.ke_patient_visit as visit, lt.ke_sample_collected_at, lt.ke_result_at,
			(exists(select 1 from `tabNormal Test Result` n
				where n.parent = lt.name and n.parenttype = 'Lab Test' and ifnull(n.result_value, '') != '')
			or exists(select 1 from `tabDescriptive Test Result` d
				where d.parent = lt.name and d.parenttype = 'Lab Test' and ifnull(d.result_value, '') != '')
			) as has_results
		from `tabLab Test` lt
		where {" and ".join(conditions)}
		""",
		values,
		as_dict=True,
	)


def _awaiting_payment(line):
	"""A cash request not paid yet: off the worklist until the Cashier takes payment."""
	return line.stage == REQUESTED and _pay(line)[1]


def _pay(line):
	"""(status key, blocked): blocked = the lab may not collect yet. A request
	reads its stored payment status (payment_status.py); a test made without a
	request is worked out here."""
	if line.get("request"):
		from royce_health_ke import payment_status

		status, why = (
			(line.payment_status, line.payment_exemption)
			if line.get("payment_status")
			else payment_status.stored(payment_status.SR, line.request)
		)
		if status == payment_status.EXEMPT:
			return why, False
		if status == payment_status.PAID:
			return "paid", False
		return "unpaid", visit_bill.enforced(visit_bill.LAB)
	insured = coverage.pays_uncovered() and coverage.is_covered(line.insurance_coverage)
	why = visit_bill.exemption(line.patient, line.visit, line.inpatient_record, insured)
	if why:
		return why, False
	if visit_bill.is_paid("Lab Test", line.lab_test):
		return "paid", False
	return "unpaid", visit_bill.enforced(visit_bill.LAB)


def _lines(from_date, to_date, company=None, patient=None):
	requests = _requests(from_date, to_date, company, patient)
	tests = _lab_tests([r.name for r in requests], from_date, to_date, company, patient)
	by_request = {t.service_request: t for t in tests if t.service_request}
	lines = []
	for r in requests:
		t = by_request.get(r.name)
		if not t and r.status == "completed-Request Status":
			continue  # done some other way (outside the lab's lab tests)
		lines.append(
			frappe._dict(
				request=r.name,
				lab_test=t.name if t else None,
				patient=r.patient,
				patient_name=r.patient_name,
				sex=r.patient_gender,
				age=r.patient_age_data,
				test=r.template_dn,
				ordered_at=get_datetime(f"{r.order_date} {r.order_time}") if r.order_time else r.creation,
				priority=_priority(r.priority),
				practitioner=r.practitioner,
				practitioner_name=r.practitioner_name,
				encounter=r.order_group,
				inpatient_record=r.inpatient_record,
				insurance_policy=r.insurance_policy,
				insurance_coverage=r.insurance_coverage,
				payment_status=r.ke_payment_status,
				payment_exemption=r.ke_payment_exemption,
				visit=r.visit or (t and t.visit),
				lab_test_doc=t,
			)
		)
	for t in tests:
		if t.service_request:
			continue
		lines.append(
			frappe._dict(
				request=None,
				lab_test=t.name,
				patient=t.patient,
				patient_name=t.patient_name,
				sex=t.patient_sex,
				age=t.patient_age,
				test=t.lab_test_name or t.template,
				ordered_at=t.creation,
				priority="Routine",
				practitioner=t.practitioner,
				practitioner_name=t.practitioner_name,
				encounter=None,
				inpatient_record=t.inpatient_record,
				insurance_coverage=t.insurance_coverage,
				visit=t.visit,
				lab_test_doc=t,
			)
		)
	dobs = (
		dict(
			frappe.get_all(
				"Patient",
				filters={"name": ["in", list({x.patient for x in lines})]},
				fields=["name", "dob"],
				as_list=True,
			)
		)
		if lines
		else {}
	)
	for line in lines:
		line.age = age_label(dobs.get(line.patient)) or line.age
		t = line.pop("lab_test_doc")
		if not t:
			line.stage = REQUESTED
		elif t.docstatus == 1:
			line.stage = COMPLETED
		elif t.has_results:
			line.stage = ENTERED
		else:
			line.stage = COLLECTED
		line.collected_at = t and t.ke_sample_collected_at
		line.result_at = t and t.ke_result_at
		line.key = group_key(line)
	return lines


def group_key(line):
	if line.visit:
		return f"visit:{line.visit}"
	if line.encounter:
		return f"enc:{line.encounter}"
	return f"pat:{line.patient}:{getdate(line.ordered_at)}"


def _range(from_date, to_date):
	to_date = getdate(to_date or nowdate())
	from_date = getdate(from_date or add_days(to_date, -6))
	return from_date, to_date


@frappe.whitelist()
def worklist(
	tab: str = "requests",
	from_date: str | None = None,
	to_date: str | None = None,
	company: str | None = None,
	search: str | None = None,
):
	"""One row per patient order, for the tab's stage."""
	frappe.has_permission("Lab Test", "read", throw=True)
	if tab not in TABS:
		frappe.throw(_("Unknown tab {0}.").format(tab))
	from_date, to_date = _range(from_date, to_date)
	groups, awaiting = {}, set()
	for line in _lines(from_date, to_date, company):
		if _awaiting_payment(line):
			awaiting.add(line.key)
			continue
		g = groups.get(line.key)
		if not g:
			g = groups[line.key] = frappe._dict(
				key=line.key,
				visit=line.visit,
				patient=line.patient,
				patient_name=line.patient_name,
				sex=line.sex,
				age=line.age,
				practitioner_name=line.practitioner_name,
				requested_at=line.ordered_at,
				priority=line.priority,
				inpatient=bool(line.inpatient_record),
				insured=False,
				tests=[],
				counts=dict.fromkeys(STAGES, 0),
				unpaid=0,
			)
		g.tests.append(line.test)
		g.insured = g.insured or bool(line.get("insurance_policy"))
		g.counts[line.stage] += 1
		if get_datetime(line.ordered_at) < get_datetime(g.requested_at):
			g.requested_at = line.ordered_at
		if PRIORITY_RANK.get(line.priority, 0) > PRIORITY_RANK.get(g.priority, 0):
			g.priority = line.priority
		if line.stage == REQUESTED:
			status, _blocked = _pay(line)
			g.unpaid += status == "unpaid"
	stage = TABS[tab]
	rows = [g for g in groups.values() if not stage or g.counts[stage]]
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
		method = methods.get(g.visit) or ("Insurance" if g.insured else "Cash")
		g.payment_method = _("Inpatient") if g.inpatient else _(method)
		g.count = len(g.tests)
	rows.sort(key=lambda g: (-PRIORITY_RANK.get(g.priority, 0), get_datetime(g.requested_at)))
	return {
		"rows": rows,
		"tab_counts": {t: sum(1 for g in groups.values() if not s or g.counts[s]) for t, s in TABS.items()},
		# patients whose requested tests wait for payment at the Cashier (not listed)
		"awaiting_payment": len(awaiting),
	}


@frappe.whitelist()
def order(key: str, from_date: str | None = None, to_date: str | None = None):
	"""The tests of one worklist row."""
	frappe.has_permission("Lab Test", "read", throw=True)
	patient = _patient_of(key)
	from_date, to_date = _range(from_date, to_date)
	lines = [
		line
		for line in _lines(from_date, to_date, patient=patient)
		if line.key == key and not _awaiting_payment(line)
	]
	out = []
	for line in sorted(lines, key=lambda x: (STAGES.index(x.stage), x.test)):
		row = {
			"request": line.request,
			"lab_test": line.lab_test,
			"test": line.test,
			"stage": line.stage,
			"priority": line.priority,
			"ordered_at": line.ordered_at,
			"collected_at": line.collected_at,
			"result_at": line.result_at,
			"practitioner_name": line.practitioner_name,
		}
		if line.stage == REQUESTED:
			status, blocked = _pay(line)
			row.update(pay=status, pay_label=PAY_LABELS.get(status, status), blocked=blocked)
		out.append(row)
	first = lines[0] if lines else frappe._dict()
	return {
		"key": key,
		"patient": patient,
		"patient_name": first.get("patient_name"),
		"sex": first.get("sex"),
		"age": first.get("age"),
		"visit": first.get("visit"),
		"tests": out,
	}


def _patient_of(key):
	kind, _sep, rest = key.partition(":")
	if kind == "visit":
		return frappe.db.get_value("Patient Visit", rest, "patient")
	if kind == "enc":
		return frappe.db.get_value("Patient Encounter", rest, "patient")
	if kind == "pat":
		return rest.rsplit(":", 1)[0]
	frappe.throw(_("Unknown order {0}.").format(key))


@frappe.whitelist()
def collect(requests: str | list | None = None, lab_tests: str | list | None = None):
	"""Collect samples: a lab test for each request (paid, or exempt), with
	who collected and when. Returns what was done and what was refused."""
	from healthcare.healthcare.doctype.service_request.service_request import make_lab_test

	frappe.has_permission("Lab Test", "create", throw=True)
	now, user = now_datetime(), frappe.session.user
	done, refused = [], []
	for request in _list(requests):
		existing = frappe.db.get_value("Lab Test", {"service_request": request, "docstatus": ["<", 2]})
		if existing:
			lab_tests = [*_list(lab_tests), existing]
			continue
		frappe.db.savepoint("ke_collect")
		try:
			doc = make_lab_test(request)
			doc.ke_sample_collected_at, doc.ke_sample_collected_by = now, user
			doc.insert()
			done.append(doc.name)
		except frappe.ValidationError as e:
			frappe.db.rollback(save_point="ke_collect")
			frappe.clear_messages()
			test = frappe.db.get_value("Service Request", request, "template_dn")
			refused.append({"test": test, "message": str(e)})
	for name in _list(lab_tests):
		doc = frappe.get_doc("Lab Test", name)
		doc.check_permission("write")
		if doc.docstatus == 0 and not doc.get("ke_sample_collected_at"):
			doc.db_set({"ke_sample_collected_at": now, "ke_sample_collected_by": user})
		done.append(name)
	return {"done": done, "refused": refused}


@frappe.whitelist()
def results_sheet(lab_tests: str | list):
	"""Result lines of draft lab tests, to enter on one screen."""
	out = []
	for name in _list(lab_tests):
		doc = frappe.get_doc("Lab Test", name)
		doc.check_permission("read")
		normal = [
			{
				"name": r.name,
				"label": r.lab_test_event or r.lab_test_name,
				"heading": not r.lab_test_uom and not r.normal_range and not r.require_result_value,
				"value": r.result_value or "",
				"uom": r.lab_test_uom or "",
				"range": r.normal_range or "",
				"flag": flag(r.result_value, r.normal_range, doc.patient_sex),
				"required": bool(r.require_result_value and not r.allow_blank),
			}
			for r in doc.normal_test_items
		]
		descriptive = [
			{
				"name": r.name,
				"label": r.lab_test_particulars,
				"value": r.result_value or "",
				"required": bool(r.require_result_value and not r.allow_blank),
			}
			for r in doc.descriptive_test_items
		]
		out.append(
			{
				"lab_test": doc.name,
				"test": doc.lab_test_name or doc.template,
				"docstatus": doc.docstatus,
				"normal": normal,
				"descriptive": descriptive,
				"comment": doc.lab_test_comment or "",
				# Sensitivity, organisms and free-form results stay on the full form.
				"full_form_only": bool(
					doc.get("sensitivity_toggle")
					or doc.get("organism_test_items")
					or doc.get("imaging_toggle")
				)
				or not (normal or descriptive),
				"results_by": doc.get("ke_results_by"),
				"sex": doc.patient_sex,
			}
		)
	return out


@frappe.whitelist()
def save_results(results: str | list, validate: int = 0):
	"""Save the results typed on the worklist; with `validate`, submit each
	lab test as well. One test failing doesn't stop the others."""
	results = json.loads(results) if isinstance(results, str) else results
	saved, validated, errors = [], [], []
	for entry in results:
		doc = frappe.get_doc("Lab Test", entry["lab_test"])
		doc.check_permission("write")
		if doc.docstatus != 0:
			continue
		frappe.db.savepoint("ke_results")
		try:
			for field, values in (
				("normal_test_items", entry.get("normal")),
				("descriptive_test_items", entry.get("descriptive")),
			):
				for row in doc.get(field):
					if values and row.name in values:
						row.result_value = values[row.name]
			if "comment" in entry:
				doc.lab_test_comment = entry["comment"]
			doc.save()
			saved.append(doc.name)
			if cint(validate):
				doc.check_permission("submit")
				doc.submit()
				validated.append(doc.name)
		except frappe.ValidationError as e:
			frappe.db.rollback(save_point="ke_results")
			frappe.clear_messages()
			errors.append({"lab_test": doc.name, "test": doc.lab_test_name, "message": str(e)})
	return {"saved": saved, "validated": validated, "errors": errors}


@frappe.whitelist()
def walk_in(
	patient: str,
	tests: str | list,
	practitioner: str | None = None,
	referred_by: str | None = None,
	priority: str | None = None,
	company: str | None = None,
):
	"""Requests for a patient who came to the lab directly. They go on the
	patient's open visit today, or on a new "Lab only" cash visit."""
	frappe.has_permission("Lab Test", "create", throw=True)
	tests = _list(tests)
	if not tests:
		frappe.throw(_("Choose at least one test."))
	visit_name = open_visit_for(patient)
	practitioner = (
		practitioner
		or frappe.db.get_single_value("Kenya Health Settings", "walk_in_lab_practitioner")
		or (visit_name and frappe.db.get_value("Patient Visit", visit_name, "practitioner"))
	)
	if not practitioner:
		frappe.throw(
			_(
				"Choose the requesting doctor, or set a default for walk-ins in Kenya Health Settings > Laboratory."
			),
			title=_("Requesting doctor"),
		)
	if visit_name:
		visit = frappe.get_doc("Patient Visit", visit_name)
	else:
		visit = frappe.get_doc(
			{
				"doctype": "Patient Visit",
				"patient": patient,
				"company": company
				or frappe.defaults.get_user_default("Company")
				or frappe.db.get_single_value("Global Defaults", "default_company"),
				"visit_type": "Lab only",
				"payment_method": "Cash",
				"is_referral": 1 if referred_by else 0,
				"referred_from": referred_by,
			}
		)
		visit.insert(ignore_permissions=True)
	policy = visit.insurance_policy if visit.payment_method == "Insurance" else None
	now = now_datetime()
	made = []
	for template in tests:
		sr = frappe.get_doc(
			{
				"doctype": "Service Request",
				"patient": patient,
				"company": visit.company,
				"practitioner": practitioner,
				"template_dt": LAB_TEMPLATE,
				"template_dn": template,
				"order_date": now.date(),
				"order_time": now.time(),
				"source": "External Referral" if referred_by else "Direct",
				"priority": f"{priority}-Priority" if priority and priority != "Routine" else None,
				"order_description": _("Walk-in, referred by {0}").format(referred_by)
				if referred_by
				else None,
				"insurance_policy": policy,
				"ke_patient_visit": visit.name,
			}
		)
		sr.insert(ignore_permissions=True)
		sr.submit()
		made.append(sr.name)
	visit_bill.refresh_bill_status(visit.name)
	return {"visit": visit.name, "requests": made, "key": f"visit:{visit.name}"}


# Results inbox


def my_practitioner():
	return frappe.db.get_value("Healthcare Practitioner", {"user_id": frappe.session.user}, "name")


@frappe.whitelist()
def results_inbox(
	practitioner: str | None = None,
	unread_only: int = 1,
	from_date: str | None = None,
	to_date: str | None = None,
):
	"""Completed lab tests and reported imaging exams, newest first.
	`practitioner` blank = every consultant's."""
	frappe.has_permission("Lab Test", "read", throw=True)
	to_date = getdate(to_date or nowdate())
	from_date = getdate(from_date or add_days(to_date, -13))
	period = ["between", [f"{from_date} 00:00:00", f"{to_date} 23:59:59"]]
	# Results from before v0.22 have no result time: their last change stands in.
	conditions = ["docstatus = 1", "coalesce(ke_result_at, modified) between %(from)s and %(to)s"]
	values = {"from": period[1][0], "to": period[1][1], "practitioner": practitioner}
	if practitioner:
		conditions.append("practitioner = %(practitioner)s")
	if cint(unread_only):
		conditions.append("ke_seen_at is null")
	labs = frappe.db.sql(
		f"""select name, patient, patient_name, lab_test_name as test, practitioner_name,
			coalesce(ke_result_at, modified) as result_at, ke_seen_at as seen_at,
			ke_seen_by as seen_by, ke_patient_visit as visit
		from `tabLab Test` where {" and ".join(conditions)}
		order by result_at desc limit 500""",
		values,
		as_dict=True,
	)
	flagged = _flagged([r.name for r in labs])
	for r in labs:
		r.doctype, r.department, r.abnormal = "Lab Test", _("Laboratory"), r.name in flagged
	imaging = []
	if frappe.get_meta("Observation").has_field("ke_seen_at"):
		obs_filters = {"ke_exam_status": ["in", ["Reported", "Verified"]], "ke_reported_at": period}
		if practitioner:
			obs_filters["healthcare_practitioner"] = practitioner
		if cint(unread_only):
			obs_filters["ke_seen_at"] = ["is", "not set"]
		imaging = frappe.get_all(
			"Observation",
			filters=obs_filters,
			fields=[
				"name",
				"patient",
				"patient_name",
				"observation_template as test",
				"practitioner_name",
				"ke_reported_at as result_at",
				"ke_seen_at as seen_at",
				"ke_seen_by as seen_by",
			],
			order_by="ke_reported_at desc",
			limit=500,
		)
		for r in imaging:
			r.doctype, r.department, r.abnormal = "Observation", _("Radiology"), False
	rows = sorted([*labs, *imaging], key=lambda r: get_datetime(r.result_at), reverse=True)
	names = {r.seen_by for r in rows if r.seen_by}
	full = (
		dict(
			frappe.get_all(
				"User", filters={"name": ["in", list(names)]}, fields=["name", "full_name"], as_list=True
			)
		)
		if names
		else {}
	)
	for r in rows:
		r.seen_by_name = full.get(r.seen_by, r.seen_by)
	return {"rows": rows, "practitioner": practitioner, "mine": my_practitioner()}


def _flagged(lab_tests):
	if not lab_tests:
		return set()
	rows = frappe.get_all(
		"Normal Test Result",
		filters={"parent": ["in", lab_tests], "parenttype": "Lab Test"},
		fields=["parent", "result_value", "normal_range"],
	)
	sexes = dict(
		frappe.get_all(
			"Lab Test", filters={"name": ["in", lab_tests]}, fields=["name", "patient_sex"], as_list=True
		)
	)
	return {r.parent for r in rows if flag(r.result_value, r.normal_range, sexes.get(r.parent))}


@frappe.whitelist()
def mark_seen(doctype: str, name: str):
	if doctype not in ("Lab Test", "Observation"):
		frappe.throw(_("Not a result."))
	frappe.has_permission(doctype, "read", name, throw=True)
	if not frappe.db.get_value(doctype, name, "ke_seen_at"):
		frappe.db.set_value(
			doctype,
			name,
			{"ke_seen_at": now_datetime(), "ke_seen_by": frappe.session.user},
			update_modified=False,
		)
