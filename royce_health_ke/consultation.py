# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""The consultation in the hospital's order (outpatient feedback, 16 Nov 2026):

	Patient -> Observation -> Requests -> Results -> Diagnosis -> Prescription -> Complete

- The tabs are custom Tab Breaks (setup/custom_fields.py CONSULTATION_TABS);
  Marley's sections are moved under them with one `field_order` property
  setter, set once: a hospital that orders the form itself keeps its order
  (ADR-023). Marley's own tabs (Encounter Details, Notes) stay last.
- Send Requests: the lab, imaging and procedure requests are placed while the
  consultation stays open (Marley's "submit orders on save"), so they reach
  the bill and their service point before the results come back.
- Results: this visit's lab results and imaging reports, read where the
  doctor works, with what each request is waiting for.
- Complete Consultation: submits the encounter and suggests where the patient
  goes next (Cashier for unpaid requests, the service points, Pharmacy)."""

import json

import frappe
from frappe import _
from frappe.utils import cint

from royce_health_ke import visit_bill

DT = "Patient Encounter"
LAB_TEMPLATE = "Lab Test Template"
OBS_TEMPLATE = "Observation Template"

# (tab break, the sections under it, in this order). A section not named here
# stays under the tab of the section it followed.
TABS = (
	("ke_tab_patient", (None, "insurance_section")),
	(
		"ke_tab_observation",
		("ke_clerking_section", "ke_history_section", "ke_obs_section", "ke_exam_section"),
	),
	(
		"ke_tab_requests",
		(
			"ke_request_type_section",
			"sb_test_prescription",
			"sb_procedures",
			"rehabilitation_section",
			"ke_requests_section",
		),
	),
	("ke_tab_results", ("ke_results_section",)),
	("ke_tab_diagnosis", ("sb_symptoms", "codification")),
	("ke_tab_prescription", ("ke_pharmacy_section", "sb_drug_prescription")),
	(
		"ke_tab_complete",
		("section_break_33", "ke_referral_section", "sb_source", "sb_refs", "ke_complete_section"),
	),
)
OUR_TABS = {tab for tab, _sections in TABS}
# Bumped when our default order changes. v2 (v0.45): the clerking order CC,
# HPI, ROS, PMH/PSH, FH, SH, OBS/Gynae, examination last; the Request Type.
# v3 (v0.50): the Order Drug panel on the Prescription tab.
LAYOUT_VERSION = 3
LAYOUT_KEY = "ke_consultation_layout"


# Layout


def _layout_property():
	return frappe.db.get_value(
		"Property Setter", {"doc_type": DT, "property": "field_order"}, ["name", "value"], as_dict=True
	)


def on_our_default(value):
	"""True when a stored field order is ours: re-ordering it under our tabs
	changes nothing (a hospital that moved sections between tabs, or reordered
	the form in Customize Form, has its own)."""
	try:
		order = json.loads(value or "[]")
	except ValueError:
		return False
	if not order or not all(tab in order for tab in OUR_TABS):
		return False
	meta = frappe.get_meta(DT)
	types = {f.fieldname: f.fieldtype for f in meta.fields}
	pairs = [(name, types[name]) for name in order if name in types]
	known = [name for name, _type in pairs]
	return layout_order(pairs) == known


def apply_layout():
	"""Order the consultation's fields under the tabs, once (ADR-023). When our
	default order changes (LAYOUT_VERSION), a site still on our earlier default
	gets the new one; a hospital's own order is kept."""
	existing = _layout_property()
	version = cint(frappe.db.get_default(LAYOUT_KEY))
	if existing:
		if version >= LAYOUT_VERSION:
			return
		if not on_our_default(existing.value):
			frappe.db.set_default(LAYOUT_KEY, LAYOUT_VERSION)
			return
		frappe.delete_doc("Property Setter", existing.name, ignore_permissions=True, force=True)
	frappe.clear_cache(doctype=DT)
	meta = frappe.get_meta(DT, cached=False)
	if not all(meta.has_field(tab) for tab in OUR_TABS):
		return
	order = layout_order([(f.fieldname, f.fieldtype) for f in meta.fields])
	frappe.make_property_setter(
		{
			"doctype": DT,
			"doctype_or_field": "DocType",
			"property": "field_order",
			"value": json.dumps(order),
			"property_type": "Data",
		},
		is_system_generated=False,
	)
	frappe.db.set_default(LAYOUT_KEY, LAYOUT_VERSION)
	frappe.clear_cache(doctype=DT)


def layout_order(fields):
	"""fields: [(fieldname, fieldtype)] in the form's current order. Returns
	the fieldnames with each section under its tab, other tabs (Marley's
	Encounter Details and Notes) kept last. One of our sections that Frappe
	placed inside those tabs is still moved under its own tab."""
	place = {}
	for t, (_tab, sections) in enumerate(TABS):
		for s, section in enumerate(sections):
			place[section] = (t, s)
	other_tabs = len(TABS)
	segments, current, tail_place = [], (0, 0), None
	for fieldname, fieldtype in fields:
		if fieldname in OUR_TABS:
			continue
		if fieldtype == "Tab Break":
			tail_place = (other_tabs, len(segments))
			current = tail_place
			segments.append([current, len(segments), [fieldname]])
		elif fieldtype == "Section Break" or not segments:
			key = fieldname if fieldtype == "Section Break" else None
			current = place.get(key) or tail_place or current
			segments.append([current, len(segments), [fieldname]])
		else:
			segments[-1][2].append(fieldname)
	segments.sort(key=lambda seg: (seg[0], seg[1]))
	order = []
	for t, (tab, _sections) in enumerate(TABS):
		order.append(tab)
		for (st, _s), _i, names in segments:
			if st == t:
				order.extend(names)
	for (st, _s), _i, names in segments:
		if st >= other_tabs:
			order.extend(names)
	return order


# Before requests are placed (IT demo, 17 Nov 2026)
#
# - The Lab Tests table's Observation column orders Marley Observations. In
#   this system only imaging is done that way (radiology worklist); the lab
#   works from Lab Test Templates. A haemogram or SpO2 ordered as an
#   Observation reached no department, so it is refused with what to do.
# - Observation first: the consultation's Observation tab is filled before
#   anything is ordered (Kenya Health Settings > Consultation). Not for
#   casualty or inpatients, where tests may come before the notes.

# (Kenya Health Settings switch, consultation field)
OBSERVATION_FIELDS = (
	("obs_need_complaint", "ke_chief_complaint"),
	("obs_need_hpi", "ke_hpi"),
	("obs_need_ros", "ke_review_of_systems"),
	("obs_need_examination", "ke_examination"),
)
ORDER_TABLES = ("lab_test_prescription", "procedure_prescription", "therapies")


def _placing_orders(doc):
	"""True when this save or submit places the consultation's orders (Marley
	places them in validate when 'submit orders on save' is ticked, and on
	submit)."""
	if doc.docstatus == 1:
		return getattr(doc, "_action", None) == "submit"
	return not doc.is_new() and cint(doc.get("submit_orders_on_save"))


def new_orders(doc):
	"""The order rows not placed yet: requests and medicines."""
	rows = [r for table in ORDER_TABLES for r in doc.get(table) or [] if not r.get("service_request")]
	return rows + new_drugs(doc)


def _is_imaging_template(template):
	from royce_health_ke.radiology import IMAGING

	return frappe.db.get_value(OBS_TEMPLATE, template, "observation_category") == IMAGING


def check_lab_rows(doc):
	for row in doc.get("lab_test_prescription") or []:
		if row.get("service_request") or not row.get("observation_template"):
			continue
		# Marley orders a row's imaging exam and drops its lab test: one per row
		if row.get("lab_test_code"):
			frappe.throw(
				_(
					"Row {0} of the lab requests has both a lab test ({1}) and an imaging exam ({2}). "
					"Put each on its own row: one row orders one test or one exam."
				).format(row.idx, frappe.bold(row.lab_test_code), frappe.bold(row.observation_template)),
				title=_("One request per row"),
			)
		if not _is_imaging_template(row.observation_template):
			frappe.throw(
				_(
					"Row {0} of the lab requests: {1} is not an imaging exam. Choose lab tests in the "
					"Lab Test column; the Imaging column is for X-ray, ultrasound and other imaging."
				).format(row.idx, frappe.bold(row.observation_template)),
				title=_("Choose it as a lab test"),
			)


def observation_exempt(doc):
	from royce_health_ke.visits import open_visit_for

	if doc.get("inpatient_record"):
		return True
	# before_validate runs before the consultation is linked to its visit (visits.link_encounter)
	visit = doc.get("ke_patient_visit") or open_visit_for(doc.get("patient"), doc.get("encounter_date"))
	return bool(visit) and frappe.db.get_value("Patient Visit", visit, "visit_type") == "Casualty"


def missing_observation(doc):
	"""Labels of the required Observation fields still empty."""
	from royce_health_ke.flow import SETTINGS, setting

	if not setting("observation_before_requests"):
		return []
	meta = frappe.get_meta(DT)
	return [
		_(meta.get_label(field))
		for switch, field in OBSERVATION_FIELDS
		if cint(frappe.db.get_single_value(SETTINGS, switch))
		and meta.has_field(field)
		and not (doc.get(field) or "").strip()
	]


def _observation_gate_on():
	"""The consultation's rules (observation first, diagnosis, pending
	investigations, saving sends the requests) are on, except while installing,
	importing or loading the demo; tests switch them on themselves
	(ke_test_observation_gate), as flow.py's gates."""
	if frappe.flags.in_import or frappe.flags.in_install or frappe.flags.in_migrate or frappe.flags.ke_demo:
		return False
	return not frappe.flags.in_test or bool(frappe.flags.ke_test_observation_gate)


_rules_on = _observation_gate_on

# Diagnosis, pending investigations, saving sends the requests (IT demo, 18 Nov 2026)


def has_diagnosis(doc):
	return bool(
		[d for d in doc.get("diagnosis") or [] if d.get("diagnosis")] or doc.get("codification_table")
	)


def _submitting(doc):
	return doc.docstatus == 1 and getattr(doc, "_action", None) == "submit"


def _setting(field):
	from royce_health_ke.flow import setting

	return setting(field)


def new_drugs(doc):
	"""Drugs to be sent: not ordered yet, and not held in draft (prescribing.py)."""
	return [
		d
		for d in doc.get("drug_prescription") or []
		if (d.get("medication") or d.get("drug_code"))
		and not d.get("medication_request")
		and not d.get("ke_draft")
	]


def _closed(status):
	from royce_health_ke.lab import CLOSED_REQUEST

	return status in CLOSED_REQUEST


def investigation_result(request):
	"""(done, what it is waiting for) of a lab or imaging request."""
	if request.template_dt == LAB_TEMPLATE:
		tests = frappe.get_all(
			"Lab Test", filters={"service_request": request.name, "docstatus": ["<", 2]}, pluck="docstatus"
		)
		return any(t == 1 for t in tests), _("lab result")
	statuses = frappe.get_all(
		"Observation",
		filters={
			"service_request": request.name,
			"parent_observation": ["is", "not set"],
			"docstatus": ["<", 2],
		},
		pluck="ke_exam_status",
	)
	return any(st in ("Reported", "Verified") for st in statuses), _("imaging report")


def pending_investigations(doc):
	"""Lab tests and imaging of this consultation without their result yet:
	placed requests not resulted or cancelled, and rows not sent yet."""
	pending = [
		r.get("lab_test_code") or r.get("observation_template")
		for r in doc.get("lab_test_prescription") or []
		if not r.get("service_request") and (r.get("lab_test_code") or r.get("observation_template"))
	]
	if doc.is_new():
		return pending
	for request in frappe.get_all(
		"Service Request",
		filters={
			"order_group": doc.name,
			"docstatus": 1,
			"template_dt": ["in", (LAB_TEMPLATE, OBS_TEMPLATE)],
		},
		fields=["name", "template_dt", "template_dn", "status"],
	):
		if _closed(request.status):
			continue
		done, _what = investigation_result(request)
		if not done:
			pending.append(request.template_dn)
	return pending


def check_diagnosis(doc, exempt):
	"""Prescribing and completing need a diagnosis (a provisional one will do).
	Lab and imaging may come first: they are often how the diagnosis is made."""
	if exempt or not _setting("diagnosis_required") or has_diagnosis(doc):
		return
	if new_drugs(doc):
		frappe.throw(
			_("Enter the diagnosis on the Diagnosis tab before prescribing (a provisional one will do)."),
			title=_("Diagnosis first"),
		)
	if _submitting(doc):
		frappe.throw(
			_("Enter the diagnosis on the Diagnosis tab before completing the consultation."),
			title=_("Diagnosis first"),
		)


def check_nothing_pending(doc):
	"""A consultation is completed once its lab and imaging results are in
	(strict: cancel a request the patient won't do)."""
	if not _submitting(doc) or doc.get("inpatient_record"):
		return
	# admitted from this consultation: the results follow the patient to the ward
	if frappe.db.exists(
		"Inpatient Record",
		{"admission_encounter": doc.name, "status": ["not in", ("Discharged", "Cancelled")]},
	):
		return
	pending = pending_investigations(doc)
	if pending:
		frappe.throw(
			_(
				"These requests have no result yet: {0}. Complete the consultation once their results are "
				"in, or cancel a request the patient won't do (Requests tab, Cancel Request). To keep the "
				"consultation open while you wait, use Send Requests."
			).format(", ".join(frappe.bold(p) for p in pending)),
			title=_("Results pending"),
		)


def saving_sends(doc, exempt):
	"""Saving sends the new requests (Kenya Health Settings > Saving the
	consultation sends its requests): cash ones go on the visit's draft bill,
	insured ones straight to their service point. Without the observation, the
	draft is saved and the requests wait."""
	if _submitting(doc) or doc.docstatus != 0 or doc.is_new() or cint(doc.get("submit_orders_on_save")):
		return
	if not _setting("save_sends_requests") or not new_orders(doc):
		return
	missing = [] if exempt else missing_observation(doc)
	if missing:
		frappe.msgprint(
			_("Saved, but the requests were not sent: record the observation first ({0}).").format(
				", ".join(missing)
			),
			indicator="orange",
			alert=True,
		)
		return
	doc.submit_orders_on_save = 1


def before_validate(doc, method=None):
	"""Patient Encounter before_validate (before Marley places the orders)."""
	from royce_health_ke.prescribing import check_no_drafts

	check_lab_rows(doc)
	check_no_drafts(doc)
	if not _rules_on():
		return
	cancel_removed_requests(doc)
	exempt = observation_exempt(doc)
	# in the order of the tabs: observation, requests, diagnosis, complete
	saving_sends(doc, exempt)
	if _placing_orders(doc) and new_orders(doc) and not exempt:
		missing = missing_observation(doc)
		if missing:
			frappe.throw(
				_("Record the observation before requesting tests or prescribing. Still empty: {0}.").format(
					", ".join(missing)
				),
				title=_("Observation first"),
			)
	check_diagnosis(doc, exempt)
	check_nothing_pending(doc)


def after_insert(doc, method=None):
	"""A new consultation saved with requests: Marley places orders only on a
	saved one, so save once more to send them (saving_sends)."""
	if not _rules_on() or doc.flags.ke_sending or not _setting("save_sends_requests") or not new_orders(doc):
		return
	doc.flags.ke_sending = True
	try:
		doc.save()
	finally:
		doc.flags.ke_sending = False


# Cancel Request: a lab, imaging or procedure request not started is
# withdrawn (Marley's "revoked"): off its worklist and off a draft bill. A
# paid one is noted on the visit for the Cashier (refund or credit).


def request_started(request):
	if frappe.db.exists("Lab Test", {"service_request": request, "docstatus": ["<", 2]}):
		return True
	if frappe.db.exists(
		"Observation",
		{
			"service_request": request,
			"docstatus": ["<", 2],
			"ke_exam_status": ["in", ("Performed", "Reported", "Verified")],
		},
	):
		return True
	return bool(frappe.db.exists("Clinical Procedure", {"service_request": request, "docstatus": ["<", 2]}))


def withdraw_request(name, reason):
	"""Revoke a request not started; take it off a draft bill. Returns a note
	for the Cashier when it was already paid or on a submitted bill."""
	from royce_health_ke import payment_status

	sr = frappe.get_doc("Service Request", name)
	if _closed(sr.status):
		return None
	if request_started(name):
		frappe.throw(
			_("{0} has already started (sample taken or exam done): it can't be cancelled.").format(
				frappe.bold(sr.template_dn)
			),
			title=_("Already started"),
		)
	note = None
	for line in frappe.get_all(
		"Sales Invoice Item",
		filters={"reference_dt": "Service Request", "reference_dn": name, "docstatus": ["<", 2]},
		fields=["name", "parent", "docstatus"],
	):
		if line.docstatus == 0:
			si = frappe.get_doc("Sales Invoice", line.parent)
			si.items = [r for r in si.items if r.name != line.name]
			si.flags.ignore_permissions = True
			if si.items:
				si.save()
			else:
				si.delete()
		else:
			note = _(
				"{0} was cancelled after it was billed on {1}: refund it or keep it as the patient's credit."
			).format(sr.template_dn, line.parent)
	frappe.db.set_value(
		"Service Request",
		name,
		{"status": "revoked-Request Status", "ke_cancel_reason": (reason or "")[:140]},
	)
	payment_status.refresh("Service Request", name)
	visit = sr.get("ke_patient_visit") or (
		sr.order_group and frappe.db.get_value("Patient Encounter", sr.order_group, "ke_patient_visit")
	)
	if note and visit:
		frappe.get_doc("Patient Visit", visit).add_comment("Comment", note)
	return note


def cancel_removed_requests(doc):
	"""Rows deleted from a saved consultation: their requests are withdrawn
	(refused when started)."""
	if doc.is_new() or doc.docstatus != 0:
		return
	before = doc.get_doc_before_save()
	if not before:
		return
	kept = {r.get("service_request") for t in ORDER_TABLES for r in doc.get(t) or []}
	for table in ORDER_TABLES:
		for row in before.get(table) or []:
			request = row.get("service_request")
			if request and request not in kept:
				note = withdraw_request(request, _("Removed from the consultation"))
				if note:
					frappe.msgprint(note, indicator="orange", alert=True)


@frappe.whitelist()
def cancel_request(request: str, reason: str):
	"""Cancel Request (Requests tab): withdraw a request the patient won't do."""
	sr = frappe.get_doc("Service Request", request)
	if not sr.order_group:
		frappe.throw(_("This request is not from a consultation."))
	frappe.get_doc(DT, sr.order_group).check_permission("write")
	if not (reason or "").strip():
		frappe.throw(_("Give a reason."))
	return {"note": withdraw_request(request, reason.strip())}


def unpriced(doc):
	"""Requests of this consultation with no price for the patient (the
	scheme's pricebook, else the cash price list): the bill can't charge them,
	so the doctor is told at once (IT demo: a request "didn't go" until its
	price was added)."""
	from royce_health_ke import fees

	visit = doc.get("ke_patient_visit")
	v = visit and frappe.db.get_value(
		"Patient Visit", visit, ["payment_method", "insurance_policy", "company"], as_dict=True
	)
	policy = v.insurance_policy if v and v.payment_method != "Cash" else None
	company = (v and v.company) or doc.get("company")
	out = []
	for request in _requests(doc):
		if request.template_dt not in (
			LAB_TEMPLATE,
			OBS_TEMPLATE,
			"Clinical Procedure Template",
			"Therapy Type",
		):
			continue
		billable, item = frappe.db.get_value(
			request.template_dt, request.template_dn, ["is_billable", "item"]
		) or (0, None)
		if not cint(billable):
			continue
		if not item or not fees.price(item, company, policy):
			out.append(request.template_dn)
	return out


# Send requests / complete


def _encounter(name, perm="write"):
	doc = frappe.get_doc(DT, name)
	doc.check_permission(perm)
	return doc


@frappe.whitelist()
def send_requests(encounter: str):
	"""Place the requests now; the consultation stays open for the results."""
	doc = _encounter(encounter)
	if doc.docstatus != 0:
		frappe.throw(_("This consultation is already completed."))
	if not (doc.lab_test_prescription or doc.procedure_prescription or doc.therapies):
		frappe.throw(_("Add a lab test, imaging exam or procedure to the requests first."))
	doc.submit_orders_on_save = 1
	doc.save()
	if doc.get("ke_patient_visit"):
		visit_bill.refresh_bill_status(doc.ke_patient_visit)
	return next_stations(doc)


@frappe.whitelist()
def complete(encounter: str):
	"""Submit the consultation (any orders not sent yet are placed)."""
	doc = _encounter(encounter, "submit")
	if doc.docstatus == 0:
		doc.submit()
	elif doc.docstatus == 2:
		frappe.throw(_("This consultation was cancelled."))
	return next_stations(doc)


def _kind(request):
	if request.template_dt == LAB_TEMPLATE:
		return visit_bill.LAB
	if request.template_dt == OBS_TEMPLATE:
		from royce_health_ke.radiology import IMAGING

		category = frappe.db.get_value(OBS_TEMPLATE, request.template_dn, "observation_category")
		return visit_bill.RADIOLOGY if category == IMAGING else visit_bill.LAB
	return None


STATION = {visit_bill.LAB: "Laboratory", visit_bill.RADIOLOGY: "Radiology", None: "Procedure Room"}


def _requests(doc):
	return frappe.get_all(
		"Service Request",
		filters={"order_group": doc.name, "docstatus": 1},
		fields=["name", "template_dt", "template_dn", "status", "ke_service_point"],
	)


def next_stations(doc):
	"""Where the patient goes next, the suggested place first."""
	visit = doc.get("ke_patient_visit")
	status = visit and frappe.db.get_value("Patient Visit", visit, "status")
	stations, unpaid = [], 0
	from royce_health_ke.routing import service_point

	for request in _requests(doc):
		kind = _kind(request)
		if kind and visit_bill.request_awaiting_payment(kind, request.name):
			unpaid += 1
		# the request type's service point (routing.py), else where its kind goes
		stations.append(service_point(request) or STATION[kind])
	drugs = frappe.get_all(
		"Medication Request", filters={"order_group": doc.name, "docstatus": 1}, pluck="name"
	)
	if drugs:
		stations.append("Pharmacy")
		unpaid += sum(1 for mr in drugs if visit_bill.drug_awaiting_payment(mr))
	stations = list(dict.fromkeys(stations))
	if unpaid:
		stations.insert(0, "Cashier")
	return {
		"visit": visit if status == "Open" else None,
		"stations": stations,
		"unpaid": unpaid,
		"unpriced": unpriced(doc),
		"completed": doc.docstatus == 1,
	}


# Latest vital signs, at the top of the consultation (IT demo, 17 Nov 2026)

VITALS = (
	"name",
	"signs_date",
	"signs_time",
	"docstatus",
	"temperature",
	"pulse",
	"respiratory_rate",
	"bp",
	"bp_systolic",
	"bp_diastolic",
	"ke_spo2",
	"weight",
	"ke_height_cm",
	"bmi",
	"ke_vitals_status",
	"ke_vitals_flags",
)


@frappe.whitelist()
def latest_vitals(patient: str, visit: str | None = None) -> dict | None:
	"""The visit's latest vital signs, else the patient's within the last day."""
	if not frappe.has_permission("Vital Signs", "read"):
		return None
	frappe.has_permission("Patient", "read", patient, throw=True)
	filters = {"patient": patient, "docstatus": ["<", 2]}
	if visit and frappe.db.exists("Vital Signs", {**filters, "ke_patient_visit": visit}):
		filters["ke_patient_visit"] = visit
	else:
		filters["signs_date"] = [">=", frappe.utils.add_days(frappe.utils.nowdate(), -1)]
	rows = frappe.get_all(
		"Vital Signs",
		filters=filters,
		fields=list(VITALS),
		order_by="signs_date desc, signs_time desc, creation desc",
		limit=1,
	)
	return rows[0] if rows else None


# Results panel


def _lab_rows(lab_test):
	from royce_health_ke.printing import flag

	t = frappe.get_doc("Lab Test", lab_test)
	rows = [
		{
			"name": r.lab_test_event or r.lab_test_name,
			"value": r.result_value,
			"uom": r.lab_test_uom,
			"range": r.normal_range,
			"flag": flag(r.result_value, r.normal_range, t.patient_sex) if r.result_value else "",
		}
		for r in t.normal_test_items
		if r.result_value or r.lab_test_event
	]
	rows += [
		{"name": r.lab_test_particulars, "value": r.result_value, "uom": "", "range": "", "flag": ""}
		for r in t.descriptive_test_items
	]
	return rows


def _lab_status(t):
	if t.docstatus == 1:
		return _("Validated")
	from royce_health_ke.lab import has_results

	if has_results(frappe.get_doc("Lab Test", t.name)):
		return _("Results entered, awaiting validation")
	if t.ke_sample_collected_at:
		return _("Sample collected")
	return _("At the lab")


IMAGING_STATUS = {
	"Requested": _("Waiting at radiology"),
	"Performed": _("Done, awaiting the report"),
	"Reported": _("Reported"),
	"Verified": _("Verified"),
}


@frappe.whitelist()
def panel(encounter: str):
	"""The Results tab (this visit's results) and the Prescription tab's
	pharmacy notes (drugs sent back to the doctor)."""
	doc = _encounter(encounter, "read")
	visit = doc.get("ke_patient_visit")
	encounters = (
		frappe.get_all(DT, filters={"ke_patient_visit": visit, "docstatus": ["<", 2]}, pluck="name")
		if visit
		else [doc.name]
	) or [doc.name]
	requests = frappe.get_all(
		"Service Request",
		filters={"order_group": ["in", encounters], "docstatus": 1},
		fields=[
			"name",
			"template_dt",
			"template_dn",
			"order_description",
			"creation",
			"status",
			"ke_cancel_reason",
		],
		order_by="creation",
	)
	results, seen_requests = [], set()
	for request in requests:
		kind = _kind(request)
		if request.template_dt not in (LAB_TEMPLATE, OBS_TEMPLATE):
			continue
		seen_requests.add(request.name)
		row = {"request": request.name, "test": request.template_dn, "kind": kind}
		if _closed(request.status):
			row["status"] = _("Cancelled: {0}").format(request.ke_cancel_reason or "")
			row["cancelled"] = 1
			results.append(row)
			continue
		# not started yet: the doctor can cancel it (Cancel Request)
		row["cancellable"] = int(doc.docstatus == 0 and not request_started(request.name))
		test = frappe.db.get_value(
			"Lab Test",
			{"service_request": request.name, "docstatus": ["<", 2]},
			["name", "docstatus", "ke_sample_collected_at", "ke_seen_at"],
			as_dict=True,
		)
		obs = not test and frappe.db.get_value(
			"Observation",
			{"service_request": request.name, "parent_observation": ["is", "not set"], "docstatus": ["<", 2]},
			["name", "ke_exam_status", "result", "ke_impression", "ke_seen_at"],
			as_dict=True,
		)
		if test:
			row.update(
				doctype="Lab Test", name=test.name, status=_lab_status(test), seen=bool(test.ke_seen_at)
			)
			if test.docstatus == 1:
				row["rows"] = _lab_rows(test.name)
		elif obs and kind == visit_bill.RADIOLOGY:
			row.update(
				doctype="Observation",
				name=obs.name,
				status=IMAGING_STATUS.get(obs.ke_exam_status, obs.ke_exam_status),
				seen=bool(obs.ke_seen_at),
			)
			if obs.ke_exam_status in ("Reported", "Verified"):
				row.update(findings=obs.result, impression=obs.ke_impression)
		elif kind and visit_bill.request_awaiting_payment(kind, request.name):
			row["status"], row["awaiting_payment"] = _("Awaiting payment at the Cashier"), 1
		else:
			row["status"] = (
				_("Waiting at radiology") if kind == visit_bill.RADIOLOGY else _("Waiting at the lab")
			)
		results.append(row)
	if visit:
		# Tests the lab added to the visit itself (walk-in requests, add-ons).
		for t in frappe.get_all(
			"Lab Test",
			filters={"ke_patient_visit": visit, "docstatus": ["<", 2], "service_request": ["is", "not set"]},
			fields=["name", "lab_test_name", "docstatus", "ke_sample_collected_at", "ke_seen_at"],
		):
			row = {
				"doctype": "Lab Test",
				"name": t.name,
				"test": t.lab_test_name,
				"kind": visit_bill.LAB,
				"status": _lab_status(t),
				"seen": bool(t.ke_seen_at),
			}
			if t.docstatus == 1:
				row["rows"] = _lab_rows(t.name)
			results.append(row)
	sent_back = frappe.get_all(
		"Medication Request",
		filters={"order_group": ["in", encounters], "docstatus": 1, "ke_pharmacy_status": "Sent Back"},
		fields=["name", "medication", "ke_pharmacy_note as note", "modified"],
	)
	return {"results": results, "sent_back": sent_back, "can_complete": cint(doc.docstatus == 0)}


# Vital signs history (Bethesda proposals, 18 Nov 2026): on a revisit every
# earlier reading is there beside today's, with the trend.

HISTORY_LIMIT = 100


@frappe.whitelist()
def vitals_history(patient: str, limit: int = HISTORY_LIMIT) -> list:
	"""The patient's vital signs, oldest first (for the trends), cancelled ones left out."""
	if not frappe.has_permission("Vital Signs", "read"):
		return []
	frappe.has_permission("Patient", "read", patient, throw=True)
	rows = frappe.get_all(
		"Vital Signs",
		filters={"patient": patient, "docstatus": ["<", 2]},
		fields=[*VITALS, "ke_patient_visit"],
		order_by="signs_date desc, signs_time desc, creation desc",
		limit=min(cint(limit) or HISTORY_LIMIT, 500),
	)
	return list(reversed(rows))
