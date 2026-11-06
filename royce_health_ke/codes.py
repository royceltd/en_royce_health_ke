# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Clinical code sets in Marley's Code System / Code Value doctypes (FHIR
shaped: system URI + code + display, which is what the Health Information
Exchange expects on claims and records).

- ICD-11 MMS: downloaded from WHO at setup (CC BY-ND 3.0 IGO - used as
  published, with attribution, never redistributed in this repository).
- ICD-10, LOINC, PPB product codes: imported from files the hospital obtains
  under each publisher's own terms (LOINC needs a free loinc.org account)."""

import csv
import io
import zipfile

import frappe
import requests
from frappe import _
from frappe.utils import now

ICD11 = "ICD-11"
ICD10 = "ICD-10"
LOINC = "LOINC"
PPB = "PPB Product Code"

CODE_SYSTEMS = {
	ICD11: {
		"uri": "http://id.who.int/icd/release/11/mms",
		"description": "WHO ICD-11 for Mortality and Morbidity Statistics (MMS). "
		"Source: World Health Organization, icd.who.int, licensed CC BY-ND 3.0 IGO.",
	},
	ICD10: {
		"uri": "http://hl7.org/fhir/sid/icd-10",
		"description": "WHO ICD-10. Kenya's MOH reports and many claims still use ICD-10.",
	},
	LOINC: {
		"uri": "http://loinc.org",
		"description": "LOINC laboratory and clinical observation codes (loinc.org). "
		"This material contains content from LOINC, copyright Regenstrief Institute, Inc.",
	},
	PPB: {
		# Placeholder until the HIE documentation gives the official system URI.
		"uri": "urn:ke:ppb:product",
		"description": "Pharmacy and Poisons Board product registration codes. Custom system: "
		"replace the URI with the one the HIE specifies.",
		"custom": 1,
	},
}

ICD11_RELEASE = "2026-01"
ICD11_URL = "https://icdcdn.who.int/static/releasefiles/{release}/SimpleTabulation-ICD-11-MMS-en.zip"


def ensure_code_systems():
	for name, spec in CODE_SYSTEMS.items():
		if not frappe.db.exists("Code System", name):
			frappe.get_doc(
				{
					"doctype": "Code System",
					"code_system": name,
					"uri": spec["uri"],
					"description": spec["description"],
					"custom": spec.get("custom", 0),
				}
			).insert(ignore_permissions=True)


def code_value_name(code_system, code):
	"""Marley's Code Value autoname without a version: '<code>-<system>'."""
	return f"{code}-{code_system}"


def upsert_codes(code_system, rows):
	"""Insert the (code, display, url, level) rows not yet present, and update
	changed displays. Bulk, so a 35,000-code release loads in seconds.
	Returns {"created": n, "updated": n}."""
	ensure_code_systems()
	uri = frappe.db.get_value("Code System", code_system, "uri")
	existing = dict(
		frappe.get_all(
			"Code Value", filters={"code_system": code_system}, fields=["code_value", "display"], as_list=True
		)
	)
	created, updated, values, stamp = 0, 0, [], now()
	user = frappe.session.user
	for code, display, url, level in rows:
		display = (display or "")[:140]
		if code in existing:
			if existing[code] != display:
				frappe.db.set_value(
					"Code Value",
					code_value_name(code_system, code),
					"display",
					display,
					update_modified=False,
				)
				updated += 1
			continue
		existing[code] = display
		values.append(
			(
				code_value_name(code_system, code),
				stamp,
				stamp,
				user,
				user,
				0,
				0,
				code_system,
				code,
				display,
				display,
				uri,
				url or None,
				level or 0,
			)
		)
		created += 1
	if values:
		frappe.db.bulk_insert(
			"Code Value",
			[
				"name",
				"creation",
				"modified",
				"owner",
				"modified_by",
				"docstatus",
				"idx",
				"code_system",
				"code_value",
				"display",
				"definition",
				"system_uri",
				"official_url",
				"level",
			],
			values,
			ignore_duplicates=True,
			chunk_size=5000,
		)
	return {"created": created, "updated": updated}


def parse_icd11_tabulation(text):
	"""(code, title, linearization URI, depth) for every coded category in WHO's
	SimpleTabulation file. Chapters and blocks carry no code and are skipped;
	titles lose the '- - ' depth markers."""
	for row in csv.DictReader(io.StringIO(text), delimiter="\t"):
		code = (row.get("Code") or "").strip()
		if not code:
			continue
		title = (row.get("Title") or "").lstrip("- ").strip()
		depth = int(row.get("DepthInKind") or 0)
		yield code, title, row.get("Linearization URI"), depth


@frappe.whitelist()
def sync_icd11(release: str = ICD11_RELEASE):
	"""Download WHO's ICD-11 MMS release and load it. Run from the Code System
	form or `bench --site <site> execute royce_health_ke.codes.sync_icd11`."""
	frappe.only_for(("System Manager", "Healthcare Administrator"))
	response = requests.get(ICD11_URL.format(release=release), timeout=120)
	response.raise_for_status()
	with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
		name = next(n for n in archive.namelist() if n.endswith(".txt") and "SimpleTabulation" in n)
		text = archive.read(name).decode("utf-8-sig")
	result = upsert_codes(ICD11, parse_icd11_tabulation(text))
	frappe.db.set_value(
		"Code System", ICD11, "description", CODE_SYSTEMS[ICD11]["description"] + f" Release {release}."
	)
	frappe.db.commit()
	return result


@frappe.whitelist()
def import_csv(code_system: str, file_url: str, code_column: str = "code", display_column: str = "display"):
	"""Load codes from an uploaded CSV (File URL). For LOINC's LoincTableCore.csv
	use code_column="LOINC_NUM", display_column="LONG_COMMON_NAME"."""
	frappe.only_for(("System Manager", "Healthcare Administrator"))
	if code_system not in CODE_SYSTEMS:
		frappe.throw(_("Unknown code system {0}.").format(code_system))
	content = frappe.get_doc("File", {"file_url": file_url}).get_content()
	if isinstance(content, bytes):
		content = content.decode("utf-8-sig")
	reader = csv.DictReader(io.StringIO(content))
	missing = {code_column, display_column} - set(reader.fieldnames or ())
	if missing:
		frappe.throw(_("The file has no column(s) {0}.").format(", ".join(sorted(missing))))
	rows = (
		(r[code_column].strip(), r[display_column].strip(), None, 0) for r in reader if r[code_column].strip()
	)
	result = upsert_codes(code_system, rows)
	frappe.db.commit()
	return result


def set_coding(doc, code_system, code, display=None):
	"""Attach `code` from `code_system` to a Marley document's codification
	table (Diagnosis, Lab Test Template, Medication, ...), creating the Code
	Value if it isn't loaded yet. One code per system: replaces an earlier one."""
	ensure_code_systems()
	name = code_value_name(code_system, code)
	if not frappe.db.exists("Code Value", name):
		upsert_codes(code_system, [(code, display or code, None, 0)])
	display = frappe.db.get_value("Code Value", name, "display")
	doc.set(
		"codification_table", [r for r in doc.get("codification_table") or [] if r.code_system != code_system]
	)
	doc.append(
		"codification_table",
		{
			"code_system": code_system,
			"system": frappe.db.get_value("Code System", code_system, "uri"),
			"code_value": name,
			"code": code,
			"display": display,
		},
	)
