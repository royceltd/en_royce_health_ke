# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Request types and where requests go (Bethesda proposals, 18 Nov 2026).

- Request Category (data, the hospital's): a type the doctor picks on the
  consultation's Requests tab (Laboratory, Imaging, Procedures, Nursing ...),
  which of Marley's request tables it draws from, optionally an item group,
  and the service point its requests go to.
- The Request Type picker filters the consultation's request tables: only
  that type's templates are offered, each with this patient's price (the
  scheme's pricebook when insured, else the cash price list).
- Every Service Request is stamped with its category and service point when
  it is placed; the next-station suggestion and the worklists read it.
- Nursing Worklist: the requests routed to Nursing (injections, dressings,
  nebulisation ...), done there with a note.

Marley's records stay as they are: the tables, templates and Service Requests
are Marley's; the category is a label on them."""

import frappe
from frappe import _
from frappe.utils import add_days, getdate, now_datetime, nowdate

CATEGORY = "Request Category"
SR = "Service Request"
NURSING = "Nursing"
NURSING_ROLES = ("Nursing User", "Healthcare Administrator", "System Manager")
NURSING_GROUP = "Nursing Procedures"
THEATRE = "Theatre"
SURGICAL_GROUP = "Surgical Procedures"

# kind -> (consultation table, template field, template doctype, template's item group field)
KINDS = {
	"Lab Test": ("lab_test_prescription", "lab_test_code", "Lab Test Template", "lab_test_group"),
	"Imaging": ("lab_test_prescription", "observation_template", "Observation Template", "item_group"),
	"Procedure": ("procedure_prescription", "procedure", "Clinical Procedure Template", "item_group"),
	"Therapy": ("therapies", "therapy_type", "Therapy Type", "item_group"),
}
# Before categories, where each kind went (consultation.STATION)
DEFAULT_POINT = {
	"Lab Test": "Laboratory",
	"Imaging": "Radiology",
	"Procedure": "Procedure Room",
	"Therapy": "Procedure Room",
}
DEFAULTS = (
	# (name, kind, item group, service point, sequence)
	("Laboratory", "Lab Test", None, "Laboratory", 10),
	("Imaging", "Imaging", None, "Radiology", 20),
	("Nursing", "Procedure", NURSING_GROUP, NURSING, 30),
	# the procedures done in theatre: requested here, booked from Theatre Requests
	(THEATRE, "Procedure", SURGICAL_GROUP, THEATRE, 35),
	("Procedures", "Procedure", None, "Procedure Room", 40),
	("Therapy and Counselling", "Therapy", None, "Procedure Room", 50),
)


def seed():
	"""The default request types and the Nursing Procedures item group, made
	once; afterwards they are the hospital's (ADR-023)."""
	if frappe.db.count(CATEGORY):
		return
	for row in DEFAULTS:
		_make_category(*row)
	clear_cache()


def _item_group(name):
	if not frappe.db.exists("Item Group", name):
		root = frappe.db.get_value(
			"Item Group", {"is_group": 1, "parent_item_group": ["in", ("", None)]}, "name"
		)
		frappe.get_doc(
			{
				"doctype": "Item Group",
				"item_group_name": name,
				"parent_item_group": root or "All Item Groups",
				"is_group": 0,
			}
		).insert(ignore_permissions=True)


def _make_category(name, kind, group, point, sequence):
	if group:
		_item_group(group)
	if frappe.db.exists(CATEGORY, name):
		return
	frappe.get_doc(
		{
			"doctype": CATEGORY,
			"category_name": name,
			"request_kind": kind,
			"item_group": group,
			"service_point": point,
			"sequence": sequence,
		}
	).insert(ignore_permissions=True)


def add_theatre():
	"""The Theatre request type, once, for sites that had their types before
	it existed (patch v0_55): skipped when one already goes to Theatre."""
	if frappe.db.exists(CATEGORY, {"service_point": THEATRE}):
		return
	row = next(r for r in DEFAULTS if r[0] == THEATRE)
	_make_category(*row)
	clear_cache()


def clear_cache():
	frappe.cache.delete_value("ke_request_categories")


def categories():
	def load():
		return frappe.get_all(
			CATEGORY,
			filters={"disabled": 0},
			fields=["name", "request_kind", "item_group", "service_point", "sequence"],
			order_by="sequence asc, name asc",
		)

	return [frappe._dict(c) for c in frappe.cache.get_value("ke_request_categories", load)]


def _groups(group):
	from frappe.utils.nestedset import get_descendants_of

	if not group or not frappe.db.exists("Item Group", group):
		return set()
	return {group, *get_descendants_of("Item Group", group)}


def kind_of(template_dt, template_dn):
	if template_dt == "Lab Test Template":
		return "Lab Test"
	if template_dt == "Observation Template":
		from royce_health_ke.radiology import IMAGING

		category = frappe.db.get_value("Observation Template", template_dn, "observation_category")
		return "Imaging" if category == IMAGING else "Lab Test"
	if template_dt == "Clinical Procedure Template":
		return "Procedure"
	if template_dt == "Therapy Type":
		return "Therapy"
	return None


def category_for(template_dt, template_dn):
	"""(category, service point) of a template: the type with an item group
	the template is in wins over a catch-all type (no item group)."""
	kind = kind_of(template_dt, template_dn)
	if not kind:
		return None, None
	group_field = KINDS[kind][3] if template_dt == KINDS[kind][2] else "item_group"
	group = frappe.db.get_value(template_dt, template_dn, group_field) if group_field else None
	catch_all = None
	for c in categories():
		if c.request_kind != kind:
			continue
		if c.item_group:
			if group and group in _groups(c.item_group):
				return c.name, c.service_point
		elif not catch_all:
			catch_all = c
	if catch_all:
		return catch_all.name, catch_all.service_point
	return None, DEFAULT_POINT[kind]


def route(doc, method=None):
	"""Service Request before_insert: its category and service point."""
	if not doc.get("template_dt") or not doc.get("template_dn"):
		return
	category, point = category_for(doc.template_dt, doc.template_dn)
	doc.ke_request_category = category
	doc.ke_service_point = point


def service_point(request):
	"""The service point of a Service Request (dict with name, template_dt,
	template_dn and maybe ke_service_point)."""
	point = request.get("ke_service_point")
	if point is None and request.get("name"):
		point = frappe.db.get_value(SR, request["name"], "ke_service_point")
	if point:
		return point
	return category_for(request.get("template_dt"), request.get("template_dn"))[1]


# The Request Type picker


@frappe.whitelist()
def picker(encounter: str | None = None) -> list:
	"""The request types for the consultation's picker: {name, kind, table, field}."""
	return [
		{
			"name": c.name,
			"kind": c.request_kind,
			"table": KINDS[c.request_kind][0],
			"field": KINDS[c.request_kind][1],
			"service_point": c.service_point,
		}
		for c in categories()
		if c.request_kind in KINDS
	]


def _patient_pricing(encounter):
	"""(company, policy) for prices: the visit's scheme when insured."""
	if not encounter:
		return None, None
	e = frappe.db.get_value("Patient Encounter", encounter, ["company", "ke_patient_visit"], as_dict=True)
	if not e:
		return None, None
	v = e.ke_patient_visit and frappe.db.get_value(
		"Patient Visit", e.ke_patient_visit, ["payment_method", "insurance_policy", "company"], as_dict=True
	)
	policy = v.insurance_policy if v and v.payment_method != "Cash" else None
	return (v and v.company) or e.company, policy


def _claimed_groups(kind, except_category):
	"""Item groups other types of this kind claim (a catch-all leaves them out)."""
	groups = set()
	for c in categories():
		if c.request_kind == kind and c.item_group and c.name != except_category:
			groups |= _groups(c.item_group)
	return groups


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def template_query(doctype, txt, searchfield, start, page_len, filters):
	"""A request table's template search, narrowed to the Request Type, with
	this patient's price."""
	from royce_health_ke import fees

	filters = frappe._dict(filters or {})
	category = filters.get("category")
	c = category and frappe.db.get_value(CATEGORY, category, ["request_kind", "item_group"], as_dict=True)
	kind = c.request_kind if c else filters.get("kind")
	if kind not in KINDS:
		return []
	_table, _field, template_dt, group_field = KINDS[kind]
	if doctype != template_dt:
		return []
	conditions = {"disabled": 0} if frappe.get_meta(template_dt).has_field("disabled") else {}
	if kind == "Imaging":
		conditions["observation_category"] = "Imaging"
	conditions["name"] = ["like", f"%{txt}%"]
	rows = frappe.get_all(
		template_dt, fields=["name", group_field, "item"], filters=conditions, order_by="name asc"
	)
	if c and c.item_group:
		allowed = _groups(c.item_group)
		rows = [r for r in rows if r.get(group_field) in allowed]
	elif c:
		claimed = _claimed_groups(kind, category)
		rows = [r for r in rows if r.get(group_field) not in claimed]
	rows = rows[int(start) : int(start) + int(page_len)]
	company, policy = _patient_pricing(filters.get("encounter"))
	out = []
	for r in rows:
		rate = fees.price(r.item, company, policy) if r.item else 0
		price = frappe.format_value(rate, {"fieldtype": "Currency"}) if rate else _("no price")
		out.append((r.name, price, r.get(group_field) or ""))
	return out


# Nursing Worklist


def _check_nursing():
	if not set(NURSING_ROLES) & set(frappe.get_roles()):
		frappe.throw(_("The Nursing Worklist is for nurses."), frappe.PermissionError)


@frappe.whitelist()
def nursing_worklist(tab: str = "waiting", from_date: str | None = None, to_date: str | None = None) -> list:
	"""The requests routed to Nursing: waiting, or done in the period."""
	from royce_health_ke import payment_status
	from royce_health_ke.lab import CLOSED_REQUEST

	_check_nursing()
	to_date = getdate(to_date or nowdate())
	from_date = getdate(from_date or add_days(to_date, -2))
	filters = {
		"docstatus": 1,
		"ke_service_point": NURSING,
		"status": ["not in", CLOSED_REQUEST],
	}
	if tab == "done":
		filters["ke_done_at"] = ["between", [f"{from_date} 00:00:00", f"{to_date} 23:59:59"]]
	else:
		filters["ke_done_at"] = ["is", "not set"]
		filters["order_date"] = ["between", [from_date, to_date]]
	rows = frappe.get_all(
		SR,
		filters=filters,
		fields=[
			"name",
			"patient",
			"patient_name",
			"template_dn",
			"order_date",
			"order_time",
			"practitioner_name",
			"order_group",
			"ke_patient_visit",
			"ke_request_category",
			"status",
			"ke_done_at",
			"ke_done_by",
			"ke_done_note",
			"order_description",
			"quantity",
		],
		order_by="order_date asc, order_time asc",
		limit=500,
	)
	for r in rows:
		status, exemption = payment_status.stored(SR, r.name)
		r.payment_status = status
		r.payment_exemption = exemption
		r.awaiting_payment = int(payment_status.awaiting(SR, r.name))
		r.comment = (
			frappe.db.get_value(SR, r.name, "comment") if frappe.get_meta(SR).has_field("comment") else ""
		)
	return rows


@frappe.whitelist()
def mark_done(request: str, note: str | None = None) -> dict:
	"""Done at the nursing station: the request is completed, with who, when
	and the nurse's note. A cash request not paid yet waits for the Cashier
	(Kenya Health Settings > Cashier before the lab, radiology and pharmacy)."""
	from royce_health_ke import payment_status
	from royce_health_ke.flow import setting
	from royce_health_ke.lab import CLOSED_REQUEST

	_check_nursing()
	sr = frappe.db.get_value(
		SR,
		request,
		["name", "status", "docstatus", "ke_service_point", "ke_done_at", "template_dn"],
		as_dict=True,
	)
	if not sr or sr.docstatus != 1:
		frappe.throw(_("Request {0} not found.").format(request))
	if sr.ke_done_at:
		frappe.throw(_("{0} is already done.").format(sr.template_dn))
	if sr.status in CLOSED_REQUEST:
		frappe.throw(_("{0} was cancelled.").format(sr.template_dn))
	if setting("cashier_before_service") and payment_status.awaiting(SR, request):
		frappe.throw(
			_("{0} is not paid yet: send the patient to the Cashier first.").format(sr.template_dn),
			title=_("Payment required"),
		)
	frappe.db.set_value(
		SR,
		request,
		{
			"status": "completed-Request Status",
			"ke_done_at": now_datetime(),
			"ke_done_by": frappe.session.user,
			"ke_done_note": (note or "").strip() or None,
		},
	)
	visit = frappe.db.get_value(SR, request, "ke_patient_visit")
	if visit:
		from royce_health_ke import visit_close

		visit_close.maybe_finish(visit)
	return {"done": request}


def open_nursing_items(request_names):
	"""Requests at Nursing not done yet, for closing a visit."""
	from royce_health_ke.lab import CLOSED_REQUEST

	if not request_names:
		return []
	return frappe.get_all(
		SR,
		filters={
			"name": ["in", request_names],
			"ke_service_point": NURSING,
			"ke_done_at": ["is", "not set"],
			"status": ["not in", (*CLOSED_REQUEST, "completed-Request Status")],
		},
		pluck="template_dn",
	)
