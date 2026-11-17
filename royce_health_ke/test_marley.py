# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""What we rely on in Marley Health, checked: a Marley upgrade that removes or
changes one of these fails here, not in a hospital (marley.py)."""

import ast
import importlib
import inspect
from pathlib import Path

from frappe.tests import IntegrationTestCase

from royce_health_ke import marley

APP = Path(__file__).parent


def marley_imports():
	"""{(module, name): [our files]} for every `from healthcare... import name`
	in the app's code (tests left out)."""
	found = {}
	for path in APP.rglob("*.py"):
		if path.name.startswith("test_"):
			continue
		for node in ast.walk(ast.parse(path.read_text())):
			if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("healthcare"):
				for alias in node.names:
					found.setdefault((node.module, alias.name), []).append(str(path.relative_to(APP)))
	return found


# Marley functions we call with positional arguments: their first parameters.
SIGNATURES = {
	("healthcare.healthcare.utils", "get_healthcare_services_to_invoice"): [
		"patient",
		"customer",
		"company",
		"link_customer",
	],
	("healthcare.healthcare.utils", "get_drugs_to_invoice"): ["encounter", "customer"],
	("healthcare.healthcare.utils", "get_appointment_type_billing_details"): [
		"appointment_type",
		"dep_su",
		"is_inpatient",
	],
	("healthcare.healthcare.utils", "get_appointment_billing_item_and_rate"): ["doc"],
}


class TestMarleyContract(IntegrationTestCase):
	def test_supported_version(self):
		self.assertEqual(
			marley.installed_version(),
			marley.SUPPORTED,
			"Marley version changed: run the tests, fix what they show, then move marley.SUPPORTED "
			"and deploy/apps.health.json together.",
		)

	def test_everything_we_import_exists(self):
		imports = marley_imports()
		self.assertTrue(imports)
		missing = []
		for (module, name), files in imports.items():
			try:
				mod = importlib.import_module(module)
			except ImportError:
				missing.append(f"{module} (used in {', '.join(files)})")
				continue
			if not hasattr(mod, name):
				try:
					importlib.import_module(f"{module}.{name}")
				except ImportError:
					missing.append(f"{module}.{name} (used in {', '.join(files)})")
		self.assertEqual(missing, [])

	def test_signatures_we_call(self):
		for (module, name), params in SIGNATURES.items():
			fn = getattr(importlib.import_module(module), name)
			if name == "get_appointment_billing_item_and_rate":
				fn = marley._ORIGINAL  # ours replaces it
			fn = inspect.unwrap(fn)
			actual = list(inspect.signature(fn).parameters)[: len(params)]
			self.assertEqual(actual, params, f"{module}.{name}")
