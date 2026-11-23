# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""ICD-11 on the consultation's diagnosis (Bethesda proposals, 18 Nov 2026).

One row, two columns: Diagnosis (the name) and ICD-11 Code. The doctor
searches either by name or by code; the other column fills in.

Underneath it stays Marley's: the row links a Diagnosis record, and that
Diagnosis carries the ICD-11 code in its codification table. MOH 705,
disease surveillance and clinical alerts read it that way already. The
consultation's own codification table gets the code too (claims and the HIE
read the encounter's codes).

A Diagnosis is made from an ICD-11 code the first time a doctor picks it
(named by WHO's title), so the hospital's list grows with what is used, not
with all 35,000 codes. A hospital's own Diagnosis records stay as they are;
picking one that has no ICD-11 code yet asks for the code."""

import frappe
from frappe import _

from royce_health_ke.codes import ICD11, set_coding

DX = "Diagnosis"
PAGE = 20


def _like(txt):
	return f"%{(txt or '').strip()}%"


def _code_rows(txt, limit):
	"""ICD-11 codes by code (prefix) or title (contains), the code matches first."""
	txt = (txt or "").strip()
	if not txt:
		return []
	return frappe.db.sql(
		"""select name, code_value, display from `tabCode Value`
		where code_system = %(system)s and (code_value like %(prefix)s or display like %(like)s)
		order by (code_value like %(prefix)s) desc, (display like %(starts)s) desc,
			char_length(display), code_value
		limit %(limit)s""",
		{
			"system": ICD11,
			"prefix": f"{txt}%",
			"like": _like(txt),
			"starts": f"{txt}%",
			"limit": int(limit),
		},
		as_dict=True,
	)


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def icd11_query(doctype, txt, searchfield, start, page_len, filters):
	"""ICD-11 Code column: search by code or name."""
	rows = _code_rows(txt, int(start) + int(page_len))[int(start) :]
	return [(r.name, r.code_value, r.display) for r in rows]


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def diagnosis_query(doctype, txt, searchfield, start, page_len, filters):
	"""Diagnosis column: the hospital's diagnoses, then ICD-11 titles not made
	into a diagnosis yet (picked by name; resolve() makes the record)."""
	txt = (txt or "").strip()
	limit = int(start) + int(page_len)
	own = frappe.db.sql(
		"""select d.name, ifnull(c.code, '') as code from `tabDiagnosis` d
		left join `tabCodification Table` c
			on c.parent = d.name and c.parenttype = 'Diagnosis' and c.code_system = %(system)s
		where d.name like %(like)s or c.code like %(prefix)s
		order by (d.name like %(starts)s) desc, char_length(d.name)
		limit %(limit)s""",
		{"system": ICD11, "like": _like(txt), "prefix": f"{txt}%", "starts": f"{txt}%", "limit": limit},
		as_dict=True,
	)
	seen = {r.name for r in own}
	out = [(r.name, f"ICD-11 {r.code}" if r.code else _("no ICD-11 code")) for r in own]
	for r in _code_rows(txt, limit):
		title = (r.display or "")[:140]
		if title and title not in seen:
			seen.add(title)
			out.append((title, f"ICD-11 {r.code_value}"))
	return out[int(start) : limit]


def icd11_of(diagnosis):
	"""(Code Value name, code) of a Diagnosis's ICD-11 coding."""
	row = frappe.db.get_value(
		"Codification Table",
		{"parenttype": DX, "parent": diagnosis, "code_system": ICD11},
		["code_value", "code"],
		as_dict=True,
	)
	return (row.code_value, row.code) if row else (None, None)


def _code_by_title(title):
	return frappe.db.get_value(
		"Code Value",
		{"code_system": ICD11, "display": title},
		["name", "code_value", "display"],
		as_dict=True,
	)


def ensure_diagnosis(code_value):
	"""The Diagnosis for an ICD-11 Code Value, made (named by its title) when
	there is none yet."""
	cv = frappe.db.get_value(
		"Code Value", code_value, ["name", "code_system", "code_value", "display"], as_dict=True
	)
	if not cv or cv.code_system != ICD11:
		frappe.throw(_("{0} is not an ICD-11 code.").format(code_value))
	existing = frappe.db.get_value(
		"Codification Table", {"parenttype": DX, "code_value": cv.name, "code_system": ICD11}, "parent"
	)
	if existing:
		return existing
	title = (cv.display or cv.code_value)[:140]
	if frappe.db.exists(DX, title):
		doc = frappe.get_doc(DX, title)
		if icd11_of(title)[0]:
			# the hospital's diagnosis of that name has another code: keep it apart
			title = f"{title[:120]} ({cv.code_value})"
			if frappe.db.exists(DX, title):
				return title
			doc = frappe.new_doc(DX)
			doc.diagnosis = title
	else:
		doc = frappe.new_doc(DX)
		doc.diagnosis = title
	set_coding(doc, ICD11, cv.code_value, cv.display)
	doc.flags.ignore_permissions = True
	doc.save()
	return doc.name


@frappe.whitelist()
def resolve(diagnosis: str | None = None, code_value: str | None = None) -> dict:
	"""Fill the other column of a diagnosis row: {diagnosis, code_value, code}."""
	if not (
		frappe.has_permission("Patient Encounter", "write")
		or frappe.has_permission("Patient Encounter", "create")
	):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	if code_value:
		name = ensure_diagnosis(code_value)
		return {
			"diagnosis": name,
			"code_value": code_value,
			"code": frappe.db.get_value("Code Value", code_value, "code_value"),
		}
	if not diagnosis:
		return {}
	found = match(diagnosis)
	if not found:
		# typed, not picked from the list: say so with the nearest choices, no error
		# (Bethesda, 23 Nov 2026: name and code fill each other)
		return {
			"not_found": diagnosis,
			"suggestions": [r[0] for r in diagnosis_query(DX, diagnosis, "name", 0, 5, {})],
		}
	return found


def match(text):
	"""{diagnosis, code_value, code} for a diagnosis typed rather than picked:
	the hospital's diagnosis of that name, an ICD-11 code typed in the name
	(1F4Z), or an ICD-11 title (case aside, as the database compares). None
	when nothing matches exactly."""
	text = (text or "").strip()
	if not text:
		return None
	name = frappe.db.get_value(DX, text, "name")
	if name:
		cv, code = icd11_of(name)
		return {"diagnosis": name, "code_value": cv, "code": code}
	by_code = frappe.db.get_value(
		"Code Value", {"code_system": ICD11, "code_value": text.upper()}, ["name", "code_value"], as_dict=True
	)
	cv = by_code or _code_by_title(text)
	if not cv:
		return None
	return {"diagnosis": ensure_diagnosis(cv.name), "code_value": cv.name, "code": cv.code_value}


@frappe.whitelist()
def get_medical_codes(template_dt: str, template_dn: str | None = None, code_standard: str | None = None):
	"""Marley's get_medical_codes (hooks: override_whitelisted_methods). Marley
	asks for a diagnosis row's codes as soon as the row is added; since the
	diagnosis is a table (v0.47.2) a new row is empty, which made Marley's
	method fail with "missing template_dn" (Bethesda, 19 Nov 2026). An empty
	row has no codes; the codes come on save (sync_rows)."""
	if not template_dn:
		return []
	from royce_health_ke.marley import get_medical_codes as marley_codes

	return marley_codes(template_dt, template_dn, code_standard)


def sync_rows(doc, method=None):
	"""Patient Encounter before_validate: each diagnosis row has its record and
	its ICD-11 code, and the consultation carries the codes (claims)."""
	for row in doc.get("diagnosis") or []:
		if row.get("ke_icd11_code") and not row.get("diagnosis"):
			row.diagnosis = ensure_diagnosis(row.ke_icd11_code)
		elif row.get("diagnosis") and not frappe.db.exists(DX, row.diagnosis):
			found = match(row.diagnosis)
			if found:
				row.diagnosis = found["diagnosis"]
				row.ke_icd11_code = found["code_value"]
			else:
				frappe.throw(
					_(
						"Row {0} of the diagnosis: {1} is not a diagnosis or an ICD-11 title. Choose one from the list."
					).format(row.idx, frappe.bold(row.diagnosis)),
					title=_("Choose the diagnosis"),
				)
		elif row.get("diagnosis") and row.get("ke_icd11_code"):
			# a code chosen for a hospital diagnosis without one: record it there
			cv, _code = icd11_of(row.diagnosis)
			if not cv:
				code = frappe.db.get_value(
					"Code Value", row.ke_icd11_code, ["code_system", "code_value"], as_dict=True
				)
				if code and code.code_system == ICD11:
					dx = frappe.get_doc(DX, row.diagnosis)
					set_coding(dx, ICD11, code.code_value)
					dx.flags.ignore_permissions = True
					dx.save()
		if row.get("diagnosis") and not row.get("ke_icd11_code"):
			row.ke_icd11_code = icd11_of(row.diagnosis)[0]
	_encounter_codes(doc)


def _encounter_codes(doc):
	have = {r.get("code_value") for r in doc.get("codification_table") or []}
	for row in doc.get("diagnosis") or []:
		cv = row.get("ke_icd11_code")
		if not cv or cv in have:
			continue
		have.add(cv)
		code = frappe.db.get_value("Code Value", cv, ["code_value", "display"], as_dict=True)
		if not code:
			continue
		doc.append(
			"codification_table",
			{
				"code_system": ICD11,
				"system": frappe.db.get_value("Code System", ICD11, "uri"),
				"code_value": cv,
				"code": code.code_value,
				"display": code.display,
			},
		)


def code_uncoded_by_title():
	"""Give the hospital's diagnoses without an ICD-11 code the code whose title
	is the same name (case aside): "PNEUMONIA" -> CA40 Pneumonia (v0.58; the
	demo's older diagnoses were made by hand). A name that matches no title, or
	more than one, is left for the doctor to code. Returns the names coded."""
	if not frappe.db.exists("Code System", ICD11):
		return []
	coded = set(
		frappe.get_all("Codification Table", filters={"parenttype": DX, "code_system": ICD11}, pluck="parent")
	)
	done = []
	for name in frappe.get_all(DX, pluck="name"):
		if name in coded:
			continue
		matches = frappe.db.sql(
			"""select code_value, display from `tabCode Value`
			where code_system = %s and lower(display) = lower(%s) limit 2""",
			(ICD11, name.strip()),
			as_dict=True,
		)
		if len(matches) != 1:
			continue
		doc = frappe.get_doc(DX, name)
		set_coding(doc, ICD11, matches[0].code_value, matches[0].display)
		doc.flags.ignore_permissions = True
		doc.save()
		done.append(name)
	return done
