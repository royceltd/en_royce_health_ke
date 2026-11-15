# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Disease surveillance (IDSR): notifiable disease cases, real-time alerts,
outbreak thresholds and the weekly IDSR digest.

How it works:
- Notifiable Disease lists what counts (code prefixes, ICD-10 or ICD-11, or
  specific Diagnosis records), like the MOH 705 mapping.
- When a consultation is submitted, each of its diagnoses that matches a
  notifiable disease records a Notifiable Disease Case (once per patient and
  disease within REPEAT_DAYS, so follow-up visits don't double count).
- Immediately reportable disease: every case alerts the Disease Surveillance
  Officers at once (in-app notification, and SMS to the numbers in Kenya
  Health Settings), so the county is notified within 24 hours.
- Outbreak threshold: `alert_threshold` cases of one disease within
  `threshold_days` days open one Public Health Event (Outbreak Alert) and
  alert the officers; later cases join the open event instead of alerting again.
- Every Monday the officers get last week's IDSR summary (the IDSR Weekly
  Report, epidemiological weeks run Monday to Sunday).

Privacy: SMS alerts name the disease, facility and case number only, never the
patient: health data is sensitive personal data under the Data Protection Act,
and a phone screen is not private. The patient is on the case record, behind
the officer's login."""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import add_days, cint, getdate, now_datetime, today

from royce_health_ke.moh.moh705 import age_on, codings

OFFICER_ROLE = "Disease Surveillance Officer"
REPEAT_DAYS = 14
IMMEDIATE = "Immediately Reportable"


# Matching ---------------------------------------------------------------------


def disease_mapping():
	"""(prefixes [(system, PREFIX, disease)], {diagnosis: disease}) for enabled diseases."""
	diseases = frappe.get_all("Notifiable Disease", filters={"disabled": 0}, pluck="name")
	prefixes, direct = [], {}
	if diseases:
		for row in frappe.get_all(
			"Notifiable Disease Code",
			filters={"parenttype": "Notifiable Disease", "parent": ["in", diseases]},
			fields=["parent", "code_system", "code_prefix", "diagnosis"],
		):
			if row.diagnosis:
				direct[row.diagnosis] = row.parent
			if row.code_system and row.code_prefix:
				prefixes.append((row.code_system, row.code_prefix.strip().upper(), row.parent))
	return prefixes, direct


def diseases_for(diagnoses):
	"""{diagnosis: disease} for the diagnoses that are notifiable. The longest
	matching prefix wins, so a specific code beats a broad one."""
	prefixes, direct = disease_mapping()
	if not prefixes and not direct:
		return {}
	codes = codings("Diagnosis", set(diagnoses))
	out = {}
	for dx in diagnoses:
		if dx in direct:
			out[dx] = direct[dx]
			continue
		best, best_len = None, -1
		for system, code in codes.get(dx, []):
			code = (code or "").upper()
			for p_system, prefix, disease in prefixes:
				if p_system == system and code.startswith(prefix) and len(prefix) > best_len:
					best, best_len = disease, len(prefix)
		if best:
			out[dx] = best
	return out


# Recording cases ----------------------------------------------------------------


def encounter_submitted(doc, method=None):
	"""Patient Encounter on_submit: record and alert notifiable disease cases.
	Never blocks the clinician: a failure here is logged, not raised."""
	try:
		record_cases(doc)
	except Exception:
		frappe.log_error(title=_("Disease surveillance: could not record cases for {0}").format(doc.name))


def record_cases(encounter):
	diagnoses = [row.diagnosis for row in encounter.get("diagnosis") or [] if row.diagnosis]
	matched = diseases_for(diagnoses)
	created = []
	for dx, disease in matched.items():
		if any(c.disease == disease for c in created):
			continue  # two diagnoses of the same disease in one consultation
		if _recent_case(encounter.patient, disease, encounter.encounter_date):
			continue
		created.append(_make_case(encounter, disease, dx))
	for case in created:
		info = frappe.db.get_value(
			"Notifiable Disease",
			case.disease,
			["category", "ihr_notifiable", "alert_threshold", "threshold_days"],
			as_dict=True,
		)
		if info.category == IMMEDIATE:
			alert_case(case, info)
		check_threshold(case, info)
	return created


def _recent_case(patient, disease, on_date):
	day = getdate(on_date)
	return frappe.db.exists(
		"Notifiable Disease Case",
		{
			"patient": patient,
			"disease": disease,
			"status": ["!=", "Not a Case"],
			"onset_date": ["between", [add_days(day, -REPEAT_DAYS), day]],
		},
	)


