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
