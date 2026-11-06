# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

import frappe


def installed(app: str) -> bool:
	return app in frappe.get_installed_apps()
