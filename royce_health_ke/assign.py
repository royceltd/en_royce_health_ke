# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""The next consultant: who sees the patient, and in which room.

When triage (or reception) sends a patient to Consultation without naming a
doctor, the visit goes to a doctor on duty now, shared out evenly:

- On duty: an active Healthcare Practitioner whose Practitioner Schedule
  (Healthcare Practitioner > Practitioner Schedules) has a time slot for
  today covering this moment. The schedule row's service unit is the room.
  Only rooms in the visit's facility. Doctors of the visit's department
  first; when none of them is on duty, any doctor on duty (the sender is
  told), since a visit's department can be stale (fetched from the doctor
  named at check-in).
- Evenly: the doctor with the fewest patients at Consultation now (waiting
  or in the room), then the fewest sent to them today, then the one who has
  waited longest for a new patient.

A doctor named by hand, or the doctor of the visit's appointment, is kept.
Nobody on duty: the sender is asked to choose the doctor."""

import frappe
from frappe import _
from frappe.utils import get_datetime, getdate, now_datetime


def _seconds(value):
	"""A TIME column (timedelta) or a time, as seconds after midnight."""
	if value is None:
		return None
	if hasattr(value, "total_seconds"):
		return int(value.total_seconds())
	return value.hour * 3600 + value.minute * 60 + value.second


def _covers(slot_from, slot_to, now):
	start, end = _seconds(slot_from), _seconds(slot_to)
	if start is None or end is None:
		return False
	if end <= start:  # a night shift past midnight
		return now >= start or now < end
	return start <= now < end


def facility_unit(facility):
	"""(lft, rgt) of the facility's service unit group, or None."""
	unit = facility and frappe.db.get_value("Health Facility", facility, "healthcare_service_unit")
	return unit and frappe.db.get_value("Healthcare Service Unit", unit, ["lft", "rgt"])


def on_duty(company=None, facility=None, department=None, at=None, exclude=()):
	"""[{practitioner, practitioner_name, department, room}] on duty at `at`."""
	at = get_datetime(at) if at else now_datetime()
	now = _seconds(at.time())
	rows = frappe.db.sql(
		"""
		select p.name as practitioner, p.practitioner_name, p.department, su.service_unit as room,
			ts.from_time, ts.to_time, unit.company, unit.lft, unit.rgt
		from `tabHealthcare Practitioner` p
		join `tabPractitioner Service Unit Schedule` su
			on su.parent = p.name and su.parenttype = 'Healthcare Practitioner'
		join `tabPractitioner Schedule` s on s.name = su.schedule and ifnull(s.disabled, 0) = 0
		join `tabHealthcare Schedule Time Slot` ts
			on ts.parent = s.name and ts.parenttype = 'Practitioner Schedule'
		left join `tabHealthcare Service Unit` unit on unit.name = su.service_unit
		where p.status = 'Active' and ts.day = %(day)s
		order by p.name, su.idx, ts.from_time
		""",
		{"day": at.strftime("%A")},
		as_dict=True,
	)
	bounds = facility_unit(facility)
	found = {}
	for r in rows:
		if r.practitioner in found or r.practitioner in exclude:
			continue
		if not _covers(r.from_time, r.to_time, now):
			continue
		if company and r.company and r.company != company:
			continue
		if bounds and not (r.lft and bounds[0] <= r.lft and r.rgt <= bounds[1]):
			continue
		if department and r.department != department:
			continue
		found[r.practitioner] = frappe._dict(
			practitioner=r.practitioner,
			practitioner_name=r.practitioner_name,
			department=r.department,
			room=r.room,
		)
	return list(found.values())


