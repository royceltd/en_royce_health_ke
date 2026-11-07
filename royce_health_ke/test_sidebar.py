# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

from frappe.tests import UnitTestCase

from royce_health_ke.sidebar import narrow_shared_module_workspaces

ALL = ["Healthcare", "Outpatient", "Diagnostics", "Unlinked"]


def shell(name, module, links):
	return {
		"name": name,
		"module": module,
		"workspaces": list(ALL) if module == "Healthcare" else [name],
		"items": [{"type": "Link", "link_type": "Workspace", "link_to": ws} for ws in links]
		+ [{"type": "Link", "link_type": "DocType", "link_to": "Patient"}],
	}


class TestSidebar(UnitTestCase):
	def test_each_shared_module_sidebar_keeps_its_own_workspaces(self):
		sidebars = {
			"Diagnostics": shell("Diagnostics", "Healthcare", ["Diagnostics"]),
			"Healthcare": shell("Healthcare", "Healthcare", ["Healthcare"]),
			"Outpatient": shell("Outpatient", "Healthcare", ["Outpatient"]),
			"Kenya Health": shell("Kenya Health", "Kenya Health", ["Kenya Health"]),
		}
		narrow_shared_module_workspaces(sidebars)
		# The desk's first match for "Healthcare" is now the Healthcare sidebar, not Diagnostics.
		first = next(s for s in sidebars.values() if "Healthcare" in s["workspaces"])
		self.assertEqual(first["name"], "Healthcare")
		self.assertEqual(sidebars["Diagnostics"]["workspaces"], ["Diagnostics", "Unlinked"])
		self.assertEqual(sidebars["Outpatient"]["workspaces"], ["Outpatient", "Unlinked"])
		self.assertEqual(sidebars["Kenya Health"]["workspaces"], ["Kenya Health"])

	def test_single_sidebar_modules_and_empty_payload_untouched(self):
		self.assertEqual(narrow_shared_module_workspaces({}), {})
		self.assertIsNone(narrow_shared_module_workspaces(None))
		lone = {"Stock": {"name": "Stock", "module": "Stock", "workspaces": ["Stock", "Other"], "items": []}}
		narrow_shared_module_workspaces(lone)
		self.assertEqual(lone["Stock"]["workspaces"], ["Stock", "Other"])
