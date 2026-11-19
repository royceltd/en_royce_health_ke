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

# Marley functions we call with positional arguments: their first parameters.
SIGNATURES = {
	"get_healthcare_services_to_invoice": ["patient", "customer", "company", "link_customer"],
	"get_drugs_to_invoice": ["encounter", "customer"],
	"get_appointment_type_billing_details": ["appointment_type", "dep_su", "is_inpatient"],
	"make_lab_test": ["service_request"],
	"create_inpatient_record": ["admission_order"],
	"get_intake_output_summary": ["patient", "hours"],
	"make_discharge_summary": ["source_name"],
	"get_medical_codes": ["template_dt", "template_dn", "code_standard"],
}


class TestMarleyContract(IntegrationTestCase):
	def test_supported_version(self):
		self.assertEqual(
			marley.installed_version(),
			marley.SUPPORTED,
			"Marley version changed: run the tests, fix what they show, then move marley.SUPPORTED "
			"and deploy/apps.health.json together.",
		)

	def test_everything_we_use_exists(self):
		missing = []
		for name, (module, attr) in marley.USES.items():
			try:
				getattr(marley, name)
			except ImportError, AttributeError:
				missing.append(f"{name}: healthcare.healthcare.{module}.{attr}")
		self.assertEqual(missing, [])

	def test_marley_only_through_the_adapter(self):
		"""No module but marley.py imports from Marley (`healthcare`)."""
		offenders = []
		for path in APP.rglob("*.py"):
			if path.name in ("marley.py", "test_marley.py"):
				continue
			for node in ast.walk(ast.parse(path.read_text())):
				module = (
					node.module
					if isinstance(node, ast.ImportFrom)
					else node.names[0].name
					if isinstance(node, ast.Import)
					else None
				)
				if module and (module == "healthcare" or module.startswith("healthcare.")):
					offenders.append(f"{path.relative_to(APP)}:{node.lineno}")
		self.assertEqual(offenders, [], "import Marley functions from royce_health_ke.marley (USES)")

	def test_signatures_we_call(self):
		for name, params in SIGNATURES.items():
			fn = inspect.unwrap(getattr(marley, name))
			actual = list(inspect.signature(fn).parameters)[: len(params)]
			self.assertEqual(actual, params, name)
		original = list(inspect.signature(inspect.unwrap(marley._ORIGINAL)).parameters)
		self.assertEqual(original[:1], ["doc"], "get_appointment_billing_item_and_rate")
