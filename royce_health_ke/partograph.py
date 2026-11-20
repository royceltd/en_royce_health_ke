# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""The Partograph on the ward's Nursing Charts (Bethesda's 7-section form,
feedback of 20 Nov 2026, PDF (11) pages 5-7).

One form writes into the maternity records we already keep:
- Patient information and blood group go on the Pregnancy Record (made here
  when the mother has none);
- labour progression and vital signs make one Labour Observation row per save,
  on a draft Delivery Record for this admission (so the Labour Care Guide and
  its alerts work as before);
- delivery details, the baby and the additional notes go on that Delivery
  Record and its Babies table.

"Complete Delivery" submits the Delivery Record: the pregnancy is marked
delivered and each live baby gets a patient record (maternity.py)."""

import json

import frappe
from frappe import _
from frappe.utils import add_to_date, cint, flt, get_datetime, now_datetime

IR = "Inpatient Record"
NAME = "Partograph"

PREGNANCY = ("gravida", "parity", "previous_cs", "haemoglobin")
OBSERVATION = (
	"cervical_dilatation_cm",
	"descent",
	"fetal_heart_rate",
	"contractions_per_10min",
	"contraction_duration_sec",
	"contraction_intensity",
	"liquor",
	"moulding",
	"oxytocin_rate",
	"drugs_and_fluids",
	"bp_systolic",
	"bp_diastolic",
	"temperature",
	"maternal_pulse",
	"urine_protein",
	"urine_acetone",
)
DELIVERY = (
	"first_stage_hours",
	"second_stage_minutes",
	"third_stage_minutes",
	"fourth_stage_hours",
	"vaginal_exams",
	"vaginal_exam_outcome",
	"mode_of_delivery",
	"maternal_condition",
	"uterotonic",
	"blood_loss_ml",
	"perineum",
	"mother_pulse",
	"mother_temperature",
	"mother_resp_rate",
	"other_complications",
	"delivery_datetime",
	"delivered_by",
)
DELIVERY_CHECKS = ("amtsl", "placenta_complete", "perineum_repaired")
COMPLICATIONS = {
	"APH": "aph",
	"PPH": "pph",
	"Eclampsia": "eclampsia",
	"Ruptured uterus": "ruptured_uterus",
	"Obstructed labour": "obstructed_labour",
	"Sepsis": "sepsis",
}
BABY = (
	"outcome",
	"sex",
	"apgar_1",
	"apgar_5",
	"apgar_10",
	"birth_weight_g",
	"length_cm",
	"head_circumference_cm",
	"deformity",
	"infant_prophylaxis",
	"cause_of_death",
	"drugs_given",
	"birth_notification_number",
)
BABY_CHECKS = ("teo", "chlorhexidine", "vitamin_k", "asphyxia", "resuscitated")


def _given(v):
	return v not in (None, "")


def _shown(doc, f):
	"""A stored value to show; numbers left empty are stored as 0."""
	v = doc.get(f)
	if v == 0 and doc.meta.get_field(f).fieldtype in ("Int", "Float"):
		return None
	return v


def _yes(v):
	return 1 if str(v).strip().lower() in ("yes", "1", "true") else 0


def _yes_no(v):
	return _("Yes") if cint(v) else _("No")


def applies(ip):
	"""The partograph is listed for women on the ward."""
	return frappe.db.get_value("Patient", ip.patient, "sex") == "Female"


def _pregnancy(patient, delivery=None):
	"""The delivery's pregnancy, else the mother's active one."""
	if delivery:
		return frappe.db.get_value("Delivery Record", delivery, "pregnancy_record")
	return frappe.db.get_value("Pregnancy Record", {"patient": patient, "status": "Active"}, "name")


def _delivery(ip_name):
	return frappe.db.get_value(
		"Delivery Record",
		{"inpatient_record": ip_name, "docstatus": ["<", 2]},
		"name",
		order_by="creation desc",
	)


def entry(ip):
	"""The partograph as one item of the Nursing Charts list."""
	delivery = _delivery(ip.name)
	status = None
	if delivery:
		status = (
			_("Delivered")
			if frappe.db.get_value("Delivery Record", delivery, "docstatus") == 1
			else _("In labour")
		)
	return {"name": NAME, "kind": "partograph", "status": status}


def _options():
	"""The choices of each select, from the doctypes, so the form keeps to them."""
	out = {}
	for doctype, fields in (
		("Labour Observation", OBSERVATION),
		("Delivery Record", DELIVERY),
		("Delivery Newborn", BABY),
	):
		meta = frappe.get_meta(doctype)
		for f in fields:
			df = meta.get_field(f)
			if df and df.fieldtype == "Select":
				out[f] = df.options or ""
	return out


@frappe.whitelist()
def get(inpatient_record: str) -> dict:
	"""What the form shows: saved values to fill it, the observations table."""
	ip = frappe.get_doc(IR, inpatient_record)
	ip.check_permission("read")
	out = {
		"values": {},
		"observations": [],
		"delivery": None,
		"docstatus": 0,
		"babies": 0,
		"options": _options(),
	}
	delivery = _delivery(ip.name)
	pregnancy = _pregnancy(ip.patient, delivery)
	if pregnancy:
		p = frappe.db.get_value(
			"Pregnancy Record", pregnancy, (*PREGNANCY, "blood_group", "hb_flag"), as_dict=True
		)
		out["values"].update({k: v for k, v in p.items() if _given(v) and k != "blood_group"})
		if p.blood_group:
			out["values"]["blood_group"] = p.blood_group[:-1]
			out["values"]["rhesus"] = _("Positive") if p.blood_group.endswith("+") else _("Negative")
		out["pregnancy"] = pregnancy
	if not delivery:
		return out
	d = frappe.get_doc("Delivery Record", delivery)
	v = out["values"]
	for f in DELIVERY:
		if _given(_shown(d, f)):
			v[f] = _shown(d, f)
	for f in DELIVERY_CHECKS:
		v[f] = _yes_no(d.get(f))
	if d.onset_of_labour:
		v["induction"] = _yes_no(d.onset_of_labour == "Induced")
	for label, f in COMPLICATIONS.items():
		if d.get(f):
			v["complication"] = label
			break
	if d.membranes_ruptured_datetime:
		v["membranes_ruptured_datetime"] = d.membranes_ruptured_datetime
	if d.babies:
		b = d.babies[0]
		for f in BABY:
			if _given(_shown(b, f)):
				v[f] = _shown(b, f)
		for f in BABY_CHECKS:
			v[f] = _yes_no(b.get(f))
	out.update(
		delivery=d.name,
		docstatus=d.docstatus,
		babies=len(d.babies),
		observations=[
			{
				**{f: _shown(r, f) for f in ("time", "alert", *OBSERVATION)},
				"by": frappe.utils.get_fullname(r.recorded_by) if r.recorded_by else "",
			}
			for r in sorted(d.labour_observations, key=lambda r: get_datetime(r.time), reverse=True)
		],
	)
	return out


@frappe.whitelist()
def record(inpatient_record: str, values: str | dict) -> str:
	"""Save one partograph entry; returns the Delivery Record."""
	values = frappe._dict(json.loads(values) if isinstance(values, str) else values)
	ip = frappe.get_doc(IR, inpatient_record)
	ip.check_permission("read")
	if not applies(ip):
		frappe.throw(_("The partograph is for women in labour."))
	when = get_datetime(values.get("observation_time") or now_datetime())

	name = _delivery(ip.name)
	if name and frappe.db.get_value("Delivery Record", name, "docstatus") == 1:
		frappe.throw(_("The delivery {0} is completed; open it to amend.").format(name))
	pregnancy = _save_pregnancy(ip, values, _pregnancy(ip.patient, name))
	d = (
		frappe.get_doc("Delivery Record", name)
		if name
		else frappe.get_doc(
			{
				"doctype": "Delivery Record",
				"pregnancy_record": pregnancy,
				"patient": ip.patient,
				"inpatient_record": ip.name,
				"company": ip.company,
				"admission_datetime": ip.admitted_datetime,
				"lcg_used": 1,
			}
		)
	)

	obs = {f: values.get(f) for f in OBSERVATION if _given(values.get(f))}
	if obs:
		d.append("labour_observations", {"time": when, "recorded_by": frappe.session.user, **obs})
	if _given(values.get("membranes_ruptured_hours")):
		d.membranes_ruptured_datetime = add_to_date(when, hours=-flt(values.membranes_ruptured_hours))
	if _given(values.get("induction")):
		d.onset_of_labour = "Induced" if _yes(values.induction) else "Spontaneous"
	for f in DELIVERY:
		if _given(values.get(f)):
			d.set(f, values.get(f))
	for f in DELIVERY_CHECKS:
		if _given(values.get(f)):
			d.set(f, _yes(values.get(f)))
	if _given(values.get("complication")) and values.complication in COMPLICATIONS:
		d.set(COMPLICATIONS[values.complication], 1)
	labour = [r for r in d.labour_observations if r.time]
	if labour and not d.active_labour_datetime:
		d.active_labour_datetime = min(get_datetime(r.time) for r in labour)
	if d.delivery_datetime and d.active_labour_datetime and not d.duration_of_labour_hours:
		hours = (get_datetime(d.delivery_datetime) - get_datetime(d.active_labour_datetime)).total_seconds()
		d.duration_of_labour_hours = flt(hours / 3600, 1) if hours > 0 else None

	baby = {f: values.get(f) for f in BABY if _given(values.get(f))}
	baby.update({f: _yes(values.get(f)) for f in BABY_CHECKS if _given(values.get(f))})
	if baby:
		row = d.babies[0] if d.babies else d.append("babies", {})
		row.update(baby)

	d.save()
	return d.name


def _save_pregnancy(ip, values, name):
	p = (
		frappe.get_doc("Pregnancy Record", name)
		if name
		else frappe.get_doc(
			{
				"doctype": "Pregnancy Record",
				"patient": ip.patient,
				"company": ip.company,
				"booking_date": get_datetime(ip.admitted_datetime or now_datetime()).date(),
				"status": "Active",
			}
		)
	)
	changed = p.is_new()
	for f in PREGNANCY:
		if _given(values.get(f)) and str(p.get(f) or "") != str(values.get(f)):
			p.set(f, values.get(f))
			changed = True
	if _given(values.get("blood_group")) and _given(values.get("rhesus")):
		group = values.blood_group + ("+" if values.rhesus in ("Positive", "+") else "-")
		if p.blood_group != group:
			p.blood_group, changed = group, True
	if changed:
		p.save()
	return p.name


@frappe.whitelist()
def complete(inpatient_record: str) -> str:
	"""Submit the admission's Delivery Record (the delivery is done)."""
	ip = frappe.get_doc(IR, inpatient_record)
	ip.check_permission("read")
	name = _delivery(ip.name)
	if not name:
		frappe.throw(_("Record the labour and the delivery on the partograph first."))
	d = frappe.get_doc("Delivery Record", name)
	if d.docstatus == 1:
		return d.name
	d.submit()
	return d.name
