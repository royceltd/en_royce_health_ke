# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Patient SMS, sent through royce_talk (RoyceTalk) when that app is installed.

Four ways a patient gets an SMS:
  - a staff member sends one from the patient's record (Send SMS button);
  - a Patient SMS Campaign to patients picked by filters (age, sex, visits,
    facility, insurer, active pregnancy);
  - an appointment reminder the day before (hourly job, daytime only);
  - a "results ready" message when a lab test is submitted.

Consent: campaigns, reminders and results messages only go to patients with
"Agrees to receive SMS" (ke_sms_consent) ticked. A message typed by staff on one
patient's record is a deliberate act and is allowed without it, with a warning.

Privacy: the automatic messages never carry clinical detail (no results, no
diagnosis), only that something is due or ready. Kenya's Data Protection Act
treats health data as sensitive, and a phone screen is not private.

royce_talk stays optional: nothing here imports it at module level, and every
entry point checks `available()` first.
"""

import frappe
from frappe import _
from frappe.utils import add_to_date, cint, get_datetime, getdate, now_datetime, today

FIRST_SEND_HOUR = 7
LAST_SEND_HOUR = 20

DEFAULT_REMINDER = (
	"Dear {{ first_name }}, this is a reminder of your appointment at {{ facility }} "
	"on {{ date }} at {{ time }}. To reschedule, call {{ phone }}."
)
DEFAULT_LAB = (
	"Dear {{ first_name }}, your laboratory results are ready at {{ facility }}. "
	"Please see your clinician. Enquiries: {{ phone }}."
)


def available() -> bool:
	return "royce_talk" in frappe.get_installed_apps()


def enabled() -> bool:
	return available() and bool(frappe.db.get_single_value("Bulk SMS Settings", "enabled"))


def _require():
	if not available():
		frappe.throw(_("SMS needs the Bulk SMS app (royce_talk) installed on this site."))
	if not enabled():
		frappe.throw(_("SMS is switched off. Enable it in Bulk SMS Settings first."))


def settings():
	return frappe.get_cached_doc("Kenya Health Settings")


def facility_for_unit(service_unit: str | None) -> str | None:
	"""The Health Facility whose service unit tree contains this unit."""
	if not service_unit:
		return None
	lft, rgt = frappe.db.get_value("Healthcare Service Unit", service_unit, ["lft", "rgt"]) or (None, None)
	if lft is None:
		return None
	for name, unit in frappe.get_all(
		"Health Facility", filters={"disabled": 0}, fields=["name", "healthcare_service_unit"], as_list=True
	):
		if not unit:
			continue
		ulft, urgt = frappe.db.get_value("Healthcare Service Unit", unit, ["lft", "rgt"]) or (None, None)
		if ulft is not None and ulft <= lft and rgt <= urgt:
			return name
	return None


def facility_units(facility: str) -> list[str]:
	"""Every service unit under a facility (its own unit included)."""
	unit = frappe.db.get_value("Health Facility", facility, "healthcare_service_unit")
	if not unit:
		return []
	lft, rgt = frappe.db.get_value("Healthcare Service Unit", unit, ["lft", "rgt"])
	return frappe.get_all(
		"Healthcare Service Unit", filters={"lft": [">=", lft], "rgt": ["<=", rgt]}, pluck="name"
	)


def _context(patient: str, company: str | None = None, service_unit: str | None = None) -> dict:
	p = frappe.db.get_value("Patient", patient, ["first_name", "patient_name"], as_dict=True) or {}
	facility = facility_for_unit(service_unit)
	phone = None
	if facility:
		phone = frappe.db.get_value("Health Facility", facility, "phone")
	if not company:
		company = frappe.defaults.get_user_default("company") or frappe.db.get_single_value(
			"Global Defaults", "default_company"
		)
	if not phone and company:
		phone = frappe.db.get_value("Company", company, "phone_no")
	return {
		"first_name": p.get("first_name") or p.get("patient_name") or "",
		"patient_name": p.get("patient_name") or "",
		"facility": facility or company or "",
		"hospital": company or "",
		"phone": phone or "",
	}


def render(template: str, context: dict) -> str:
	return " ".join(frappe.render_template(template, context).split())


# Single patient (form button) ------------------------------------------------


@frappe.whitelist()
def patient_sms_info(patient: str) -> dict:
	"""What the Send SMS dialog needs: the number, consent, and whether SMS is on."""
	frappe.has_permission("Patient", "read", patient, throw=True)
	p = frappe.db.get_value("Patient", patient, ["mobile", "ke_sms_consent"], as_dict=True)
	info = {
		"available": available(),
		"enabled": enabled(),
		"mobile": p.mobile if p else None,
		"consent": cint(p.ke_sms_consent) if p else 0,
		"sent": 0,
	}
	if available():
		info["sent"] = frappe.db.count(
			"Bulk SMS Log", {"reference_doctype": "Patient", "reference_name": patient}
		)
		info.update(_context(patient))
	return info


@frappe.whitelist(methods=["POST"])
def send_to_patient(patient: str, message: str) -> dict:
	"""Send one SMS to one patient, typed by a staff member on the patient's record."""
	frappe.has_permission("Patient", "write", patient, throw=True)
	_require()
	message = (message or "").strip()
	if not message:
		frappe.throw(_("Type a message first."))
	mobile = frappe.db.get_value("Patient", patient, "mobile")
	if not mobile:
		frappe.throw(_("This patient has no mobile number. Add one to the patient's record first."))

	from royce_talk.bulk_sms.utils import send_single_sms

	return send_single_sms(
		phone_number=mobile,
		text_message=message,
		reference_doctype="Patient",
		reference_name=patient,
	)


