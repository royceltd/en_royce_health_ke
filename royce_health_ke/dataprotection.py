# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""The Data Protection Act's duties to patients, kept as records (v0.46).

- Consent at registration: the patient is told how their information is
  used (privacy notice) and says yes or no to SMS. Who gave it (the patient,
  or a parent or guardian), when, and which staff member recorded it are
  stamped on the patient; every change is kept in the Patient Consent Log,
  which is never edited.
- Data Subject Requests: a patient asks for a copy of their record, a
  correction, deletion, restriction or to withdraw consent. Each is logged
  with its reply due date (Kenya Health Settings > Data Protection). Access
  requests export the whole record (a readable PDF and a machine-readable
  JSON file) attached to the request.
- Data Breach register: what happened, the risk, containment, and notice to
  the Data Commissioner within 72 hours of discovery (section 43).
- A daily alert names overdue requests and breaches not yet notified, and the
  Compliance Check shows them.

Response times are settings, not code: the defaults follow the Data
Protection (General) Regulations, 2021; the hospital's Data Protection
Officer confirms them."""

import json

import frappe
from frappe import _
from frappe.utils import add_days, add_to_date, cint, get_datetime, getdate, now_datetime

SETTINGS = "Kenya Health Settings"
DPO_ROLE = "Data Protection Officer"
MANAGER_ROLES = ("Healthcare Administrator", "System Manager", DPO_ROLE)
BREACH_HOURS = 72
ACCESS = "Access (copy of the record)"
CORRECTION = "Correction"
CLOSED = ("Completed", "Refused")
PRIVACY, SMS = "Privacy notice", "SMS"


def _setting(field, default=None):
	value = frappe.db.get_single_value(SETTINGS, field)
	return value if value not in (None, "") else default


def ensure_role():
	from royce_health_ke.privacy import ensure_role as make

	make(DPO_ROLE)


# Consent at registration


def _rules_on():
	"""On, except while installing, importing or loading the demo; tests switch
	it on themselves (ke_test_consent)."""
	if frappe.flags.in_import or frappe.flags.in_install or frappe.flags.in_migrate or frappe.flags.ke_demo:
		return False
	return not frappe.flags.in_test or bool(frappe.flags.ke_test_consent)


def patient_validate(doc, method=None):
	"""Patient validate: a new patient is told how their data is used
	(Kenya Health Settings > Consent at registration); any change to the
	consent is stamped with when and by whom."""
	if (
		doc.is_new()
		and _rules_on()
		and not doc.flags.ignore_consent_check
		and cint(_setting("consent_at_registration", 0))
		and not cint(doc.get("ke_privacy_notice"))
	):
		frappe.throw(
			_(
				"Tell the patient how their information is used (the privacy notice), then tick "
				"Privacy Notice Given. Also ask whether they agree to SMS."
			),
			title=_("Consent at registration"),
		)
	changes = consent_changes(doc)
	if changes:
		doc.ke_consent_at = now_datetime()
		doc.ke_consent_recorded_by = frappe.session.user
		doc.flags.ke_consent_changes = changes


def consent_changes(doc):
	"""[(purpose, decision)] changed by this save."""
	before = None if doc.is_new() else doc.get_doc_before_save()
	out = []
	for field, purpose in (("ke_privacy_notice", PRIVACY), ("ke_sms_consent", SMS)):
		now = cint(doc.get(field))
		was = cint(before.get(field)) if before else 0
		if now != was:
			out.append((purpose, "Given" if now else "Withdrawn"))
	return out


def patient_on_update(doc, method=None):
	"""Patient on_update: the consent history (never changed)."""
	for purpose, decision in doc.flags.ke_consent_changes or []:
		frappe.get_doc(
			{
				"doctype": "Patient Consent Log",
				"patient": doc.name,
				"purpose": purpose,
				"decision": decision,
				"given_by": doc.get("ke_consent_given_by"),
				"relation": doc.get("ke_consent_relation"),
				"recorded_by": frappe.session.user,
				"recorded_at": doc.get("ke_consent_at") or now_datetime(),
			}
		).insert(ignore_permissions=True)
	doc.flags.ke_consent_changes = None


# Data subject requests


def due_date(request_type, received_on):
	days = (
		cint(_setting("dsr_correction_days", 14))
		if request_type != ACCESS
		else cint(_setting("dsr_access_days", 7))
	)
	return add_days(getdate(received_on), days)


def validate_request(doc):
	if doc.is_new() and not doc.received_by:
		doc.received_by = frappe.session.user
	doc.due_date = due_date(doc.request_type, doc.received_on or now_datetime())
	if doc.status in CLOSED:
		if doc.status == "Completed" and not (doc.resolution or "").strip():
			frappe.throw(_("Say what was done before completing the request."))
		if doc.status == "Refused" and not (doc.refusal_reason or "").strip():
			frappe.throw(_("Give the reason for refusing."))
		if doc.request_type == ACCESS and doc.status == "Completed" and not doc.export_file:
			frappe.throw(_("Export the patient's record (Export Patient Record) before completing."))
		if not doc.completed_on:
			doc.completed_on = now_datetime()
			doc.completed_by = frappe.session.user
	else:
		doc.completed_on = doc.completed_by = None


def _check_manager():
	if not set(MANAGER_ROLES) & set(frappe.get_roles()):
		frappe.throw(
			_("Only the Data Protection Officer or an administrator exports a patient's record."),
			frappe.PermissionError,
		)


def _rows(doctype, filters, fields, order_by="creation asc"):
	return frappe.get_all(doctype, filters=filters, fields=fields, order_by=order_by)


def record_data(patient):
	"""The patient's whole record as plain data (JSON-ready)."""
	p = frappe.get_doc("Patient", patient)
	skip = {
		"owner",
		"modified_by",
		"docstatus",
		"idx",
		"doctype",
		"image",
		"_user_tags",
		"_comments",
		"_assign",
		"_liked_by",
	}
	data = {
		"exported_at": str(now_datetime()),
		"facility": frappe.db.get_single_value("Global Defaults", "default_company"),
		"patient": {
			"patient_number": p.name,
			**{
				k: v
				for k, v in p.as_dict(no_default_fields=True).items()
				if k not in skip and v not in (None, "", 0)
			},
		},
		"consents": _rows(
			"Patient Consent Log",
			{"patient": patient},
			["purpose", "decision", "given_by", "relation", "recorded_at"],
		),
		"visits": _rows(
			"Patient Visit",
			{"patient": patient},
			[
				"name",
				"visit_date",
				"visit_type",
				"payment_method",
				"insurance_payor",
				"status",
				"practitioner_name",
			],
		),
		"vital_signs": _rows(
			"Vital Signs",
			{"patient": patient, "docstatus": ["<", 2]},
			[
				"signs_date",
				"signs_time",
				"temperature",
				"pulse",
				"respiratory_rate",
				"bp",
				"ke_spo2",
				"weight",
				"ke_height_cm",
				"bmi",
			],
		),
	}
	encounters = []
	for name in frappe.get_all(
		"Patient Encounter",
		filters={"patient": patient, "docstatus": ["<", 2]},
		pluck="name",
		order_by="creation",
	):
		e = frappe.get_doc("Patient Encounter", name)
		encounters.append(
			{
				"consultation": e.name,
				"date": str(e.encounter_date),
				"doctor": e.practitioner_name,
				**{
					field: e.get(field)
					for field in (
						"ke_chief_complaint",
						"ke_hpi",
						"ke_review_of_systems",
						"ke_obs_gynae",
						"ke_examination",
						"encounter_comment",
					)
					if e.get(field)
				},
				"diagnoses": [
					{
						"diagnosis": d.diagnosis,
						"icd11": d.get("ke_icd11_code")
						and frappe.db.get_value("Code Value", d.ke_icd11_code, "code_value"),
					}
					for d in e.diagnosis
				],
				"medicines": [
					{
						"medicine": d.medication or d.drug_code,
						"dose": d.get("ke_dose"),
						"dose_unit": d.get("ke_dose_uom"),
						"frequency": d.dosage,
						"duration": d.period,
						"route": d.get("ke_route"),
						"instructions": d.comment,
					}
					for d in e.drug_prescription
				],
				"requests": [r.lab_test_code or r.observation_template for r in e.lab_test_prescription]
				+ [r.procedure for r in e.procedure_prescription],
			}
		)
	data["consultations"] = encounters
	labs = []
	for name in frappe.get_all(
		"Lab Test", filters={"patient": patient, "docstatus": 1}, pluck="name", order_by="creation"
	):
		t = frappe.get_doc("Lab Test", name)
		labs.append(
			{
				"test": t.lab_test_name or t.template,
				"date": str(t.result_date or t.date or ""),
				"results": [
					{
						"name": r.lab_test_event or r.lab_test_name,
						"value": r.result_value,
						"unit": r.lab_test_uom,
						"range": r.normal_range,
					}
					for r in t.normal_test_items
					if r.result_value
				]
				+ [
					{"name": r.lab_test_particulars, "value": r.result_value}
					for r in t.descriptive_test_items
				],
			}
		)
	data["lab_results"] = labs
	data["imaging_reports"] = _rows(
		"Observation",
		{
			"patient": patient,
			"parent_observation": ["is", "not set"],
			"ke_exam_status": ["in", ("Reported", "Verified")],
		},
		["observation_template", "posting_date", "time_of_result", "result", "ke_impression"],
	)
	data["admissions"] = _rows(
		"Inpatient Record",
		{"patient": patient},
		["name", "admitted_datetime", "discharge_datetime", "status"],
	)
	customer = p.get("customer")
	data["bills"] = (
		_rows(
			"Sales Invoice",
			{"customer": customer, "patient": patient, "docstatus": 1},
			["name", "posting_date", "grand_total", "outstanding_amount"],
		)
		if customer
		else []
	)
	return data


