# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""after_install and after_migrate: converge the site to this app's setup.
Every step is idempotent and never overwrites a hospital's own data (ADR-023).
Downloading code sets (ICD-11) is left to an explicit action - a migrate must
not depend on WHO's servers being reachable."""

from royce_health_ke import codes, privacy, roles
from royce_health_ke.setup import custom_fields, marley_fixes


def after_install():
	run()
	from royce_health_ke.printing import set_default_print_formats

	# Once, at install: afterwards the default belongs to the client (ADR-023).
	set_default_print_formats()


def after_migrate():
	run()


def run():
	custom_fields.apply()
	marley_fixes.apply()
	codes.ensure_code_systems()
	seed_moh705()
	seed_moh706()
	default_settings()
	privacy.apply_defaults()
	roles.apply_defaults()


def seed_moh705():
	"""Create the default MOH 705 rows that don't exist yet. Existing rows are
	the hospital's to edit and are never touched (ADR-023)."""
	import frappe

	from royce_health_ke.moh.seed705 import rows

	for form, sequence, code, label, kind, mapping in rows():
		if frappe.db.exists("MOH 705 Indicator", f"{form}-{code}"):
			continue
		frappe.get_doc(
			{
				"doctype": "MOH 705 Indicator",
				"form": form,
				"code": code,
				"label": label,
				"kind": kind,
				"sequence": sequence,
				"codes": [{"code_system": system, "code_prefix": prefix} for system, prefix in mapping],
			}
		).insert(ignore_permissions=True)


def seed_moh706():
	"""Create the default MOH 706 rows that don't exist yet; existing rows and
	their lab test mappings are the hospital's (ADR-023)."""
	import frappe

	from royce_health_ke.moh.seed706 import ROWS

	for sequence, (section, code, label, kind, words, low, high, age_group) in enumerate(ROWS, 1):
		if frappe.db.exists("MOH 706 Indicator", code):
			continue
		frappe.get_doc(
			{
				"doctype": "MOH 706 Indicator",
				"code": code,
				"label": label,
				"section": section,
				"sequence": sequence,
				"kind": kind,
				"positive_results": words,
				"range_low": low,
				"range_high": high,
				"age_group": age_group,
			}
		).insert(ignore_permissions=True)


def default_settings():
	"""Defaults for Kenya Health Settings fields added after a site was set up:
	a Single's new field starts empty, not at its default. Only fields never
	saved are set, so a hospital's own choice stands (ADR-023)."""
	import frappe

	for field, value in (
		("track_record_access", 1),
		("require_registration_details", 1),
		("pay_before_lab", 1),
		("pay_before_radiology", 1),
		("pay_before_pharmacy", 1),
	):
		if not frappe.db.exists("Singles", {"doctype": "Kenya Health Settings", "field": field}):
			frappe.db.set_single_value("Kenya Health Settings", field, value)
