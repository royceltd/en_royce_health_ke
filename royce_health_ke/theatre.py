# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Theatre: booking and scheduling, consent, the WHO Surgical Safety
Checklist, anaesthesia record and operation note, around Marley's Clinical
Procedure (which carries the procedure's billing and its consumables).

Gates, in theatre order:
- Start (patient into theatre): signed consent, checklist Sign In done, and
  no pending or declined pre-authorisation (an Emergency may proceed while
  it is pending). Starting creates, submits and starts the Clinical Procedure.
- Complete: checklist Time Out and Sign Out done and the operation note's
  procedure details written. Completing completes the Clinical Procedure,
  which issues its consumables from stock."""

import frappe
from frappe import _
from frappe.utils import add_to_date, get_datetime, getdate, now_datetime, nowtime

OPEN = ("Scheduled", "In Theatre")

SIGN_IN = (
	"si_identity_confirmed",
	"si_site_marked",
	"si_anaesthesia_check",
	"si_pulse_oximeter",
	"si_known_allergy",
	"si_difficult_airway",
	"si_blood_loss_risk",
	"sign_in_by",
)
TIME_OUT = (
	"to_team_introduced",
	"to_confirmed",
	"to_antibiotic",
	"to_imaging",
	"to_surgeon_events",
	"to_anaesthetist_concerns",
	"to_nursing_sterility",
	"time_out_by",
)
SIGN_OUT = (
	"so_procedure_recorded",
	"so_counts_correct",
	"so_specimen_labelled",
	"so_recovery_reviewed",
	"sign_out_by",
)
PHASES = (
	("sign_in_status", "sign_in_time", SIGN_IN, _("Sign In")),
	("time_out_status", "time_out_time", TIME_OUT, _("Time Out")),
	("sign_out_status", "sign_out_time", SIGN_OUT, _("Sign Out")),
)


# Booking


def validate_booking(doc):
	if not frappe.db.get_value(
		"Healthcare Service Unit Type",
		frappe.db.get_value("Healthcare Service Unit", doc.theatre, "service_unit_type"),
		"is_ot",
	):
		frappe.throw(
			_("{0} is not an operating theatre (its Service Unit Type must have 'Is OT' ticked).").format(
				doc.theatre
			)
		)
	if not doc.duration_minutes:
		# The template's Default Duration is a Duration field, in seconds.
		seconds = frappe.db.get_value(
			"Clinical Procedure Template", doc.procedure_template, "default_duration"
		)
		doc.duration_minutes = int(seconds / 60) if seconds else 60
	doc.scheduled_end = add_to_date(get_datetime(doc.scheduled_start), minutes=doc.duration_minutes)
	if doc.status in OPEN:
		check_clashes(doc)


def check_clashes(doc):
	"""Another open booking overlapping this one in the same theatre, or for
	the same surgeon, anaesthetist or patient."""
	for field, label in (
		("theatre", _("Theatre")),
		("surgeon", _("Surgeon")),
		("anaesthetist", _("Anaesthetist")),
		("patient", _("Patient")),
	):
		value = doc.get(field)
		if not value:
			continue
		clash = frappe.db.get_value(
			"Theatre Booking",
			{
				field: value,
				"name": ["!=", doc.name],
				"status": ["in", OPEN],
				"scheduled_start": ["<", doc.scheduled_end],
				"scheduled_end": [">", doc.scheduled_start],
			},
			["name", "patient_name", "scheduled_start"],
			as_dict=True,
		)
		if clash:
			frappe.throw(
				_("{0} {1} is already booked for {2} at {3} ({4}).").format(
					label,
					value,
					clash.patient_name,
					frappe.format(clash.scheduled_start, "Datetime"),
					clash.name,
				),
				title=_("Theatre clash"),
			)


def _booking(name):
	doc = frappe.get_doc("Theatre Booking", name)
	doc.check_permission("write")
	return doc


@frappe.whitelist()
def start(booking: str):
	doc = _booking(booking)
	if doc.status != "Scheduled":
		frappe.throw(_("Only a scheduled booking can start; this one is {0}.").format(doc.status))
	if not (
		doc.surgical_consent
		and frappe.db.get_value("Surgical Consent", doc.surgical_consent, "docstatus") == 1
	):
		frappe.throw(_("Record and submit the patient's surgical consent first."))
	if not (
		doc.safety_checklist
		and frappe.db.get_value("Surgical Safety Checklist", doc.safety_checklist, "sign_in_status") == "Done"
	):
		frappe.throw(_("Complete the Surgical Safety Checklist Sign In first."))
	if doc.pre_authorisation == "Declined":
		frappe.throw(_("The insurer declined pre-authorisation for this procedure."))
	if doc.pre_authorisation == "Pending":
		if doc.priority != "Emergency":
			frappe.throw(_("Pre-authorisation is still pending."))
		frappe.msgprint(
			_("Emergency: starting while pre-authorisation is pending."), indicator="orange", alert=True
		)

	from healthcare.healthcare.doctype.clinical_procedure.clinical_procedure import get_procedure_consumables

	template = frappe.get_doc("Clinical Procedure Template", doc.procedure_template)
	procedure = frappe.get_doc(
		{
			"doctype": "Clinical Procedure",
			"patient": doc.patient,
			"procedure_template": doc.procedure_template,
			"practitioner": doc.surgeon,
			"medical_department": template.medical_department,
			"service_unit": doc.theatre,
			"company": doc.company,
			"inpatient_record": doc.inpatient_record,
			"service_request": doc.service_request,
			"start_date": getdate(),
			"start_time": nowtime(),
			"consume_stock": template.consume_stock,
			"warehouse": frappe.db.get_value("Healthcare Service Unit", doc.theatre, "warehouse")
			or frappe.db.get_single_value("Stock Settings", "default_warehouse"),
			"ke_theatre_booking": doc.name,
			"items": [
				{
					k: item.get(k)
					for k in (
						"item_code",
						"item_name",
						"qty",
						"uom",
						"stock_uom",
						"conversion_factor",
						"transfer_qty",
						"invoice_separately_as_consumables",
					)
				}
				for item in get_procedure_consumables(doc.procedure_template)
			],
		}
	)
	procedure.insert(ignore_permissions=True)
	procedure.submit()
	if procedure.start_procedure() != "success":
		frappe.throw(_("Not enough stock of the procedure's consumables in {0}.").format(procedure.warehouse))
	doc.db_set({"status": "In Theatre", "clinical_procedure": procedure.name})
	return procedure.name


@frappe.whitelist()
def complete(booking: str):
	doc = _booking(booking)
	if doc.status != "In Theatre":
		frappe.throw(_("Only a booking in theatre can be completed; this one is {0}.").format(doc.status))
	checklist = frappe.db.get_value(
		"Surgical Safety Checklist",
		doc.safety_checklist,
		["time_out_status", "sign_out_status"],
		as_dict=True,
	)
	if not checklist or checklist.time_out_status != "Done" or checklist.sign_out_status != "Done":
		frappe.throw(_("Complete the Surgical Safety Checklist Time Out and Sign Out first."))
	procedure = frappe.get_doc("Clinical Procedure", doc.clinical_procedure)
	if not procedure.get("ke_procedure_details"):
		frappe.throw(_("Write the operation note (procedure details) on {0} first.").format(procedure.name))
	stock_entry = procedure.complete_procedure()
	doc.db_set("status", "Completed")
	return {"clinical_procedure": procedure.name, "stock_entry": stock_entry}


@frappe.whitelist()
def set_status(booking: str, status: str, reason: str):
	doc = _booking(booking)
	if status not in ("Postponed", "Cancelled", "Scheduled"):
		frappe.throw(_("Status {0} is set by starting or completing the booking.").format(status))
	if doc.status in ("In Theatre", "Completed"):
		frappe.throw(_("The patient has already been in theatre."))
	doc.status = status
	doc.status_reason = reason
	doc.save()
	return doc.status


# Linked records


def link_to_booking(doc, field):
	"""One consent / checklist / anaesthesia record per booking, linked back."""
	existing = frappe.db.get_value("Theatre Booking", doc.theatre_booking, field)
	if existing and existing != doc.name and frappe.db.get_value(doc.doctype, existing, "docstatus") != 2:
		frappe.throw(
			_("Theatre Booking {0} already has {1} {2}.").format(doc.theatre_booking, doc.doctype, existing)
		)
	frappe.db.set_value("Theatre Booking", doc.theatre_booking, field, doc.name)


def validate_checklist(doc):
	"""Each phase is Done when all its items are answered, and only after the
	phase before it; its time is stamped when it becomes Done."""
	previous_done = True
	for status_field, time_field, fields, label in PHASES:
		answered = all(doc.get(f) for f in fields)
		if answered and not previous_done:
			frappe.throw(_("{0} can't be completed before the phase before it.").format(label))
		doc.set(status_field, "Done" if answered else "Pending")
		if answered and not doc.get(time_field):
			doc.set(time_field, now_datetime())
		previous_done = answered


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def theatre_query(doctype, txt, searchfield, start, page_len, filters):
	"""Service units whose type is an operating theatre."""
	ot_types = frappe.get_all("Healthcare Service Unit Type", filters={"is_ot": 1}, pluck="name") or [""]
	conditions = {"service_unit_type": ["in", ot_types], "is_group": 0, "name": ["like", f"%{txt}%"]}
	if filters and filters.get("company"):
		conditions["company"] = filters["company"]
	return frappe.get_all(
		"Healthcare Service Unit",
		filters=conditions,
		fields=["name", "healthcare_service_unit_name"],
		as_list=True,
		start=start,
		page_length=page_len,
	)
