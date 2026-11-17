# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Who may do what: the hospital's role-access matrix (v0.44, DHA security
tests and ODPC safeguards), checked two ways.

- test_role_access pins it: a release that changes any role's access fails
  until this matrix is changed on purpose.
- The Compliance Check's "Role access" row compares the site with it: a role
  given MORE than the matrix is a Fail (a loosened role, named); a role given
  less is the hospital's choice and passes.

Deliberate choices (agreed 18 Nov 2026):
- Only reception and administrators edit a patient's registration
  (demographics). Doctors, nurses and the lab read it; the history a doctor
  records on the consultation updates the patient's record through the
  consultation (history.py), not by editing the patient.
- The Pharmacist reads consultations: dispensing safely needs the diagnosis
  and the prescriber's notes.
- Reception and the Cashier see no consultation, diagnosis or result
  (DHA: "a receptionist cannot see diagnoses").
- Ward nurses' access to consultations and lab results is decided with the
  inpatient work.

Rights per document type, in this order: Read, Write, Create, Submit,
Cancel, Delete ("-" = not allowed)."""

import frappe
from frappe import _

RIGHTS = ("read", "write", "create", "submit", "cancel", "delete")

# The roles as staff are given them (a cashier is also an Accounts User, a
# pharmacist a Stock User).
ROLE_GROUPS = {
	"Receptionist": ("Receptionist",),
	"Cashier": ("Cashier", "Accounts User"),
	"Physician": ("Physician",),
	"Laboratory User": ("Laboratory User",),
	"Pharmacist": ("Pharmacist", "Stock User"),
	"Healthcare Administrator": ("Healthcare Administrator",),
	"Nursing User": ("Nursing User",),
}

DOCTYPES = {
	"Patient": {
		"Receptionist": "RWC---",
		"Cashier": "R-----",
		"Physician": "R-----",
		"Laboratory User": "R-----",
		"Pharmacist": "R-----",
		"Healthcare Administrator": "RWC---",
		"Nursing User": "R-----",
	},
	"Patient Visit": {
		"Receptionist": "RWC---",
		"Cashier": "RW----",
		"Physician": "RW----",
		"Laboratory User": "RW----",
		"Pharmacist": "R-----",
		"Healthcare Administrator": "RWC---",
		"Nursing User": "RWC---",
	},
	"Vital Signs": {"Physician": "RWCSCD", "Nursing User": "RWCSCD"},
	"Patient Encounter": {"Physician": "RWCSCD", "Pharmacist": "R-----"},
	"Lab Test": {"Physician": "RW----", "Laboratory User": "RWCSC-"},
	"Observation": {"Physician": "RWCSC-", "Healthcare Administrator": "RWCSCD", "Nursing User": "RWCSC-"},
	"Medication Request": {
		"Physician": "RWC---",
		"Pharmacist": "R-----",
		"Healthcare Administrator": "RWC--D",
		"Nursing User": "R-----",
	},
	"Clinical Note": {"Physician": "RWC---", "Healthcare Administrator": "RWC---", "Nursing User": "RWC---"},
	"Patient Medical Record": {"Physician": "RWC--D", "Nursing User": "R-----"},
	"Inpatient Record": {
		"Physician": "RWC--D",
		"Healthcare Administrator": "RWC--D",
		"Nursing User": "RWC--D",
	},
	"Service Request": {
		"Physician": "RWC---",
		"Healthcare Administrator": "RWC--D",
		"Nursing User": "R-----",
	},
	"Sales Invoice": {"Cashier": "RWCS--", "Pharmacist": "RWC---"},
	"Payment Entry": {"Cashier": "RWCSCD"},
	"GL Entry": {"Cashier": "R-----"},
	"Patient Record Access": {"Healthcare Administrator": "R-----"},
	"Kenya Health Settings": {"Healthcare Administrator": "RWC---"},
}

# Pages and reports each role opens (the rest are closed to it).
EVERYONE_REPORTS = ("Medication Item wise Sales", "Planned vs Actual Therapy Session")
PAGES = {
	"Receptionist": (),
	"Cashier": ("patient-bills",),
	"Physician": ("results-inbox", "patient_history"),
	"Laboratory User": ("lab-worklist",),
	"Pharmacist": ("pharmacy-worklist",),
	"Healthcare Administrator": (
		"lab-worklist",
		"pharmacy-worklist",
		"results-inbox",
		"patient-bills",
		"patient_history",
	),
	"Nursing User": ("patient_history",),
}
REPORTS = {
	"Receptionist": ("Patients by Residence", *EVERYONE_REPORTS),
	"Cashier": EVERYONE_REPORTS,
	"Physician": (
		"Quality Measures",
		"Clinical Alert Summary",
		"IDSR Weekly Report",
		"Turnaround Time",
		"MOH 706 Laboratory Summary",
		"Ward Diet List",
		"Radiology Worklist",
		"Theatre List",
		"MOH 711 Integrated Summary",
		"MOH 717 Service Workload",
		"MOH 705 Outpatient Summary",
		"Emergency Triage Queue",
		"Diagnosis Trends",
		"Inpatient Medication Orders",
		"Patient Appointment Analytics",
		*EVERYONE_REPORTS,
	),
	"Laboratory User": (
		"Turnaround Time",
		"MOH 706 Laboratory Summary",
		"Patient Appointment Analytics",
		"Lab Test Report",
		*EVERYONE_REPORTS,
	),
	"Pharmacist": ("Pharmacy Stock Status", *EVERYONE_REPORTS),
	"Healthcare Administrator": None,  # every Kenya Health and Healthcare report
	"Nursing User": (
		"Linen Status",
		"Ward Diet List",
		"Radiology Worklist",
		"Theatre List",
		"Emergency Triage Queue",
		"Diagnosis Trends",
		"Inpatient Medication Orders",
		"Patient Appointment Analytics",
		"Lab Test Report",
		*EVERYONE_REPORTS,
	),
}
# Reports that show diagnoses or results: never for reception or the cashier.
CLINICAL_REPORTS = (
	"MOH 705 Outpatient Summary",
	"MOH 706 Laboratory Summary",
	"MOH 711 Integrated Summary",
	"IDSR Weekly Report",
	"Clinical Alert Summary",
	"Diagnosis Trends",
	"Lab Test Report",
	"Quality Measures",
)


def expected(doctype, group):
	return DOCTYPES.get(doctype, {}).get(group, "------")


def as_letters(rights):
	return "".join(r[0].upper() if rights.get(r) else "-" for r in RIGHTS)


def role_rights(doctype, roles):
	"""What these roles may do with the document type, from its role
	permissions (level 0, not "only if creator"), as Frappe reads them."""
	from frappe.permissions import AUTOMATIC_ROLES, get_valid_perms

	roles = [*roles, *(r for r in AUTOMATIC_ROLES if r not in ("Guest", "Administrator"))]
	rules = [p for p in get_valid_perms(doctype, roles=roles) if not p.get("if_owner")]
	submittable = frappe.get_meta(doctype).is_submittable
	rights = {}
	for right in RIGHTS:
		if right in ("submit", "cancel") and not submittable:
			rights[right] = False
		else:
			rights[right] = any(p.get(right) for p in rules)
	return rights


def loosened():
	"""(role, document type, has, expected) for every role given more than the matrix."""
	found = []
	for doctype in DOCTYPES:
		if not frappe.db.exists("DocType", doctype):
			continue
		for group, roles in ROLE_GROUPS.items():
			has = as_letters(role_rights(doctype, roles))
			want = expected(doctype, group)
			if any(h != "-" and w == "-" for h, w in zip(has, want, strict=True)):
				found.append((group, doctype, has, want))
	return found


def compliance_row(make_row):
	extra = loosened()
	return make_row(
		_("Access"),
		_("Each role has only the access the hospital's role matrix gives it"),
		not extra,
		"; ".join(f"{_(g)}: {_(d)} {h} (expected {w})" for g, d, h, w in extra) or _("as expected"),
		_("no role given more"),
		_("Role Permissions Manager (royce_health_ke/role_access.py lists the matrix)"),
	)
