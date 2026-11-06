# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Family planning visits, as on the MOH FP register (MOH 512) and counted on
MOH 711. Visit type: New the first time a client gets a method here,
Revisit after that (unless the provider sets it)."""

import frappe
from frappe import _

LARC = ("Implant (1 rod)", "Implant (2 rods)", "Hormonal IUCD", "Non-hormonal IUCD")
FEMALE_ONLY = (
	"Progestin only pills",
	"Combined oral contraceptive pills",
	"Emergency contraceptive pill",
	"DMPA-IM",
	"DMPA-SC",
	"Cycle beads",
	"BTL",
	*LARC,
)
MALE_ONLY = ("Vasectomy",)


def validate_visit(doc):
	if doc.method in LARC:
		if not doc.procedure:
			frappe.throw(_("Say whether the {0} was inserted, reinserted or removed.").format(doc.method))
	else:
		doc.procedure = None
	sex = frappe.db.get_value("Patient", doc.patient, "sex")
	if sex == "Male" and doc.method in FEMALE_ONLY:
		frappe.throw(
			_("{0} is a method for women; {1} is recorded as male.").format(doc.method, doc.patient_name)
		)
	if sex == "Female" and doc.method in MALE_ONLY:
		frappe.throw(
			_("{0} is a method for men; {1} is recorded as female.").format(doc.method, doc.patient_name)
		)
	if not doc.visit_type:
		doc.visit_type = "Revisit" if earlier_visits(doc) else "New"


def earlier_visits(doc):
	return frappe.db.count(
		"Family Planning Visit",
		{
			"patient": doc.patient,
			"method": doc.method,
			"docstatus": 1,
			"name": ["!=", doc.name],
			"visit_date": ["<=", doc.visit_date],
		},
	)
