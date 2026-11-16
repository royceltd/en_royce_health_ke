# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Height is now taken in centimetres and Patient shows one contact number
(Mobile): fill Height (cm) on vital signs recorded in metres, and copy a
patient's Phone to Mobile where Mobile is empty, before Phone is hidden.
Custom fields are created in after_migrate, which runs after patches, so
they are applied here first."""

import frappe

from royce_health_ke.setup import custom_fields


def execute():
	custom_fields.apply()
	frappe.db.sql(
		"""update `tabVital Signs` set ke_height_cm = round(height * 100, 1)
		where ifnull(height, 0) > 0 and ifnull(ke_height_cm, 0) = 0"""
	)
	frappe.db.sql(
		"""update `tabPatient` set mobile = phone
		where ifnull(mobile, '') = '' and ifnull(phone, '') != ''"""
	)
