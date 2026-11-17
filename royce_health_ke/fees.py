# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""The outpatient consultation fee, one rule for every hospital.

Which fee (an Item), the first that applies:
  1. the doctor's own consultation item (Practitioner > Charges), e.g. a
     consultant who charges the specialist fee;
  2. the Service Type's item for the department (Appointment Type > Billing),
     e.g. Review, Gynae clinic;
  3. the hospital default (Kenya Health Settings > Default Consultation Item,
     else Healthcare Settings > Out Patient Consulting Charge Item).

What it costs:
  - a fixed amount typed on the doctor, or on the Service Type's row, when
    there is one (Marley's way, kept so existing set-ups work);
  - otherwise the item's price on the patient's price list: the scheme's
    pricebook for an insured patient, the cash (selling) price list otherwise.
  A price of 0 means no fee (e.g. a free review).

Marley's own rule requires a typed amount and stops with an error without
one. Its billing helpers use this rule instead, in every request and job
(marley.install), so the visit bill, Create Bill, Get Items From >
Healthcare Services and the consultation's insurance cover price a
consultation the same way. Inpatient visit charges keep Marley's rule."""

import frappe
from frappe import _
from frappe.utils import flt

PRACTITIONER = "Healthcare Practitioner"
SETTINGS = "Kenya Health Settings"


def _department(doc):
	if doc.get("doctype") == "Patient Encounter":
		return doc.get("medical_department")
	return doc.get("department") or doc.get("medical_department")


def fee_item(doc):
	"""(item, fixed amount or 0, where it came from) for an outpatient
	consultation of `doc` (a visit, appointment or encounter, or a dict with
	practitioner / appointment_type / department)."""
	from healthcare.healthcare.utils import get_appointment_type_billing_details

	practitioner = doc.get("practitioner")
	if practitioner:
		item, amount = frappe.db.get_value(
			PRACTITIONER, practitioner, ["op_consulting_charge_item", "op_consulting_charge"]
		) or (None, 0)
		if item:
			return item, flt(amount), "practitioner"
	if doc.get("appointment_type"):
		where = _department(doc) or doc.get("service_unit")
		service_type = doc.get("appointment_type")
		item, amount = get_appointment_type_billing_details(service_type, where, False)
		if not item and where:
			# a Service Type with one row for every department
			item, amount = get_appointment_type_billing_details(service_type, "", False)
		if item:
			return item, flt(amount), "service type"
	item = frappe.db.get_single_value(SETTINGS, "default_consultation_item") or frappe.db.get_single_value(
		"Healthcare Settings", "op_consulting_charge_item"
	)
	return item, 0, "default" if item else None


def price(item, company=None, policy=None, price_list=None):
	"""The item's price for this patient: the scheme's pricebook when insured
	(and it prices the item), else `price_list`, else the cash price list."""
	from royce_health_ke.schemes import scheme_price

	if not item:
		return 0
	if policy:
		found = scheme_price(policy, item, company)
		if found:
			return flt(found[1])
	price_list = price_list or frappe.db.get_single_value("Selling Settings", "selling_price_list")
	filters = {"item_code": item, "selling": 1}
	if price_list:
		filters["price_list"] = price_list
	return flt(frappe.db.get_value("Item Price", filters, "price_list_rate", order_by="valid_from desc"))


def _policy(doc):
	if doc.get("payment_method") == "Cash":
		return None
	return doc.get("insurance_policy")


def consultation_fee(doc, priced=True):
	"""(item, rate) of the consultation fee; rate 0 when there is none.
	`priced=False`: the fixed amount only (0 = the invoice prices it from
	the patient's price list)."""
	item, amount, _source = fee_item(doc)
	if not item:
		return None, 0
	if amount or not priced:
		return item, amount
	return item, price(item, doc.get("company"), _policy(doc))


def explain(doc):
	"""Why a cash consultation has no fee, for reception; None when it has one."""
	item, amount, source = fee_item(doc)
	if not item:
		return _(
			"No consultation fee is set: give the doctor a consultation item, the Service Type a charge, "
			"or set Kenya Health Settings > Default Consultation Item."
		)
	cash = frappe.db.get_single_value("Selling Settings", "selling_price_list")
	if amount or frappe.db.exists("Item Price", {"item_code": item, "price_list": cash, "selling": 1}):
		# a price of 0 is a hospital's choice (e.g. a free review), not a gap
		return None
	return _("The consultation item {0} (from the {1}) has no price on the cash price list {2}.").format(
		frappe.bold(item), _(source), cash
	)


# Marley's billing helpers, with this rule


def billing_item_and_rate(doc):
	"""Drop-in for Marley's get_appointment_billing_item_and_rate:
	{service_item, practitioner_charge}. A charge of None lets the invoice
	price the item from the patient's price list."""
	from royce_health_ke.marley import original_billing_item_and_rate as marley

	if isinstance(doc, str):
		import json

		doc = json.loads(doc)
	if isinstance(doc, dict) and not hasattr(doc, "meta"):
		doc = frappe._dict(doc)
	if doc.get("inpatient_record"):
		return marley(doc)
	item, amount, _source = fee_item(doc)
	if not item:
		frappe.throw(
			_("Set a consultation item: on the doctor, on the Service Type, or in Kenya Health Settings."),
			title=_("Missing Configuration"),
		)
	return {"service_item": item, "practitioner_charge": amount or None}


@frappe.whitelist()
def get_healthcare_services_to_invoice(
	patient: str, customer: str, company: str, link_customer: bool = False
) -> list[dict]:
	"""Get Items From > Healthcare Services on an invoice, with this fee rule."""
	from healthcare.healthcare.utils import get_healthcare_services_to_invoice as marley

	from royce_health_ke.marley import install

	install()
	return marley(patient, customer, company, link_customer)


@frappe.whitelist()
def get_appointment_billing_item_and_rate(doc: str | dict) -> dict:
	"""The appointment form's fee preview, with this fee rule."""
	return billing_item_and_rate(doc)
