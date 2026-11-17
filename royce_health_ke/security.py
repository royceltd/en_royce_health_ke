# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Security safeguards a hospital needs (DHA certification security tests,
ODPC technical safeguards), on top of Frappe's own:

- Logins: lockout after failed attempts, password strength, session length.
  Frappe has these switches; BASELINE sets them to hospital values once, only
  where a site still has Frappe's default, so a hospital's own choice stands
  (ADR-023).
- Users: an account can carry a "Valid Until" date and is disabled the day
  after; a user who has worked in the system is disabled, never deleted, so
  the audit trail keeps who did what.
- Idle screen lock: after Kenya Health Settings > Idle Screen Lock (minutes)
  without activity, the desk locks behind the user's password; unsaved work
  stays on the page (public/js/desk.js).
- Audit trail: every clinical record keeps its change history (old and new
  values, who, when: Frappe's Version), and every opening or printing of a
  patient's record is logged with the user's IP address (access.py).

The Compliance Check report shows each safeguard as passing or not."""

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import cint, getdate, nowdate

SETTINGS = "Kenya Health Settings"

# System Settings: (field, hospital value, Frappe's default, what it is)
BASELINE = (
	("allow_consecutive_login_attempts", 5, 10, "failed logins before the account is locked"),
	("allow_login_after_fail", 600, 60, "seconds an account stays locked after failed logins"),
	("enable_password_policy", 1, 1, "password strength is checked"),
	("minimum_password_score", "3", "2", "minimum password strength (0-4)"),
	("session_expiry", "12:00", "170:00", "a login ends after this long without activity (hh:mm)"),
)


def apply_baseline():
	"""Hospital values for the login settings still at Frappe's default (after_migrate)."""
	for field, value, frappe_default, _what in BASELINE:
		current = frappe.db.get_single_value("System Settings", field)
		if str(current) in (str(frappe_default), "", "None"):
			frappe.db.set_single_value("System Settings", field, value)


# Users


def disable_expired_users():
	"""Daily: accounts past their Valid Until date are disabled."""
	for user in frappe.get_all(
		"User",
		filters={
			"enabled": 1,
			"ke_valid_until": ["<", nowdate()],
			"name": ["not in", ("Administrator", "Guest")],
		},
		pluck="name",
	):
		frappe.db.set_value("User", user, "enabled", 0)
		frappe.get_doc("User", user).add_comment(
			"Info",
			_("Disabled: the account was valid until {0}.").format(
				frappe.format(frappe.db.get_value("User", user, "ke_valid_until"), "Date")
			),
		)


def user_validate(doc, method=None):
	"""An account past its Valid Until date can't be switched back on without a new date."""
	if doc.get("ke_valid_until") and getdate(doc.ke_valid_until) < getdate(nowdate()) and doc.enabled:
		if not doc.is_new() and doc.has_value_changed("enabled"):
			frappe.throw(
				_("This account was valid until {0}. Set a new Valid Until date to enable it.").format(
					frappe.format(doc.ke_valid_until, "Date")
				)
			)


def has_worked(user):
	"""The user created or changed records: their name is in the audit trail."""
	return bool(
		frappe.db.exists("Version", {"owner": user})
		or frappe.db.exists("Patient Record Access", {"user": user})
	)


def user_on_trash(doc, method=None):
	"""Users who have worked in the system are disabled, not deleted."""
	if frappe.flags.in_test and not frappe.flags.ke_test_security:
		return
	if has_worked(doc.name):
		frappe.throw(
			_(
				"{0} has worked in the system, so the account is kept for the audit trail. Disable it "
				"instead (untick Enabled), or set a Valid Until date."
			).format(doc.full_name or doc.name),
			title=_("Disable, don't delete"),
		)


# Idle screen lock


def idle_lock_minutes():
	return cint(frappe.db.get_single_value(SETTINGS, "idle_lock_minutes"))


def extend_bootinfo(bootinfo):
	try:
		bootinfo.ke_idle_lock_minutes = idle_lock_minutes()
	except Exception:
		bootinfo.ke_idle_lock_minutes = 0


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=10, seconds=60)
def unlock(password: str) -> bool:
	"""The idle screen lock: the user's own password unlocks it."""
	from frappe.utils.password import check_password

	try:
		check_password(frappe.session.user, password)
	except frappe.AuthenticationError:
		frappe.clear_last_message()
		return False
	return True
