# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""v0.44: the role-access matrix (role_access.py). Fresh users, one per
role as staff are given them; any change in what a role may do fails here
until the matrix is changed on purpose."""

import frappe
from frappe.tests import IntegrationTestCase

from royce_health_ke import compliance, role_access, roles


class RoleAccessCase(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		roles.apply_defaults()
		cls.users = {}
		for group, role_names in role_access.ROLE_GROUPS.items():
			missing = [r for r in role_names if not frappe.db.exists("Role", r)]
			if missing:
				continue
			email = f"matrix.{group.lower().replace(' ', '')}@roleaccess.test"
			if not frappe.db.exists("User", email):
				frappe.get_doc(
					{
						"doctype": "User",
						"email": email,
						"first_name": f"Matrix {group}",
						"send_welcome_email": 0,
						"roles": [{"role": r} for r in role_names],
					}
				).insert(ignore_permissions=True)
			cls.users[group] = email

	def tearDown(self):
		frappe.set_user("Administrator")


class TestDocumentAccess(RoleAccessCase):
	def test_each_role_has_exactly_the_matrix(self):
		differences = []
		for doctype in role_access.DOCTYPES:
			if not frappe.db.exists("DocType", doctype):
				continue
			for group, user in self.users.items():
				has = "".join(
					r[0].upper() if frappe.has_permission(doctype, r, user=user) else "-"
					for r in role_access.RIGHTS
				)
				want = role_access.expected(doctype, group)
				if has != want:
					differences.append(f"{group} on {doctype}: {has}, matrix {want}")
		self.assertEqual(differences, [])

	def test_only_reception_and_administrators_edit_registration(self):
		for group, user in self.users.items():
			edits = bool(frappe.has_permission("Patient", "write", user=user))
			self.assertEqual(edits, group in ("Receptionist", "Healthcare Administrator"), group)

	def test_reception_and_cashier_see_no_diagnosis(self):
		for group in ("Receptionist", "Cashier"):
			user = self.users.get(group)
			if not user:
				continue
			for doctype in (
				"Patient Encounter",
				"Lab Test",
				"Observation",
				"Clinical Note",
				"Patient Medical Record",
			):
				self.assertFalse(frappe.has_permission(doctype, "read", user=user), f"{group} {doctype}")

	def test_users_edit_only_their_own_profile(self):
		user = self.users.get("Physician")
		other = self.users.get("Nursing User")
		frappe.set_user(user)
		self.assertTrue(frappe.has_permission("User", "write", doc=frappe.get_doc("User", user)))
		self.assertFalse(frappe.has_permission("User", "write", doc=frappe.get_doc("User", other)))


class TestPagesAndReports(RoleAccessCase):
	def test_pages_and_reports_per_role(self):
		pages = [p for p in {p for v in role_access.PAGES.values() for p in v} if frappe.db.exists("Page", p)]
		reports = frappe.get_all(
			"Report", filters={"module": ["in", ["Kenya Health", "Healthcare"]], "disabled": 0}, pluck="name"
		)
		differences = []
		for group, user in self.users.items():
			frappe.set_user(user)
			opened_pages = {p for p in pages if frappe.get_doc("Page", p).is_permitted()}
			opened_reports = {r for r in reports if frappe.get_doc("Report", r).is_permitted()}
			frappe.set_user("Administrator")
			want_pages = {p for p in role_access.PAGES[group] if p in pages}
			want = role_access.REPORTS[group]
			want_reports = set(reports) if want is None else {r for r in want if r in reports}
			if opened_pages != want_pages:
				differences.append(f"{group} pages: {sorted(opened_pages ^ want_pages)}")
			if opened_reports != want_reports:
				differences.append(f"{group} reports: {sorted(opened_reports ^ want_reports)}")
		self.assertEqual(differences, [])

	def test_no_clinical_report_for_reception_or_cashier(self):
		for group in ("Receptionist", "Cashier"):
			user = self.users.get(group)
			if not user:
				continue
			frappe.set_user(user)
			for report in role_access.CLINICAL_REPORTS:
				if frappe.db.exists("Report", report):
					self.assertFalse(frappe.get_doc("Report", report).is_permitted(), f"{group} {report}")
			frappe.set_user("Administrator")

	def test_compliance_check_only_for_administrators(self):
		for group, user in self.users.items():
			frappe.set_user(user)
			allowed = bool(frappe.get_doc("Report", "Compliance Check").is_permitted())
			frappe.set_user("Administrator")
			self.assertEqual(allowed, group == "Healthcare Administrator", group)


class TestComplianceRow(RoleAccessCase):
	def test_role_rights_agree_with_frappe(self):
		for doctype in ("Patient", "Patient Encounter", "Sales Invoice", "Vital Signs"):
			for group, user in self.users.items():
				by_role = role_access.as_letters(
					role_access.role_rights(doctype, role_access.ROLE_GROUPS[group])
				)
				by_user = "".join(
					r[0].upper() if frappe.has_permission(doctype, r, user=user) else "-"
					for r in role_access.RIGHTS
				)
				self.assertEqual(by_role, by_user, f"{group} {doctype}")

	def test_a_loosened_role_fails_the_check(self):
		def row():
			return next(r for r in compliance.checks() if r["area"] == "Access")

		self.assertEqual(row()["status"], compliance.PASS, row()["current"])
		from frappe.permissions import update_permission_property

		update_permission_property("Patient", "Physician", 0, "write", 1, validate=False)
		frappe.clear_cache(doctype="Patient")
		try:
			failed = row()
			self.assertEqual(failed["status"], compliance.FAIL)
			self.assertIn("Physician", failed["current"])
		finally:
			update_permission_property("Patient", "Physician", 0, "write", 0, validate=False)
			frappe.clear_cache(doctype="Patient")