def workload(practitioners, on=None):
	"""{practitioner: (at consultation now, sent today, last sent)}."""
	if not practitioners:
		return {}
	day = getdate(on) if on else getdate()
	now = dict(
		frappe.db.sql(
			"""
			select practitioner, count(*) from `tabPatient Visit`
			where status = 'Open' and current_station = 'Consultation' and practitioner in %(p)s
			group by practitioner
			""",
			{"p": practitioners},
		)
	)
	today = {
		r[0]: (r[1], r[2])
		for r in frappe.db.sql(
			"""
			select m.practitioner, count(*), max(m.sent_at) from `tabPatient Visit Movement` m
			where m.parenttype = 'Patient Visit' and m.to_station = 'Consultation'
				and m.practitioner in %(p)s and date(m.sent_at) = %(day)s
			group by m.practitioner
			""",
			{"p": practitioners, "day": day},
		)
	}
	return {p: (now.get(p, 0), *(today.get(p) or (0, None))) for p in practitioners}


def next_consultant(company=None, facility=None, department=None, exclude=()):
	"""The doctor on duty with the least work, with their room; None if nobody is on duty."""
	candidates = on_duty(company, facility, department, exclude=exclude)
	if not candidates:
		return None
	load = workload([c.practitioner for c in candidates])
	earliest = get_datetime("1900-01-01")

	def key(c):
		waiting, sent_today, last = load[c.practitioner]
		return (waiting, sent_today, get_datetime(last) if last else earliest, c.practitioner)

	return min(candidates, key=key)


def assign(doc, exclude=()):
	"""Give the visit the next consultant and their room, or ask for one."""
	department = doc.get("department")
	chosen = next_consultant(doc.company, doc.get("facility"), department, exclude)
	if not chosen and department:
		chosen = next_consultant(doc.company, doc.get("facility"), None, exclude)
		if chosen:
			frappe.msgprint(
				_("No {0} doctor is on duty now: sent to {1} ({2}).").format(
					department, chosen.practitioner_name, chosen.department or _("no department")
				),
				indicator="orange",
				alert=True,
			)
	if not chosen:
		frappe.throw(
			_("No doctor {0}is on duty now (Practitioner Schedules). Choose the doctor.").format(
				_("at {0} ").format(doc.facility) if doc.get("facility") else ""
			),
			title=_("Nobody on duty"),
		)
	doc.practitioner = chosen.practitioner
	doc.practitioner_name = chosen.practitioner_name
	doc.consultation_room = chosen.room
	return chosen


def room_of(practitioner, company=None, facility=None):
	"""The room the doctor is scheduled in now, for a doctor chosen by hand."""
	for c in on_duty(company, facility):
		if c.practitioner == practitioner:
			return c.room
	return None


def default_facility(company):
	"""The user's default Health Facility, else the company's only one."""
	facility = frappe.defaults.get_user_default("Health Facility")
	if facility and frappe.db.get_value("Health Facility", facility, "company") in (company, None):
		return facility
	facilities = frappe.get_all("Health Facility", filters={"company": company, "disabled": 0}, pluck="name")
	return facilities[0] if len(facilities) == 1 else None


def ahead_of(doc):
	"""Patients waiting for the same doctor who were sent before this one."""
	if doc.current_station != "Consultation" or not doc.practitioner or not doc.sent_at:
		return 0
	return frappe.db.count(
		"Patient Visit",
		{
			"status": "Open",
			"current_station": "Consultation",
			"queue_status": "Waiting",
			"practitioner": doc.practitioner,
			"sent_at": ["<", doc.sent_at],
			"name": ["!=", doc.name],
		},
	)


def health_queue_slip(doc):
	"""Jinja: what the patient's queue slip shows."""
	return frappe._dict(
		hospital=frappe.db.get_value("Health Facility", doc.get("facility"), "facility_name")
		if doc.get("facility")
		else doc.company,
		room=doc.get("consultation_room")
		and (
			frappe.db.get_value(
				"Healthcare Service Unit", doc.consultation_room, "healthcare_service_unit_name"
			)
			or doc.consultation_room
		),
		doctor=doc.get("practitioner_name") or doc.get("practitioner"),
		service=doc.get("appointment_type"),
		ahead=ahead_of(doc),
	)
