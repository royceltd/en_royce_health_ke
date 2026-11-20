# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Immunisation (the child welfare clinic's register) and MOH 710
(immunisation, vitamin A and EPI summary; Bethesda's "CWC = 710" note).

- Immunisation Dose: the schedule as data (KEPI, seeded once; the hospital
  disables what its county doesn't give and edits ages).
- Immunisation: one dose given, at this facility or copied from the child's
  card (that one completes the schedule but MOH 710 doesn't count it).
- On the patient: the schedule with each dose given, due, overdue or not yet
  due, and Record Dose.
- MOH 710: doses given here in the period by age (under 1 year, 1 year and
  over), and fully immunised children (every dose ticked "Needed for Fully
  Immunised Child", the last one given here in the period before the first
  birthday)."""

import frappe
from frappe import _
from frappe.utils import add_days, cint, date_diff, getdate, nowdate

DOSE = "Immunisation Dose"
RECORD = "Immunisation"
YEAR = 365
CHILD_UNTIL = 5 * YEAR  # child doses are shown up to 5 years
OVERDUE_AFTER = 28  # days after the due date

# (dose, vaccine, for whom, due age in days, fully immunised, repeat every, until age)
SCHEDULE = (
	("BCG", "BCG", "Child", 0, 1, None, None),
	("OPV 0 (birth)", "OPV", "Child", 0, 0, None, 14),
	("OPV 1", "OPV", "Child", 42, 1, None, None),
	("Pentavalent 1", "DPT-HepB-Hib", "Child", 42, 1, None, None),
	("PCV10 1", "Pneumococcal", "Child", 42, 1, None, None),
	("Rotavirus 1", "Rotavirus", "Child", 42, 0, None, 105),
	("OPV 2", "OPV", "Child", 70, 1, None, None),
	("Pentavalent 2", "DPT-HepB-Hib", "Child", 70, 1, None, None),
	("PCV10 2", "Pneumococcal", "Child", 70, 1, None, None),
	("Rotavirus 2", "Rotavirus", "Child", 70, 0, None, 245),
	("OPV 3", "OPV", "Child", 98, 1, None, None),
	("Pentavalent 3", "DPT-HepB-Hib", "Child", 98, 1, None, None),
	("PCV10 3", "Pneumococcal", "Child", 98, 1, None, None),
	("IPV", "Inactivated polio", "Child", 98, 1, None, None),
	("Vitamin A 100,000 IU (6-11 months)", "Vitamin A", "Child", 182, 0, None, 364),
	("Malaria vaccine 1", "Malaria (RTS,S / R21)", "Child", 182, 0, None, None),
	("Malaria vaccine 2", "Malaria (RTS,S / R21)", "Child", 213, 0, None, None),
	("Malaria vaccine 3", "Malaria (RTS,S / R21)", "Child", 243, 0, None, None),
	("Measles-Rubella 1", "Measles-Rubella", "Child", 270, 1, None, None),
	("Yellow Fever", "Yellow Fever", "Child", 270, 0, None, None),
	("Vitamin A 200,000 IU (12-59 months)", "Vitamin A", "Child", 365, 0, 182, 1825),
	("Measles-Rubella 2", "Measles-Rubella", "Child", 548, 0, None, None),
	("Malaria vaccine 4", "Malaria (RTS,S / R21)", "Child", 730, 0, None, None),
	("HPV 1", "HPV", "Girl", 3650, 0, None, 5475),
	("Td 1", "Tetanus-diphtheria", "Woman", None, 0, None, None),
	("Td 2", "Tetanus-diphtheria", "Woman", None, 0, None, None),
	("Td 3", "Tetanus-diphtheria", "Woman", None, 0, None, None),
	("Td 4", "Tetanus-diphtheria", "Woman", None, 0, None, None),
	("Td 5", "Tetanus-diphtheria", "Woman", None, 0, None, None),
)


def seed():
	"""The KEPI schedule, once (afterwards the hospital's)."""
	if frappe.db.count(DOSE):
		return
	for i, (dose, vaccine, whom, due, fic, repeat, until) in enumerate(SCHEDULE, start=1):
		frappe.get_doc(
			{
				"doctype": DOSE,
				"dose_name": dose,
				"vaccine": vaccine,
				"for_whom": whom,
				"due_age_days": due,
				"counts_for_fic": fic,
				"repeat_every_days": repeat,
				"until_age_days": until,
				"sequence": i * 10,
			}
		).insert(ignore_permissions=True)


def age_text(days):
	if days is None:
		return ""
	if days < 7 * 8:
		return _("{0} weeks").format(days // 7) if days >= 14 else _("{0} days").format(days)
	if days < YEAR * 2:
		return _("{0} months").format(round(days / 30.4))
	return _("{0} years").format(days // YEAR)


def validate_dose_given(doc):
	patient = frappe.db.get_value("Patient", doc.patient, ["dob", "sex"], as_dict=True)
	dose = frappe.get_cached_doc(DOSE, doc.dose)
	if getdate(doc.given_on) > getdate(nowdate()):
		frappe.throw(_("A dose can't be given in the future."))
	if patient.dob:
		if getdate(doc.given_on) < getdate(patient.dob):
			frappe.throw(_("The dose date is before the patient's date of birth."))
		doc.age_days = date_diff(doc.given_on, patient.dob)
		doc.age_label = age_text(doc.age_days)
	if dose.for_whom in ("Girl", "Woman") and patient.sex and patient.sex != "Female":
		frappe.throw(_("{0} is for women and girls.").format(doc.dose))
	same = frappe.get_all(
		RECORD,
		filters={"patient": doc.patient, "dose": doc.dose, "name": ["!=", doc.name]},
		pluck="given_on",
	)
	if same and not cint(dose.repeat_every_days):
		frappe.throw(_("{0} is already recorded for this patient ({1}).").format(doc.dose, same[0]))
	doc.given_by = doc.given_by or frappe.session.user
	if not doc.company:
		doc.company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value(
			"Global Defaults", "default_company"
		)


def _eligible(dose, sex, age):
	if dose.for_whom == "Girl":
		return sex == "Female" and 9 * YEAR <= age <= 15 * YEAR
	if dose.for_whom == "Woman":
		return sex == "Female" and age >= 15 * YEAR
	return age <= CHILD_UNTIL


@frappe.whitelist()
def schedule(patient: str) -> dict:
	"""The patient's schedule: each dose given (dates), due, overdue or upcoming."""
	frappe.has_permission(RECORD, "read", throw=True)
	p = frappe.db.get_value("Patient", patient, ["patient_name", "dob", "sex"], as_dict=True)
	today = getdate(nowdate())
	age = date_diff(today, p.dob) if p.dob else None
	given = {}
	for r in frappe.get_all(
		RECORD,
		filters={"patient": patient},
		fields=["name", "dose", "given_on", "given_here", "batch_number"],
		order_by="given_on asc",
	):
		given.setdefault(r.dose, []).append(r)
	rows = []
	for d in frappe.get_all(
		DOSE,
		filters={"disabled": 0},
		fields=["name", "vaccine", "for_whom", "due_age_days", "repeat_every_days", "until_age_days"],
		order_by="sequence asc",
	):
		done = given.get(d.name, [])
		if not done and (age is None or not _eligible(d, p.sex, age)):
			continue
		status, due = "Given", None
		if not done or cint(d.repeat_every_days):
			if done:
				due = add_days(done[-1].given_on, cint(d.repeat_every_days))
			elif d.due_age_days is not None and p.dob:
				due = add_days(p.dob, cint(d.due_age_days))
			if d.until_age_days and p.dob and age > cint(d.until_age_days):
				status = "Given" if done else "Too late"
			elif due is None:
				status = "When needed" if not done else "Given"
			elif getdate(due) > today:
				status = "Given" if done else "Not yet due"
			elif date_diff(today, due) > OVERDUE_AFTER:
				status = "Overdue"
			else:
				status = "Due"
		rows.append(
			{
				"dose": d.name,
				"vaccine": d.vaccine,
				"due": due,
				"status": status,
				"given": [{"on": g.given_on, "here": g.given_here, "batch": g.batch_number} for g in done],
			}
		)
	return {"patient_name": p.patient_name, "age": age_text(age), "rows": rows}


@frappe.whitelist()
def record(
	patient: str,
	dose: str,
	given_on: str | None = None,
	batch_number: str | None = None,
	given_here: int = 1,
	notes: str | None = None,
) -> str:
	doc = frappe.get_doc(
		{
			"doctype": RECORD,
			"patient": patient,
			"dose": dose,
			"given_on": given_on or nowdate(),
			"batch_number": batch_number,
			"given_here": cint(given_here),
			"notes": notes,
		}
	)
	doc.insert()
	return doc.name


def moh710(start, end, company=None):
	"""Doses given here in the period, by age, and fully immunised children."""
	filters = {"given_here": 1, "given_on": ["between", [start, end]]}
	if company:
		filters["company"] = company
	given = frappe.get_all(RECORD, filters=filters, fields=["patient", "dose", "given_on", "age_days"])
	counts = {}
	for g in given:
		c = counts.setdefault(g.dose, [0, 0])
		c[0 if (g.age_days or 0) < YEAR else 1] += 1
	rows = []
	for d in frappe.get_all(DOSE, filters={"disabled": 0}, fields=["name"], order_by="sequence asc"):
		under, over = counts.get(d.name, [0, 0])
		rows.append({"indicator": d.name, "under_1": under, "over_1": over, "total": under + over})
	fic = fully_immunised(start, end, company)
	rows.append(
		{"indicator": _("Fully Immunised Child (under 1 year)"), "under_1": fic, "total": fic, "bold": 1}
	)
	return rows


def fully_immunised(start, end, company=None):
	"""Children whose last needed dose was given here in the period before
	their first birthday, with every needed dose recorded."""
	needed = set(frappe.get_all(DOSE, filters={"disabled": 0, "counts_for_fic": 1}, pluck="name"))
	if not needed:
		return 0
	filters = {"given_here": 1, "given_on": ["between", [start, end]], "dose": ["in", list(needed)]}
	if company:
		filters["company"] = company
	patients = set(frappe.get_all(RECORD, filters=filters, pluck="patient"))
	count = 0
	for patient in patients:
		doses = frappe.get_all(
			RECORD,
			filters={"patient": patient, "dose": ["in", list(needed)]},
			fields=["dose", "given_on", "age_days", "given_here"],
			order_by="given_on asc",
		)
		if not needed <= {d.dose for d in doses}:
			continue
		last = doses[-1]
		if (
			last.given_here
			and getdate(start) <= getdate(last.given_on) <= getdate(end)
			and (last.age_days or 0) < YEAR
		):
			count += 1
	return count