def _make_case(encounter, disease, diagnosis):
	visit = encounter.get("ke_patient_visit")
	facility = frappe.db.get_value("Patient Visit", visit, "facility") if visit else None
	p = frappe.db.get_value(
		"Patient",
		encounter.patient,
		["sex", "dob", "ke_county", "ke_sub_county", "ke_residence"],
		as_dict=True,
	)
	day = getdate(encounter.encounter_date)
	return frappe.get_doc(
		{
			"doctype": "Notifiable Disease Case",
			"disease": disease,
			"status": "New",
			"onset_date": day,
			"company": encounter.company,
			"facility": facility,
			"patient": encounter.patient,
			"sex": p.sex,
			"age_years": age_on(p.dob, day),
			"county": p.ke_county,
			"sub_county": p.ke_sub_county,
			"residence": p.ke_residence,
			"encounter": encounter.name,
			"diagnosis": diagnosis,
			"practitioner": encounter.practitioner,
			"inpatient": 1 if encounter.get("inpatient_record") else 0,
		}
	).insert(ignore_permissions=True)


# Alerts -------------------------------------------------------------------------


def officers():
	"""Enabled users with the Disease Surveillance Officer role; Healthcare
	Administrators when the hospital hasn't named one yet, so no alert is lost."""
	for role in (OFFICER_ROLE, "Healthcare Administrator"):
		users = frappe.get_all(
			"Has Role", filters={"role": role, "parenttype": "User"}, pluck="parent", distinct=True
		)
		users = [
			u
			for u in users
			if u not in ("Administrator", "Guest") and frappe.db.get_value("User", u, "enabled")
		]
		if users:
			return sorted(users)
	return []


def _notify(subject, doctype, name):
	for user in officers():
		frappe.get_doc(
			{
				"doctype": "Notification Log",
				"for_user": user,
				"type": "Alert",
				"subject": subject,
				"document_type": doctype,
				"document_name": name,
			}
		).insert(ignore_permissions=True)


def _sms_officers(message, doctype, name):
	from royce_health_ke import sms

	settings = frappe.get_cached_doc("Kenya Health Settings")
	if not cint(settings.get("surveillance_sms")) or not sms.enabled():
		return
	for mobile in (settings.get("surveillance_sms_numbers") or "").replace(",", "\n").splitlines():
		if mobile.strip():
			sms._queue(mobile.strip(), message, doctype, name)


def _place(case):
	return case.facility or case.company


def alert_case(case, info=None):
	info = info or frappe.db.get_value("Notifiable Disease", case.disease, ["ihr_notifiable"], as_dict=True)
	subject = _(
		"Immediately reportable: suspected {0} ({1}), seen {2}. Notify the county within 24 hours."
	).format(case.disease, case.name, frappe.utils.formatdate(case.onset_date))
	if cint(info.ihr_notifiable):
		subject += " " + _("IHR notifiable: the county informs the national IHR focal point.")
	_notify(subject, "Notifiable Disease Case", case.name)
	_sms_officers(
		_("IDSR ALERT: suspected {0} at {1} on {2}. Case {3}. Notify the county within 24 hours.").format(
			case.disease, _place(case), frappe.utils.formatdate(case.onset_date), case.name
		),
		"Notifiable Disease Case",
		case.name,
	)


def check_threshold(case, info):
	"""Open (or add to) an Outbreak Alert when the disease reaches its threshold."""
	threshold, days = cint(info.alert_threshold), cint(info.threshold_days) or 7
	if threshold < 2:
		return None  # 0 = off; 1 = every case already alerts
	end = getdate(case.onset_date)
	start = add_days(end, -(days - 1))
	cases = frappe.get_all(
		"Notifiable Disease Case",
		filters={
			"disease": case.disease,
			"company": case.company,
			"status": ["!=", "Not a Case"],
			"onset_date": ["between", [start, end]],
		},
		fields=["name", "onset_date", "outcome", "event"],
		order_by="onset_date asc",
	)
	if len(cases) < threshold:
		return None
	event = frappe.db.get_value(
		"Public Health Event",
		{
			"disease": case.disease,
			"company": case.company,
			"event_type": "Outbreak Alert",
			"status": ["in", ["Open", "Verified", "Reported to County"]],
		},
		"name",
	)
	is_new = not event
	if is_new:
		event = (
			frappe.get_doc(
				{
					"doctype": "Public Health Event",
					"event_type": "Outbreak Alert",
					"disease": case.disease,
					"status": "Open",
					"source": "Automatic Threshold",
					"company": case.company,
					"reported_on": now_datetime(),
					"description": _(
						"{0} cases of {1} within {2} days reached the alert threshold of {3}. "
						"Verify the cases and inform the county."
					).format(len(cases), case.disease, days, threshold),
				}
			)
			.insert(ignore_permissions=True)
			.name
		)
	for c in cases:
		if not c.event:
			frappe.db.set_value("Notifiable Disease Case", c.name, "event", event, update_modified=False)
	_update_event_counts(event)
	if is_new:
		subject = _("Outbreak alert: {0} cases of {1} in {2} days ({3}).").format(
			len(cases), case.disease, days, event
		)
		_notify(subject, "Public Health Event", event)
		_sms_officers(
			_("IDSR OUTBREAK ALERT: {0} cases of {1} at {2} in {3} days. Event {4}.").format(
				len(cases), case.disease, _place(case), days, event
			),
			"Public Health Event",
			event,
		)
	return event


