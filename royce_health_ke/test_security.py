# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Security safeguards (security.py) and the Compliance Check (compliance.py)."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, nowdate
from frappe.utils.password import update_password

from royce_health_ke import compliance, security


class TestSecurity(IntegrationTestCase):
	def setUp(self):
		frappe.flags.ke_test_security = True

	def tearDown(self):
		frappe.flags.ke_test_security = False
		frappe.set_user("Administrator")

	def user(self, **values):
		email = f"sec-{frappe.generate_hash(length=8)}@example.com"
		return frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": "Security", "send_welcome_email": 0, **values}
		).insert(ignore_permissions=True)

	def test_baseline_applies_only_over_frappes_defaults(self):
		frappe.db.set_single_value(
			"System Settings", "allow_consecutive_login_attempts", 10
		)  # Frappe's default
		frappe.db.set_single_value("System Settings", "allow_login_after_fail", 900)  # the hospital's own
		security.apply_baseline()
		self.assertEqual(frappe.db.get_single_value("System Settings", "allow_consecutive_login_attempts"), 5)
		self.assertEqual(frappe.db.get_single_value("System Settings", "allow_login_after_fail"), 900)

	def test_expired_account_is_disabled_and_stays_disabled(self):
		user = self.user(ke_valid_until=add_days(nowdate(), -1))
		security.disable_expired_users()
		user.reload()
		self.assertEqual(user.enabled, 0)
		user.enabled = 1
		with self.assertRaisesRegex(frappe.ValidationError, "valid until"):
			user.save(ignore_permissions=True)
		user.reload()
		user.update({"enabled": 1, "ke_valid_until": add_days(nowdate(), 30)})
		user.save(ignore_permissions=True)
		self.assertEqual(user.enabled, 1)

	def test_a_user_who_worked_is_disabled_not_deleted(self):
		idle = self.user()
		frappe.delete_doc("User", idle.name, ignore_permissions=True)
		self.assertFalse(frappe.db.exists("User", idle.name))

		worker = self.user()
		version = frappe.get_doc(
			{"doctype": "Version", "ref_doctype": "User", "docname": worker.name, "data": "{}"}
		)
		version.db_insert()
		# a change made by the worker (insert records the session user as owner)
		frappe.db.set_value("Version", version.name, "owner", worker.name, update_modified=False)
		with self.assertRaisesRegex(frappe.ValidationError, "Disable"):
			frappe.delete_doc("User", worker.name, ignore_permissions=True)

	def test_unlock_with_own_password_only(self):
		user = self.user()
		update_password(user.name, "Idle-Lock-Test-2026!")
		frappe.set_user(user.name)
		self.assertFalse(security.unlock("wrong password"))
		self.assertTrue(security.unlock("Idle-Lock-Test-2026!"))

	def test_compliance_check_reports_a_weak_setting(self):
		frappe.db.set_single_value("System Settings", "allow_consecutive_login_attempts", 20)
		rows = {r["safeguard"]: r for r in compliance.checks()}
		self.assertEqual(rows["Account locked after failed logins"]["status"], compliance.FAIL)
		frappe.db.set_single_value("System Settings", "allow_consecutive_login_attempts", 5)
		rows = {r["safeguard"]: r for r in compliance.checks()}
		self.assertEqual(rows["Account locked after failed logins"]["status"], compliance.PASS)
		self.assertEqual(
			rows["Clinical records keep their change history (old and new values)"]["status"], compliance.PASS
		)