# Campaigns -------------------------------------------------------------------


def campaign_recipients(doc) -> list[dict]:
	"""Patients matching a Patient SMS Campaign's filters, with consent and a
	mobile number. Re-run at preview and at send time: consent may change."""
	conditions = [
		"p.status = 'Active'",
		"p.ke_sms_consent = 1",
		"ifnull(p.mobile, '') != ''",
	]
	values = {}

	if doc.get("sex"):
		conditions.append("p.sex = %(sex)s")
		values["sex"] = doc.sex
	if cint(doc.get("age_from")):
		conditions.append("p.dob <= %(born_by)s")
		values["born_by"] = add_to_date(today(), years=-cint(doc.age_from))
	if cint(doc.get("age_to")):
		conditions.append("p.dob > %(born_after)s")
		values["born_after"] = add_to_date(today(), years=-(cint(doc.age_to) + 1))
	if doc.get("insurance_payor"):
		conditions.append(
			"exists (select 1 from `tabPatient Insurance Policy` ip where ip.patient = p.name "
			"and ip.docstatus = 1 and ip.insurance_payor = %(payor)s "
			"and (ip.policy_expiry_date is null or ip.policy_expiry_date >= %(today)s))"
		)
		values["payor"] = doc.insurance_payor
		values["today"] = today()
	if cint(doc.get("active_pregnancy")):
		conditions.append(
			"exists (select 1 from `tabPregnancy Record` pr where pr.patient = p.name and pr.status = 'Active')"
		)

	visit = _visit_condition(doc, values)
	if visit:
		conditions.append(visit)

	# Static SQL fragments only; every value goes through `values`.
	query = "select distinct p.name as name, p.mobile as mobile_no from `tabPatient` p where " + " and ".join(
		conditions
	)
	return frappe.db.sql(query, values, as_dict=True)


def _visit_condition(doc, values) -> str | None:
	"""A visit is an appointment (not cancelled / no-show) or a submitted
	encounter in the date range, optionally at a facility / in a department.
	An encounter counts for a facility through its appointment's service unit."""
	date_from, date_to = doc.get("visited_from"), doc.get("visited_to")
	dept, facility = doc.get("medical_department"), doc.get("health_facility")
	if not (date_from or date_to or dept or facility):
		return None

	appt = ["a.patient = p.name", "a.status not in ('Cancelled', 'No Show')"]
	enc = ["e.patient = p.name", "e.docstatus = 1"]
	if date_from:
		appt.append("a.appointment_date >= %(visited_from)s")
		enc.append("e.encounter_date >= %(visited_from)s")
		values["visited_from"] = getdate(date_from)
	if date_to:
		appt.append("a.appointment_date <= %(visited_to)s")
		enc.append("e.encounter_date <= %(visited_to)s")
		values["visited_to"] = getdate(date_to)
	if dept:
		appt.append("a.department = %(dept)s")
		enc.append("e.medical_department = %(dept)s")
		values["dept"] = dept
	if facility:
		units = facility_units(facility) or ["__none__"]
		values["units"] = tuple(units)
		appt.append("a.service_unit in %(units)s")
		enc.append(
			"exists (select 1 from `tabPatient Appointment` ea where ea.name = e.appointment "
			"and ea.service_unit in %(units)s)"
		)
	return (
		"(exists (select 1 from `tabPatient Appointment` a where "
		+ " and ".join(appt)
		+ ") or exists (select 1 from `tabPatient Encounter` e where "
		+ " and ".join(enc)
		+ "))"
	)