def _update_event_counts(event):
	rows = frappe.get_all(
		"Notifiable Disease Case",
		filters={"event": event, "status": ["!=", "Not a Case"]},
		fields=["onset_date", "outcome"],
	)
	if rows:
		frappe.db.set_value(
			"Public Health Event",
			event,
			{
				"cases": len(rows),
				"deaths": sum(1 for r in rows if r.outcome == "Died"),
				"first_case_on": min(r.onset_date for r in rows),
				"last_case_on": max(r.onset_date for r in rows),
			},
			update_modified=False,
		)


def event_inserted(doc, method=None):
	"""Public Health Event after_insert: an event reported by staff (a rumour, a
	maternal death, ...) alerts the officers. Threshold events alert themselves."""
	if doc.source != "Automatic Threshold":
		_notify(
			_("Public health event reported: {0}{1} ({2}). Verify it.").format(
				doc.event_type, f" - {doc.disease}" if doc.disease else "", doc.name
			),
			"Public Health Event",
			doc.name,
		)


# IDSR weekly ----------------------------------------------------------------------


def epi_week(day):
	"""(ISO year, ISO week): IDSR epidemiological weeks run Monday to Sunday."""
	year, week, _weekday = getdate(day).isocalendar()
	return year, week


def week_dates(year, week):
	from datetime import date

	start = date.fromisocalendar(int(year), int(week), 1)
	return start, add_days(start, 6)


def weekly_summary(company, year, week):
	"""One row per enabled notifiable disease (zero reporting is part of IDSR):
	cases and deaths, under 5 and 5 and over."""
	start, end = week_dates(year, week)
	counts = defaultdict(lambda: defaultdict(int))
	for c in frappe.get_all(
		"Notifiable Disease Case",
		filters={
			"company": company,
			"status": ["!=", "Not a Case"],
			"onset_date": ["between", [start, end]],
		},
		fields=["disease", "age_years", "outcome"],
	):
		group = "u5" if c.age_years is not None and c.age_years < 5 else "o5"
		counts[c.disease][f"cases_{group}"] += 1
		if c.outcome == "Died":
			counts[c.disease][f"deaths_{group}"] += 1
	rows = []
	for d in frappe.get_all(
		"Notifiable Disease",
		filters={"disabled": 0},
		fields=["name", "category", "ihr_notifiable"],
		order_by="category asc, name asc",
	):
		c = counts[d.name]
		rows.append(
			{
				"disease": d.name,
				"category": d.category,
				"ihr": d.ihr_notifiable,
				"cases_u5": c["cases_u5"],
				"deaths_u5": c["deaths_u5"],
				"cases_o5": c["cases_o5"],
				"deaths_o5": c["deaths_o5"],
				"cases": c["cases_u5"] + c["cases_o5"],
				"deaths": c["deaths_u5"] + c["deaths_o5"],
			}
		)
	return rows


def send_weekly_digest(on_date=None):
	"""Weekly (Monday): last epidemiological week's IDSR summary to the officers,
	per company, with a link to the report."""
	year, week = epi_week(add_days(getdate(on_date or today()), -7))
	for company in frappe.get_all("Company", pluck="name"):
		rows = weekly_summary(company, year, week)
		cases = sum(r["cases"] for r in rows)
		deaths = sum(r["deaths"] for r in rows)
		listed = ", ".join(f"{r['disease']} {r['cases']}" for r in rows if r["cases"])
		subject = _(
			"IDSR week {0}/{1} for {2}: {3} case(s), {4} death(s){5}. Submit the weekly report."
		).format(week, year, company, cases, deaths, f" ({listed})" if listed else _(" (zero report)"))
		for user in officers():
			frappe.get_doc(
				{
					"doctype": "Notification Log",
					"for_user": user,
					"type": "Alert",
					"subject": subject,
					"link": f"/app/query-report/IDSR Weekly Report?company={company}&year={year}&week={week}",
				}
			).insert(ignore_permissions=True)


def weekly_job():
	if getdate(today()).weekday() == 0:  # Monday
		send_weekly_digest()