def _attach(request, file_name, content):
	f = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": file_name,
			"attached_to_doctype": "Data Subject Request",
			"attached_to_name": request,
			"is_private": 1,
			"content": content,
		}
	)
	f.save(ignore_permissions=True)
	return f.file_url


@frappe.whitelist()
def export_record(request: str) -> dict:
	"""Access request: the patient's record as a JSON file (machine readable)
	and a PDF (the Patient File), attached to the request, private."""
	_check_manager()
	doc = frappe.get_doc("Data Subject Request", request)
	doc.check_permission("write")
	if doc.request_type != ACCESS:
		frappe.throw(_("Only an access request exports the record."))
	stamp = now_datetime().strftime("%Y%m%d-%H%M")
	json_url = _attach(
		doc.name,
		f"{doc.patient}-record-{stamp}.json",
		json.dumps(record_data(doc.patient), indent=1, default=str).encode(),
	)
	pdf_url = None
	frappe.flags.ke_record_export = True
	try:
		pdf = frappe.get_print("Patient", doc.patient, "Patient File", as_pdf=True)
		pdf_url = _attach(doc.name, f"{doc.patient}-record-{stamp}.pdf", pdf)
	except Exception:
		frappe.log_error(
			title=_("Patient record PDF not made"),
			reference_doctype="Data Subject Request",
			reference_name=doc.name,
		)
	finally:
		frappe.flags.ke_record_export = False
	doc.export_file = pdf_url or json_url
	if doc.status == "Open":
		doc.status = "In Progress"
	doc.flags.ignore_permissions = True
	doc.save()
	_log_export(doc.patient, doc.name)
	return {"json": json_url, "pdf": pdf_url}


