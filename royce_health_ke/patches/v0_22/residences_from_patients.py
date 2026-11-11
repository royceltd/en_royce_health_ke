# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""v0.22 makes the patient's residence a pick list (Residence). Each place
already typed on a patient becomes a Residence, with the county and
sub-county most of its patients have, so the field keeps its value. Places
typed slightly differently ("Lanet" / "lanet ") are merged; spelling
variants are left for the hospital to merge (rename one onto the other).

Frappe refuses to turn a Data custom field into a Link, so the field's type
is set here directly (both are the same varchar column); after_migrate then
applies the rest of its definition."""

from collections import Counter

import frappe


def execute():
	frappe.reload_doc("kenya_health", "doctype", "residence")
	rows = frappe.db.sql(
		"""select name, ke_residence, ke_county, ke_sub_county from `tabPatient`
		where ifnull(ke_residence, '') != ''""",
		as_dict=True,
	)
	places = {}
	for r in rows:
		clean = " ".join(r.ke_residence.split())
		key = clean.lower()
		place = places.setdefault(key, {"name": clean, "county": Counter(), "sub": Counter(), "patients": []})
		place["patients"].append(r)
		if r.ke_county:
			place["county"][r.ke_county] += 1
		if r.ke_sub_county:
			place["sub"][r.ke_sub_county.strip()] += 1

	for place in places.values():
		name = frappe.db.get_value("Residence", {"residence_name": place["name"]}) or place["name"]
		if not frappe.db.exists("Residence", name):
			frappe.get_doc(
				{
					"doctype": "Residence",
					"residence_name": name,
					"county": place["county"].most_common(1)[0][0] if place["county"] else None,
					"sub_county": place["sub"].most_common(1)[0][0] if place["sub"] else None,
				}
			).insert(ignore_permissions=True)
		for r in place["patients"]:
			if r.ke_residence != name:
				frappe.db.set_value("Patient", r.name, "ke_residence", name, update_modified=False)

	field = frappe.db.get_value("Custom Field", {"dt": "Patient", "fieldname": "ke_residence"})
	if field:
		frappe.db.set_value("Custom Field", field, {"fieldtype": "Link", "options": "Residence"})
		frappe.clear_cache(doctype="Patient")
