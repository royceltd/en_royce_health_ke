# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""The Order Drug panel on the consultation's Prescription tab (Bethesda,
"ERPNext HMIS Requirements & Workflow Overview (9)", page 4).

Left, one drug at a time (or a Drug Package): Drug Class, Drug Name with the
pharmacy's stock, Buy Externally, dose and unit, frequency (or every N hours),
duration, route, start, chronic. Right: Pending (this consultation, not sent),
Sent (this consultation), Active, Past and Chronic (the patient's other
prescriptions). Save to Draft keeps the pending drugs on the consultation;
Submit sends them to the pharmacy.

Everything is written into Marley's own Drug Prescription rows, so dispensing
(dispensing.py), billing, the pharmacy worklist and the ward are unchanged:
- A drug is the pharmacy's stock Item (Drug Prescription.drug_code); the
  Medication is filled in when one is linked to the Item.
- Drug Class is the Item Group under the pharmacy's drug group (Kenya Health
  Settings > Pharmacy): the hospital's own grouping.
- A Drug Package is a Treatment Plan Template with drugs (Marley's).
- Draft rows (ke_draft) are skipped when Marley makes Medication Requests
  (dispensing.EncounterOrders), so saving never sends them, even with
  "Saving the consultation sends its requests" on. Submit clears the flag.
- Buy Externally: the Medication Request is made already marked Buy Outside,
  so it is on the prescription but neither dispensed nor billed (as when the
  pharmacist marks it)."""

import frappe
from frappe import _
from frappe.utils import add_days, cint, get_datetime, getdate, nowdate

from royce_health_ke import dispensing, pharmacy

DT = "Patient Encounter"
MR = "Medication Request"
PACKAGE = "Treatment Plan Template"
UNITS = ("Day", "Week", "Month", "Hour")
HISTORY_LIMIT = 30


def _check(encounter=None, perm="write"):
	if encounter:
		doc = frappe.get_doc(DT, encounter)
		doc.check_permission(perm)
		return doc
	frappe.has_permission(DT, perm, throw=True)
	return None


def _groups(drug_class=None):
	groups = pharmacy.drug_groups()
	if drug_class and drug_class in groups:
		from frappe.utils.nestedset import get_descendants_of

		return [drug_class, *get_descendants_of("Item Group", drug_class)]
	return groups


@frappe.whitelist()
def drug_classes():
	"""The Item Groups under the pharmacy's drug group."""
	_check()
	groups = pharmacy.drug_groups()
	return sorted(groups[1:])


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def drug_query(doctype, txt, searchfield, start, page_len, filters):
	"""Drug Name: the pharmacy's drugs (of the class, if chosen), with stock."""
	_check()
	groups = _groups((filters or {}).get("drug_class"))
	if not groups:
		return []
	rows = frappe.db.sql(
		"""select name, item_name, stock_uom from `tabItem`
		where disabled = 0 and has_variants = 0 and item_group in %(groups)s
			and (name like %(like)s or item_name like %(like)s)
		order by item_name limit %(start)s, %(page_len)s""",
		{"groups": tuple(groups), "like": f"%{txt}%", "start": cint(start), "page_len": cint(page_len)},
		as_dict=True,
	)
	stock = pharmacy._stock([r.name for r in rows], pharmacy.default_warehouse())
	return [
		(
			r.name,
			r.item_name if r.item_name != r.name else "",
			_("Available: {0} {1}").format(frappe.format(stock.get(r.name) or 0, "Float"), r.stock_uom or ""),
		)
		for r in rows
	]


@frappe.whitelist()
def drug_info(item_code: str) -> dict:
	"""Stock and the Medication's defaults, to fill the Order Drug form."""
	_check()
	item = frappe.db.get_value("Item", item_code, ["name", "item_name", "stock_uom"], as_dict=True)
	if not item:
		frappe.throw(_("{0} is not a drug in this pharmacy.").format(item_code))
	warehouse = pharmacy.default_warehouse()
	medication = dispensing.medication_for_item(item_code)
	m = (
		frappe.db.get_value(
			"Medication",
			medication,
			[
				"default_prescription_dosage as dosage",
				"default_prescription_duration as period",
				"default_interval as interval",
				"default_interval_uom as interval_uom",
				"ke_dose_uom",
				"ke_default_route",
				"ke_prescription_only",
			],
			as_dict=True,
		)
		if medication
		else None
	) or frappe._dict()
	period = m.period and frappe.db.get_value(
		"Prescription Duration", m.period, ["number", "period"], as_dict=True
	)
	return {
		"item_code": item.name,
		"item_name": item.item_name,
		"stock_uom": item.stock_uom,
		"stock": (pharmacy._stock([item.name], warehouse) or {}).get(item.name, 0) if warehouse else None,
		"warehouse": warehouse,
		"medication": medication,
		"dose_uom": m.ke_dose_uom,
		"route": m.ke_default_route,
		"dosage": m.dosage,
		"duration": period and period.number,
		"duration_unit": period and period.period,
		"interval": m.interval,
		"interval_uom": m.interval_uom,
	}


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def package_query(doctype, txt, searchfield, start, page_len, filters):
	"""Drug Package: Treatment Plan Templates that carry drugs."""
	_check()
	return frappe.db.sql(
		"""select t.name, count(d.name) from `tabTreatment Plan Template` t
		join `tabDrug Prescription` d on d.parent = t.name and d.parenttype = 'Treatment Plan Template'
		where ifnull(t.disabled, 0) = 0 and t.name like %(like)s
		group by t.name order by t.name limit %(start)s, %(page_len)s""",
		{"like": f"%{txt}%", "start": cint(start), "page_len": cint(page_len)},
	)


ROW_FIELDS = (
	"drug_code",
	"drug_name",
	"medication",
	"ke_dose",
	"ke_dose_uom",
	"ke_route",
	"dosage",
	"period",
	"dosage_by_interval",
	"interval",
	"interval_uom",
	"comment",
	"ke_buy_externally",
	"ke_chronic",
)


@frappe.whitelist()
def package_drugs(package: str) -> list:
	"""The package's drugs, as rows for the consultation."""
	_check()
	frappe.has_permission(PACKAGE, "read", package, throw=True)
	return [
		{f: d.get(f) for f in ROW_FIELDS}
		for d in frappe.get_doc(PACKAGE, package).get("drugs") or []
		if d.get("drug_code")
	]


@frappe.whitelist()
def duration(number: int, unit: str = "Day") -> str:
	"""The Prescription Duration for '5 Day', made if the hospital has none."""
	_check()
	number = cint(number)
	if unit not in UNITS:
		frappe.throw(_("Duration unit must be one of {0}.").format(", ".join(UNITS)))
	if number < 1 or number > 366:
		frappe.throw(_("Duration must be from 1 to 366."))
	name = frappe.db.get_value("Prescription Duration", {"number": number, "period": unit})
	if name:
		return name
	doc = frappe.get_doc({"doctype": "Prescription Duration", "number": number, "period": unit})
	doc.insert(ignore_permissions=True)
	return doc.name


def _end(mr):
	start = getdate(get_datetime(mr.ke_start)) if mr.get("ke_start") else getdate(mr.order_date)
	return add_days(start, max(int(dispensing.days(mr.period)) - 1, 0)) if mr.period else start


def _row(mr):
	return {
		"name": mr.name,
		"encounter": mr.order_group,
		"drug_code": mr.medication_item,
		"medication": mr.medication,
		"drug": mr.medication or mr.medication_item,
		"instructions": pharmacy.instructions(mr),
		"quantity": mr.quantity,
		"order_date": mr.order_date,
		"practitioner": mr.practitioner_name,
		"pharmacy_status": mr.ke_pharmacy_status or pharmacy.WAITING,
		"chronic": cint(mr.ke_chronic),
		# to prescribe it again
		"ke_dose": mr.ke_dose,
		"ke_dose_uom": mr.ke_dose_uom,
		"ke_route": mr.ke_route,
		"dosage": mr.dosage,
		"period": mr.period,
		"comment": mr.comment,
	}


@frappe.whitelist()
def history(encounter: str) -> dict:
	"""Sent (this consultation), Active, Past and Chronic (the patient's others)."""
	doc = _check(encounter, "read")
	mrs = frappe.get_all(
		MR,
		filters={"patient": doc.patient, "docstatus": 1, "status": ["not in", pharmacy.CLOSED_MR[:3]]},
		fields=[
			"name",
			"order_group",
			"order_date",
			"medication",
			"medication_item",
			"quantity",
			"dosage",
			"period",
			"comment",
			"status",
			"practitioner_name",
			"ke_dose",
			"ke_dose_uom",
			"ke_route",
			"ke_start",
			"ke_chronic",
			"ke_pharmacy_status",
		],
		order_by="order_date desc, creation desc",
		limit=500,
	)
	today = getdate(nowdate())
	sent, active, past, chronic, seen = [], [], [], [], set()
	for mr in mrs:
		if mr.order_group == doc.name:
			sent.append(_row(mr))
			continue
		stopped = mr.status == "stopped-Medication Request Status"
		if not stopped and getdate(_end(mr)) >= today:
			active.append(_row(mr))
		elif len(past) < HISTORY_LIMIT:
			past.append(_row(mr))
		key = mr.medication_item or mr.medication
		if cint(mr.ke_chronic) and not stopped and key not in seen:
			seen.add(key)
			chronic.append(_row(mr))
	return {"sent": sent, "active": active, "past": past, "chronic": chronic}


@frappe.whitelist()
def submit(encounter: str) -> dict:
	"""Send the consultation's pending drugs (drafts included) to the pharmacy."""
	doc = _check(encounter)
	if doc.docstatus != 0:
		frappe.throw(_("This consultation is already completed."))
	pending = [
		d
		for d in doc.get("drug_prescription") or []
		if d.get("drug_code") and not d.get("medication_request")
	]
	if not pending:
		frappe.throw(_("No drugs to send: add one on the Order Drug panel first."))
	for d in pending:
		d.ke_draft = 0
	from royce_health_ke import consultation

	if consultation._rules_on() and not consultation.observation_exempt(doc):
		missing = consultation.missing_observation(doc)
		if missing:
			frappe.throw(
				_("Record the observation before prescribing. Still empty: {0}.").format(", ".join(missing)),
				title=_("Observation first"),
			)
	doc.save()
	if any(not d.get("medication_request") for d in doc.drug_prescription if d.get("drug_code")):
		doc.make_medication_request()
		doc.save()
	if doc.get("ke_patient_visit"):
		from royce_health_ke import visit_bill

		visit_bill.refresh_bill_status(doc.ke_patient_visit)
	return {"sent": len(pending)}


def check_no_drafts(doc):
	"""Completing the consultation: a drug left in draft would never reach the
	pharmacy, so it is sent or removed first."""
	from royce_health_ke.consultation import _submitting

	if not _submitting(doc):
		return
	drafts = [d.drug_name or d.drug_code for d in doc.get("drug_prescription") or [] if d.get("ke_draft")]
	if drafts:
		frappe.throw(
			_(
				"These drugs are still in draft: {0}. On the Prescription tab, Submit them to the pharmacy or "
				"remove them, then complete the consultation."
			).format(", ".join(frappe.bold(d) for d in drafts)),
			title=_("Drugs in draft"),
		)
