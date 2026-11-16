# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""after_install and after_migrate: converge the site to this app's setup.
Every step is idempotent and never overwrites a hospital's own data (ADR-023).
Downloading code sets (ICD-11) is left to an explicit action - a migrate must
not depend on WHO's servers being reachable."""

from royce_health_ke import clinical, codes, forms, formulary, privacy, roles
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
	seed_notifiable_diseases()
	clinical.ensure_note_types()
	seed_clinical_alerts()
	seed_quality_measures()
	default_settings()
	privacy.apply_defaults()
	roles.apply_defaults()
	formulary.batch_quick_entry()
	forms.apply()


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


def seed_notifiable_diseases():
	"""Create the Disease Surveillance Officer role and the default notifiable
	diseases that don't exist yet; existing rows are the hospital's (ADR-023)."""
	import frappe

	from royce_health_ke.moh.seed_idsr import rows
	from royce_health_ke.privacy import ensure_role
	from royce_health_ke.surveillance import OFFICER_ROLE

	ensure_role(OFFICER_ROLE)
	for disease, category, ihr, alert, days, mapping in rows():
		if frappe.db.exists("Notifiable Disease", disease):
			continue
		frappe.get_doc(
			{
				"doctype": "Notifiable Disease",
				"disease_name": disease,
				"category": category,
				"ihr_notifiable": ihr,
				"alert_threshold": alert,
				"threshold_days": days,
				"codes": [{"code_system": system, "code_prefix": prefix} for system, prefix in mapping],
			}
		).insert(ignore_permissions=True)


def seed_clinical_alerts():
	"""Create the default clinical alert rules that don't exist yet; existing
	rules are the hospital's (ADR-023)."""
	import frappe

	from royce_health_ke.moh.seed_cds import rows

	for row in rows():
		if not frappe.db.exists("Clinical Alert Rule", row["rule_name"]):
			frappe.get_doc({"doctype": "Clinical Alert Rule", **row}).insert(ignore_permissions=True)


def seed_quality_measures():
	"""Create the default quality measures that don't exist yet; existing
	measures and their targets are the hospital's (ADR-023)."""
	import frappe

	from royce_health_ke.moh.seed_quality import MEASURES

	for row in MEASURES:
		if not frappe.db.exists("Quality Measure", row["measure_code"]):
			frappe.get_doc({"doctype": "Quality Measure", **row}).insert(ignore_permissions=True)


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
		("auto_bill_insured", 1),
		("clinical_alerts", 1),
	):
		if not frappe.db.exists("Singles", {"doctype": "Kenya Health Settings", "field": field}):
			frappe.db.set_single_value("Kenya Health Settings", field, value)
