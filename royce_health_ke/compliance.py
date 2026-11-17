# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Each security and privacy safeguard as a live check on this site (the
Compliance Check report). A check returns Pass, Fail or Advice, what this site
has, what is expected, and where to change it. Add a check here when a
safeguard is built, so the report stays the one list an auditor is shown."""

import os

import frappe
from frappe import _
from frappe.utils import add_to_date, cint, now_datetime, nowdate

PASS, FAIL, ADVICE = "Pass", "Fail", "Advice"


def _row(area, safeguard, ok, current, expected, where, advice=False):
	return {
		"area": area,
		"safeguard": safeguard,
		"status": PASS if ok else (ADVICE if advice else FAIL),
		"current": str(current),
		"expected": expected,
		"where": where,
	}


def _system(field):
	return frappe.db.get_single_value("System Settings", field)


def _hours(duration):
	try:
		h, m = (duration or "0:0").split(":")[:2]
		return int(h) + int(m) / 60
	except ValueError:
		return 999


def checks():
	from royce_health_ke.access import TRACKED
	from royce_health_ke.security import idle_lock_minutes

	system = _("Setup > System Settings")
	health = _("Kenya Health Settings")
	rows = []

	# Logins
	attempts = cint(_system("allow_consecutive_login_attempts"))
	rows.append(
		_row(
			_("Logins"),
			_("Account locked after failed logins"),
			0 < attempts <= 5,
			attempts,
			"5 or fewer",
			system,
		)
	)
	locked = cint(_system("allow_login_after_fail"))
	rows.append(
		_row(
			_("Logins"),
			_("Locked account waits before the next try (seconds)"),
			locked >= 300,
			locked,
			"300 or more",
			system,
		)
	)
	policy, score = cint(_system("enable_password_policy")), cint(_system("minimum_password_score"))
	rows.append(
		_row(
			_("Logins"),
			_("Strong passwords required"),
			bool(policy) and score >= 3,
			_("policy on, score {0}").format(score) if policy else _("policy off"),
			"policy on, score 3 or more",
			system,
		)
	)
	expiry = _system("session_expiry") or ""
	rows.append(
		_row(
			_("Logins"),
			_("A login ends after inactivity (hours)"),
			_hours(expiry) <= 12,
			expiry,
			"12:00 or less",
			system,
		)
	)
	rows.append(
		_row(
			_("Logins"),
			_("Two-factor authentication"),
			bool(cint(_system("enable_two_factor_auth"))),
			_("on") if cint(_system("enable_two_factor_auth")) else _("off"),
			"on, at least for managers",
			system,
			advice=True,
		)
	)
	minutes = idle_lock_minutes()
	rows.append(
		_row(
			_("Logins"),
			_("Screen locks when idle (minutes)"),
			0 < minutes <= 15,
			minutes or _("off"),
			"1 to 15",
			health,
		)
	)

	# Users
	expired = frappe.db.count(
		"User",
		{"enabled": 1, "ke_valid_until": ["<", nowdate()], "name": ["not in", ("Administrator", "Guest")]},
	)
	rows.append(
		_row(
			_("Users"),
			_("Accounts past their Valid Until date are disabled"),
			expired == 0,
			expired,
			"0",
			_("User > Valid Until"),
		)
	)
	admins = frappe.get_all(
		"Has Role",
		filters={"role": "System Manager", "parenttype": "User", "parent": ["not in", ("Administrator",)]},
		pluck="parent",
		distinct=True,
	)
	admins = [u for u in admins if frappe.db.get_value("User", u, "enabled")]
	rows.append(
		_row(
			_("Users"),
			_("Few users have full system access (System Manager)"),
			len(admins) <= 3,
			len(admins),
			"3 or fewer",
			_("User > Roles"),
			advice=True,
		)
	)

	# Audit trail
	untracked = [
		d for d in TRACKED if frappe.db.exists("DocType", d) and not frappe.get_meta(d).track_changes
	]
	rows.append(
		_row(
			_("Audit trail"),
			_("Clinical records keep their change history (old and new values)"),
			not untracked,
			", ".join(untracked) or _("all {0}").format(len(TRACKED)),
			"all",
			_("Customize Form > Track Changes"),
		)
	)
	rows.append(
		_row(
			_("Audit trail"),
			_("Opening and printing a patient's record is logged, with the IP address"),
			bool(cint(frappe.db.get_single_value("Kenya Health Settings", "track_record_access"))),
			_("on")
			if cint(frappe.db.get_single_value("Kenya Health Settings", "track_record_access"))
			else _("off"),
			"on",
			health,
		)
	)

	# Access
	from royce_health_ke.role_access import compliance_row

	rows.append(compliance_row(_row))

	# Backups
	rows.append(_backups())
	return rows


def _backups():
	folder = frappe.get_site_path("private", "backups")
	newest = None
	if os.path.isdir(folder):
		times = [
			os.path.getmtime(os.path.join(folder, f))
			for f in os.listdir(folder)
			if f.endswith("-database.sql.gz")
		]
		newest = max(times) if times else None
	from datetime import datetime

	since = add_to_date(now_datetime(), hours=-26)
	ok = bool(newest) and datetime.fromtimestamp(newest) >= since
	return _row(
		_("Backups"),
		_("A database backup in the last day"),
		ok,
		frappe.format(datetime.fromtimestamp(newest), "Datetime") if newest else _("none"),
		_("within 24 hours (and a copy off the server)"),
		_("Scheduler (daily backups) and the server's off-site backup"),
	)