def _log_export(patient, request):
	frappe.get_doc(
		{
			"doctype": "Patient Record Access",
			"patient": patient,
			"patient_name": frappe.db.get_value("Patient", patient, "patient_name"),
			"reference_doctype": "Data Subject Request",
			"reference_name": request,
			"action": "Export",
			"user": frappe.session.user,
			"full_name": frappe.utils.get_fullname(frappe.session.user),
			"ip_address": getattr(frappe.local, "request_ip", None),
			"accessed_at": now_datetime(),
		}
	).insert(ignore_permissions=True)


# Breach register


def validate_breach(doc):
	if doc.is_new() and not doc.reported_by:
		doc.reported_by = frappe.session.user
	doc.odpc_due = add_to_date(get_datetime(doc.discovered_at), hours=BREACH_HOURS)
	if not cint(doc.odpc_notification_required) and not (doc.not_notified_reason or "").strip():
		frappe.throw(_("Say why the Data Commissioner is not notified."))
	if doc.status == "Closed":
		if cint(doc.odpc_notification_required) and not doc.odpc_notified_at:
			frappe.throw(_("Record when the Data Commissioner (ODPC) was notified before closing."))
		if not (doc.lessons or "").strip():
			frappe.throw(_("Say what changes so it doesn't happen again before closing."))
		doc.closed_at = doc.closed_at or now_datetime()
	else:
		doc.closed_at = None


