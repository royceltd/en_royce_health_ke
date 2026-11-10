# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Theatre: booking and scheduling, consent, the WHO Surgical Safety
Checklist, anaesthesia record and operation note, around Marley's Clinical
Procedure (which carries the procedure's billing and its consumables).

The Surgical Safety Checklist follows the hospital's paper theatre checklist:
ward preparation and handover, the WHO Sign In / Time Out / Sign Out, the
gauze and instrument counts, and the post-operative checklist back to the
ward.

Gates, in theatre order:
- Start (patient into theatre): signed consent, ward preparation done (an
  Emergency may skip it, with a warning), checklist Sign In done, and no
  pending or declined pre-authorisation (an Emergency may proceed while it is
  pending). Starting creates, submits and starts the Clinical Procedure.
- Complete: checklist Time Out and Sign Out done (Sign Out can't confirm the
  counts unless every count line balances) and the operation note's procedure
  details written. Completing completes the Clinical Procedure, which issues
  its consumables from stock."""

import re

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
WARD_PREP = (
	"wp_consent_signed",
	"wp_identity_band",
	"wp_gown",
	"wp_jewellery_removed",
	"wp_dentures",
	"wp_fasting",
	"wp_prepared_by",
	"wp_handed_over_by",
	"wp_received_by",
)
POST_OP = (
	"po_pulse",
	"po_bp_systolic",
	"po_consciousness",
	"po_handed_over_by",
	"po_received_by",
)
DEFAULT_COUNTS = (
	("Gauze", "Abdominal packs"),
	("Gauze", "Detectable gauze swabs"),
	("Instrument", "Instrument set"),
	("Instrument", "Surgical blades"),
	("Instrument", "Needles"),
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
	ward_prep = frappe.db.get_value("Surgical Safety Checklist", doc.safety_checklist, "ward_prep_status")
	if ward_prep != "Done":
		if doc.priority != "Emergency":
			frappe.throw(
				_("Complete the ward preparation and handover on the Surgical Safety Checklist first.")
			)
		frappe.msgprint(
			_("Emergency: going into theatre before the ward preparation is complete."),
			indicator="orange",
			alert=True,
		)
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
	"""Ward preparation is Done when its items are answered (consent from the
	booking). Each WHO phase is Done when all its items are answered, and only
	after the phase before it; its time is stamped when it becomes Done. The
	post-op checklist is Done when answered, after Sign Out."""
	if doc.get("theatre_booking"):
		booking = frappe.db.get_value(
			"Theatre Booking", doc.theatre_booking, ["surgical_consent", "inpatient_record"], as_dict=True
		)
		if booking:
			doc.wp_consent_signed = int(
				bool(booking.surgical_consent)
				and frappe.db.get_value("Surgical Consent", booking.surgical_consent, "docstatus") == 1
			)
			if booking.inpatient_record and not doc.get("wp_ward"):
				ward = frappe.db.get_value(
					"Inpatient Occupancy",
					{"parent": booking.inpatient_record, "parenttype": "Inpatient Record"},
					"service_unit",
					order_by="idx desc",
				)
				if ward:
					ward = (
						frappe.db.get_value("Healthcare Service Unit", ward, "parent_healthcare_service_unit")
						or ward
					)
				doc.wp_ward = ward.rsplit(" - ", 1)[0] if ward else None
	if doc.is_new() and not doc.get("counts"):
		for category, item in DEFAULT_COUNTS:
			doc.append("counts", {"category": category, "item": item})
	ward_done = all(doc.get(f) for f in WARD_PREP)
	doc.ward_prep_status = "Done" if ward_done else "Pending"
	if ward_done:
		if not doc.get("wp_handed_over_time"):
			doc.wp_handed_over_time = now_datetime()
		if not doc.get("wp_received_time"):
			doc.wp_received_time = now_datetime()

	validate_counts(doc)

	previous_done = True
	for status_field, time_field, fields, label in PHASES:
		answered = all(doc.get(f) for f in fields)
		if answered and not previous_done:
			frappe.throw(_("{0} can't be completed before the phase before it.").format(label))
		doc.set(status_field, "Done" if answered else "Pending")
		if answered and not doc.get(time_field):
			doc.set(time_field, now_datetime())
		previous_done = answered

	post_done = all(doc.get(f) for f in POST_OP)
	if post_done and doc.sign_out_status != "Done":
		frappe.throw(_("The post-operative checklist can't be completed before Sign Out."))
	doc.post_op_status = "Done" if post_done else "Pending"
	if post_done and not doc.get("po_received_time"):
		doc.po_received_time = now_datetime()


def validate_counts(doc):
	"""Each line's result; ticking 'counts correct' at Sign Out needs every
	counted line to balance (end = start + added) and both nurses named."""
	wrong = []
	counted = False
	for row in doc.get("counts") or []:
		expected = (row.start_count or 0) + (row.added or 0)
		if not expected and not row.end_count:
			row.result = ""
			continue
		counted = True
		if row.end_count == expected:
			row.result = _("Correct")
		elif row.end_count < expected:
			row.result = _("Missing {0}").format(expected - row.end_count)
			wrong.append(row)
		else:
			row.result = _("{0} extra").format(row.end_count - expected)
			wrong.append(row)
	if not doc.get("so_counts_correct") or not counted:
		return
	if wrong:
		frappe.throw(
			"<br>".join(
				_("{0}: start {1} + added {2}, end {3} ({4})").format(
					r.item, r.start_count or 0, r.added or 0, r.end_count or 0, r.result
				)
				for r in wrong
			),
			title=_("The counts don't balance"),
		)
	if not (doc.get("count_scrub_nurse") and doc.get("count_circulating_nurse")):
		frappe.throw(_("Name the scrub nurse and the circulating nurse who did the counts."))


# Anaesthesia record

SYSTEMS_REVIEW = (
	(
		"Cardiovascular",
		(
			"Hypertension / hypotension",
			"Easy fatiguability",
			"Murmur",
			"Chest pain / angina / CAD",
			"Congestive heart failure",
			"Arrhythmia",
			"Peripheral vascular disease",
			"Congenital / valvular heart disease",
		),
	),
	("Respiratory", ("Asthma", "TB", "COPD")),
	("Endocrine", ("Diabetes", "Thyroid disease", "Recent steroid use")),
	(
		"Neurological",
		("Seizures", "Elevated ICP", "Neuromuscular disease", "CVA / cerebrovascular disease"),
	),
	("Renal", ("Acute renal failure", "Chronic renal failure", "Haemodialysis")),
	(
		"Gastroenterological",
		("Hepatitis / cirrhosis / jaundice", "Increased risk of reflux", "Peptic ulcer disease"),
	),
)

# Lab result names (lower case) -> anaesthesia record field.
LAB_PATTERNS = (
	("lab_hb", re.compile(r"\bh(a)?emoglobin\b|\bhb\b")),
	("lab_hct", re.compile(r"h(a)?ematocrit|\bpcv\b|\bhct\b")),
	("lab_plt", re.compile(r"platelet|\bplt\b")),
	("lab_wbc", re.compile(r"white (blood )?cell|\bwbc\b|leu[ck]ocyte count|total leu[ck]ocyte")),
	("lab_inr", re.compile(r"\binr\b")),
	("lab_aptt", re.compile(r"\baptt\b|\bptt\b|partial thromboplastin")),
	("lab_pt", re.compile(r"prothrombin time|^pt\b|\(pt\)")),
)
LAB_DAYS = 30


def lab_field(test_name):
	name = (test_name or "").lower()
	# HbA1c and the red cell indices (MCH, MCHC, MPV, RDW) aren't Hb or platelets
	if any(word in name for word in ("a1c", "glyc", "mean ", "mch", "mpv", "distribution width")):
		return None
	for field, pattern in LAB_PATTERNS:
		if pattern.search(name):
			return field
	return None


@frappe.whitelist()
def latest_labs(patient: str, on=None) -> dict:
	"""The patient's latest Hb, Hct, platelets, WBC, PT, INR and APTT from
	submitted lab tests in the last LAB_DAYS days, as 'value unit'."""
	frappe.has_permission("Lab Test", "read", throw=True)
	since = add_to_date(get_datetime(on or now_datetime()), days=-LAB_DAYS)
	rows = frappe.db.sql(
		"""select r.lab_test_name, r.lab_test_event, r.result_value, r.lab_test_uom
		from `tabNormal Test Result` r join `tabLab Test` t on t.name = r.parent
		where r.parenttype = 'Lab Test' and t.patient = %s and t.docstatus = 1
			and coalesce(t.result_date, date(t.creation)) >= %s and coalesce(r.result_value, '') != ''
		order by coalesce(t.result_date, date(t.creation)) desc, t.creation desc, r.idx""",
		(patient, getdate(since)),
		as_dict=True,
	)
	found = {}
	for r in rows:
		field = lab_field(r.lab_test_event) or lab_field(r.lab_test_name)
		if field and field not in found:
			found[field] = f"{r.result_value} {r.lab_test_uom or ''}".strip()
	return found


def validate_anaesthesia(doc):
	if doc.is_new():
		if not doc.get("systems_review"):
			for system, findings in SYSTEMS_REVIEW:
				for finding in findings:
					doc.append("systems_review", {"system": system, "finding": finding})
		if not doc.get("allergies") and doc.get("patient"):
			doc.allergies = frappe.db.get_value("Patient", doc.patient, "allergies")
		if doc.get("patient") and not any(doc.get(f) for f, _p in LAB_PATTERNS):
			try:
				doc.update(latest_labs(doc.patient))
			except frappe.PermissionError:
				pass
	scores = [doc.get("gcs_e"), doc.get("gcs_m"), doc.get("gcs_v")]
	for value, top, label in zip(scores, (4, 6, 5), (_("eye"), _("motor"), _("verbal")), strict=True):
		if value and not 1 <= value <= top:
			frappe.throw(_("GCS {0} must be between 1 and {1}.").format(label, top))
	doc.gcs_total = sum(scores) if all(scores) else 0
	for start, end, label in (
		("induction_time", "end_time", _("anaesthesia")),
		("surgery_start", "surgery_end", _("surgery")),
	):
		if doc.get(start) and doc.get(end) and get_datetime(doc.get(end)) < get_datetime(doc.get(start)):
			frappe.throw(_("The end of {0} is before its start.").format(label))


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