@frappe.whitelist()
def preview_campaign(name: str) -> dict:
	doc = frappe.get_doc("Patient SMS Campaign", name)
	doc.check_permission("write")
	if not available():
		frappe.throw(_("SMS needs the Bulk SMS app (royce_talk) installed on this site."))
	from royce_talk.bulk_sms.bulk_send import estimate_cost

	recipients = campaign_recipients(doc)
	cost = estimate_cost(doc.message or "", len(recipients))
	doc.db_set(
		{
			"recipient_count": len(recipients),
			"estimated_units": cost["total_units"],
			"estimated_cost": cost["estimated_cost"],
		},
		update_modified=False,
	)
	return {
		"recipient_count": len(recipients),
		"sample": [r.name for r in recipients[:10]],
		**cost,
	}


def before_submit_campaign(doc):
	_require()
	from royce_talk.bulk_sms.bulk_send import check_submit_guardrails

	recipients = campaign_recipients(doc)
	cost = check_submit_guardrails(recipients, doc.message)
	doc.recipient_count = len(recipients)
	doc.estimated_units = cost["total_units"]
	doc.estimated_cost = cost["estimated_cost"]
	doc.status = "Queued"


def send_campaign(campaign_name: str):
	"""Background job: royce_talk's bulk sender re-resolves recipients and
	writes the result (batch id, queued, failed, cost) back onto the campaign."""
	from royce_talk.bulk_sms.bulk_send import send_bulk

	try:
		send_bulk("Patient SMS Campaign", campaign_name, campaign_recipients)
	except Exception:
		# royce_talk 16.3.0 writes balance_remaining=None when every chunk fails
		# (wrong key, provider down), which the Int column refuses; the campaign
		# would otherwise sit at Queued/Sending forever with no visible error.
		frappe.db.rollback()
		frappe.log_error(title=f"Patient SMS Campaign {campaign_name} failed")
		frappe.db.set_value(
			"Patient SMS Campaign",
			campaign_name,
			{
				"status": "Failed",
				"error": _(
					"Sending failed. Check the API key and balance in Bulk SMS Settings, "
					"and the Error Log for details. Nothing was charged for messages not accepted."
				),
			},
			update_modified=False,
		)


# Automatic messages ----------------------------------------------------------


def _consented_mobile(patient: str) -> str | None:
	p = frappe.db.get_value("Patient", patient, ["mobile", "ke_sms_consent", "status"], as_dict=True)
	if p and cint(p.ke_sms_consent) and p.mobile and p.status == "Active":
		return p.mobile
	return None


def _queue(mobile, message, doctype, name):
	from royce_talk.bulk_sms.utils import queue_sms

	queue_sms(
		phone_number=mobile,
		text_message=message,
		reference_doctype=doctype,
		reference_name=name,
	)


def send_appointment_reminders(now=None):
	"""Hourly. Reminds patients of appointments 2 to 24 hours ahead, once each
	(Marley's `reminded` flag), and only in daytime so nobody is woken at 3am."""
	if not enabled() or not cint(settings().sms_appointment_reminders):
		return
	now = get_datetime(now) if now else now_datetime()
	if not (FIRST_SEND_HOUR <= now.hour < LAST_SEND_HOUR):
		return
	template = settings().sms_reminder_template or DEFAULT_REMINDER
	appointments = frappe.get_all(
		"Patient Appointment",
		filters={
			"appointment_datetime": ["between", (add_to_date(now, hours=2), add_to_date(now, hours=24))],
			"reminded": 0,
			"status": ["in", ["Scheduled", "Open", "Confirmed"]],
		},
		fields=["name", "patient", "company", "service_unit", "appointment_date", "appointment_time"],
	)
	for a in appointments:
		mobile = _consented_mobile(a.patient)
		if mobile:
			ctx = _context(a.patient, a.company, a.service_unit)
			ctx.update(
				{
					"date": frappe.utils.formatdate(a.appointment_date, "EEE d MMM"),
					"time": frappe.utils.format_time(a.appointment_time, "HH:mm"),
				}
			)
			_queue(mobile, render(template, ctx), "Patient Appointment", a.name)
		# Marked either way, so patients without consent aren't re-checked hourly.
		frappe.db.set_value("Patient Appointment", a.name, "reminded", 1, update_modified=False)


def lab_test_submitted(doc, method=None):
	"""Lab Test on_submit: tell the patient results are ready (no values)."""
	if not enabled() or not cint(settings().sms_lab_results):
		return
	mobile = _consented_mobile(doc.patient)
	if not mobile:
		return
	template = settings().sms_lab_template or DEFAULT_LAB
	ctx = _context(doc.patient, doc.company, doc.get("service_unit"))
	_queue(mobile, render(template, ctx), "Lab Test", doc.name)


def extend_bootinfo(bootinfo):
	bootinfo.ke_sms = 1 if enabled() else 0