# Overdue: alerts and the Compliance Check


def overdue_requests():
	return frappe.get_all(
		"Data Subject Request",
		filters={"status": ["not in", CLOSED], "due_date": ["<", getdate()]},
		pluck="name",
	)


def unnotified_breaches(within_hours=0):
	"""Breaches to notify whose 72 hours are over (or end within `within_hours`)."""
	return frappe.get_all(
		"Data Breach",
		filters={
			"odpc_notification_required": 1,
			"odpc_notified_at": ["is", "not set"],
			"odpc_due": ["<", add_to_date(now_datetime(), hours=within_hours)],
		},
		pluck="name",
	)


def _managers():
	users = frappe.get_all(
		"Has Role",
		filters={"role": ["in", ("Healthcare Administrator", DPO_ROLE)], "parenttype": "User"},
		pluck="parent",
		distinct=True,
	)
	dpo = _setting("data_protection_officer")
	if dpo:
		users.append(dpo)
	return [
		u
		for u in dict.fromkeys(users)
		if u not in ("Administrator", "Guest") and frappe.db.get_value("User", u, "enabled")
	]


def notify_overdue():
	"""Daily: overdue patient requests, and breaches whose 72 hours end within a day."""
	requests = overdue_requests()
	breaches = unnotified_breaches(within_hours=24)
	messages = []
	if requests:
		messages.append(
			(
				"Data Subject Request",
				_("{0} patient data request(s) past their reply date").format(len(requests)),
			)
		)
	if breaches:
		messages.append(
			(
				"Data Breach",
				_("{0} data breach(es) to notify to the Data Commissioner within 72 hours").format(
					len(breaches)
				),
			)
		)
	for user in _managers():
		for doctype, subject in messages:
			frappe.get_doc(
				{
					"doctype": "Notification Log",
					"for_user": user,
					"type": "Alert",
					"document_type": doctype,
					"subject": subject,
				}
			).insert(ignore_permissions=True)


def compliance_rows(make_row):
	health = _("Kenya Health Settings > Data Protection")
	consent = cint(_setting("consent_at_registration", 0))
	dpo = _setting("data_protection_officer")
	requests = overdue_requests()
	breaches = unnotified_breaches()
	return [
		make_row(
			_("Data protection"),
			_("Patients are told how their data is used, and asked about SMS, at registration"),
			bool(consent),
			_("on") if consent else _("off"),
			"on",
			health,
		),
		make_row(
			_("Data protection"),
			_("A Data Protection Officer is named"),
			bool(dpo),
			dpo or _("none"),
			_("a named user"),
			health,
			advice=True,
		),
		make_row(
			_("Data protection"),
			_("Patients' requests (copy, correction, deletion) answered on time"),
			not requests,
			", ".join(requests) or _("none overdue"),
			_("none overdue"),
			_("Data Subject Request list"),
		),
		make_row(
			_("Data protection"),
			_("Data breaches notified to the Data Commissioner within 72 hours"),
			not breaches,
			", ".join(breaches) or _("none late"),
			_("none late"),
			_("Data Breach register"),
		),
	]
