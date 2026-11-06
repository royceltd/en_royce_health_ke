# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Kenyan identifiers on patients and practitioners: normalise what staff type
at reception, catch obvious mistakes, keep Marley's own fields in step."""

import re

import frappe
from frappe import _
from frappe.utils import add_days, date_diff, getdate, today

PHONE_FIELDS = ("mobile", "phone", "ke_nok_phone")
# Kenyan mobile and fixed numbers: 07xx/01xx with or without the 254 prefix.
KENYAN_PHONE = re.compile(r"^(?:\+?254|0)?([17]\d{8})$")


def normalise_phone(value):
	"""'0712 000 001', '254712000001', '+254-712-000-001' -> '+254712000001'.
	Anything that isn't a Kenyan number is returned unchanged (foreign
	patients keep what was typed)."""
	if not value:
		return value
	digits = re.sub(r"[\s\-()]", "", value)
	match = KENYAN_PHONE.match(digits)
	return f"+254{match.group(1)}" if match else value


def validate_id_number(id_type, number):
	"""The cleaned ID number, or a thrown error for an impossible one. Only
	the National ID format is checked strictly (digits); other documents vary."""
	number = re.sub(r"\s", "", number or "").upper()
	if not id_type or id_type == "None":
		return None
	if not number:
		frappe.throw(_("Enter the {0} number.").format(id_type))
	if id_type == "National ID" and not (number.isdigit() and 6 <= len(number) <= 9):
		frappe.throw(_("A National ID number has 6 to 9 digits; got {0}.").format(number))
	return number


def validate_patient(doc, method=None):
	for field in PHONE_FIELDS:
		if doc.get(field):
			doc.set(field, normalise_phone(doc.get(field)))
	doc.ke_sha_number = (doc.ke_sha_number or "").strip().upper() or None
	doc.ke_id_number = validate_id_number(doc.ke_id_type, doc.ke_id_number)
	if doc.ke_id_number:
		duplicate = frappe.db.get_value(
			"Patient",
			{"uid": doc.ke_id_number, "name": ["!=", doc.name]},
			["name", "patient_name"],
			as_dict=True,
		)
		if duplicate:
			frappe.throw(
				_("{0} {1} is already registered to {2} ({3}).").format(
					doc.ke_id_type, doc.ke_id_number, duplicate.patient_name, duplicate.name
				),
				title=_("Patient already registered"),
			)
		doc.uid = doc.ke_id_number


def validate_practitioner(doc, method=None):
	doc.ke_registration_number = (doc.ke_registration_number or "").strip().upper() or None
	doc.ke_licence_number = (doc.ke_licence_number or "").strip().upper() or None
	if doc.ke_licence_expiry and getdate(doc.ke_licence_expiry) < getdate(today()) and doc.status == "Active":
		frappe.msgprint(
			_("{0}'s practising licence expired on {1}.").format(
				doc.practitioner_name or doc.name, frappe.format(doc.ke_licence_expiry, "Date")
			),
			indicator="orange",
			alert=True,
		)


# Days before expiry on which administrators are reminded; once expired, weekly.
REMIND_AT = (30, 14, 7, 1)


def licences_needing_attention(on_date=None):
	"""Active practitioners whose licence expires on a reminder day, or expired
	today or a whole number of weeks ago."""
	on_date = getdate(on_date or today())
	rows = frappe.get_all(
		"Healthcare Practitioner",
		filters={
			"status": "Active",
			"ke_licence_expiry": ["<=", add_days(on_date, max(REMIND_AT))],
		},
		fields=["name", "practitioner_name", "ke_licence_expiry", "ke_regulator"],
	)
	due = []
	for row in rows:
		days_left = date_diff(row.ke_licence_expiry, on_date)
		if days_left in REMIND_AT or (days_left <= 0 and days_left % 7 == 0):
			row.days_left = days_left
			due.append(row)
	return due


def remind_licence_expiry():
	"""Daily: a notification to every Healthcare Administrator per licence due."""
	due = licences_needing_attention()
	if not due:
		return
	users = {
		u.parent
		for u in frappe.get_all(
			"Has Role", filters={"role": "Healthcare Administrator", "parenttype": "User"}, fields=["parent"]
		)
		if frappe.db.get_value("User", u.parent, "enabled")
	}
	for row in due:
		subject = (
			_("{0}'s practising licence expired {1} day(s) ago").format(row.practitioner_name, -row.days_left)
			if row.days_left < 0
			else _("{0}'s practising licence expires today").format(row.practitioner_name)
			if row.days_left == 0
			else _("{0}'s practising licence expires in {1} day(s)").format(
				row.practitioner_name, row.days_left
			)
		)
		for user in users:
			frappe.get_doc(
				{
					"doctype": "Notification Log",
					"for_user": user,
					"type": "Alert",
					"subject": subject,
					"document_type": "Healthcare Practitioner",
					"document_name": row.name,
				}
			).insert(ignore_permissions=True)
