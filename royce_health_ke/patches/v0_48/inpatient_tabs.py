# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""The patient screen's default tabs grew (Bethesda's ward screen): TB
Screening, Doctor Notes, Doctor Instructions, Consent and Disposition. A site
still on v0.47's default tab bar gets the new one; a hospital's own is kept."""

import frappe

from royce_health_ke.inpatient import DEFAULT_PROFILE, PANELS, PANELS_V1


def execute():
	if not frappe.db.exists("Patient Workspace Profile", DEFAULT_PROFILE):
		return
	profile = frappe.get_doc("Patient Workspace Profile", DEFAULT_PROFILE)
	current = tuple(t.panel for t in profile.tabs)
	untouched = current == PANELS_V1 and all(
		(t.label or t.panel) == t.panel and not t.hidden for t in profile.tabs
	)
	if not untouched:
		return
	profile.set("tabs", [{"panel": p, "label": p} for p in PANELS])
	profile.flags.ignore_permissions = True
	profile.save()
