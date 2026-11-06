# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""after_install and after_migrate: converge the site to this app's setup.
Every step is idempotent and never overwrites a hospital's own data (ADR-023).
Downloading code sets (ICD-11) is left to an explicit action - a migrate must
not depend on WHO's servers being reachable."""

from royce_health_ke import codes
from royce_health_ke.setup import custom_fields, marley_fixes


def after_install():
	run()


def after_migrate():
	run()


def run():
	custom_fields.apply()
	marley_fixes.apply()
	codes.ensure_code_systems()
	seed_moh705()


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
