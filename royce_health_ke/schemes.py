# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Pricebooks: each payment category bills at its own prices.

ERPNext Price Lists are the pricebooks. Cash patients pay the default selling
price list. An insurance scheme (Insurance Payor Eligibility Plan) names its
price list, and several schemes may share one (SHA-Mwalimu, UASALAMA and
POMSF at one list, say); an insurer's contract can name a default for its
schemes. Marley prices insured services from those lists. Two gaps closed
here:

- A consultation opened from an insured visit (no appointment) had no
  insurance cover, so the consultation fee was billed to the patient. It
  now gets cover on submit, as Marley gives an insured appointment.
- Marley prices a consultation's cover at the doctor's cash charge. The
  scheme's own price for the consultation item wins when it has one."""

import frappe
from frappe import _
from frappe.utils import flt


def scheme_price(policy, item_code, company):
	"""(price list, rate) for the item in the policy's scheme price list, else
	its insurer's contract list; None when neither prices it. The default
	selling (cash) list never counts as a scheme's."""
	from healthcare.healthcare.doctype.patient_insurance_coverage.patient_insurance_coverage import (
		get_item_price_list_rate,
	)
	from healthcare.healthcare.doctype.patient_insurance_policy.patient_insurance_policy import (
		get_insurance_price_lists,
	)

	if not (policy and item_code):
		return None
	lists = get_insurance_price_lists(policy, company) or {}
	cash = frappe.db.get_single_value("Selling Settings", "selling_price_list")
	for key in ("plan_price_list", "default_price_list"):
		price_list = lists.get(key)
		if not price_list or price_list == cash:
			continue
		if not frappe.db.exists("Item Price", {"price_list": price_list, "item_code": item_code}):
			continue
		rate = flt(get_item_price_list_rate(item_code, price_list, 1, company))
		if rate:
			return price_list, rate
	return None


def price_consultation_cover(doc, method=None):
	"""Patient Insurance Coverage before_validate: a new consultation cover
	(template Appointment Type) takes the scheme's price."""
	if doc.docstatus != 0 or not doc.is_new() or doc.template_dt != "Appointment Type":
		return
	found = scheme_price(doc.insurance_policy, doc.item_code, doc.company)
	if found:
		doc.price_list, doc.price_list_rate = found


def cover_consultation(doc, method=None):
	"""Patient Encounter on_submit: insurance cover for the consultation fee
	of an insured consultation without an appointment (one opened from an
	insured visit). An appointment's own cover bills its fee."""
	from healthcare.healthcare.doctype.patient_insurance_coverage.patient_insurance_coverage import (
		make_insurance_coverage,
	)
	from healthcare.healthcare.utils import get_appointment_billing_item_and_rate

	if not doc.get("insurance_policy") or doc.get("insurance_coverage") or doc.get("appointment"):
		return
	if doc.get("inpatient_record") and frappe.db.get_single_value(
		"Healthcare Settings", "do_not_bill_inpatient_encounters"
	):
		return
	try:
		billing = get_appointment_billing_item_and_rate(doc)
		cover = make_insurance_coverage(
			patient=doc.patient,
			policy=doc.insurance_policy,
			company=doc.company,
			template_dt="Appointment Type" if doc.get("appointment_type") else None,
			template_dn=doc.get("appointment_type"),
			item_code=billing.get("service_item"),
			qty=1,
			rate=billing.get("practitioner_charge"),
		)
	except frappe.ValidationError as e:
		# no contract or no fee set up: the fee is billed to the patient as before
		frappe.clear_last_message()
		frappe.msgprint(
			_("The consultation fee is not covered by insurance: {0}").format(
				frappe.utils.strip_html(str(e))
			),
			indicator="orange",
			alert=True,
		)
		return
	if cover and cover.get("coverage"):
		doc.db_set("insurance_coverage", cover.get("coverage"))
