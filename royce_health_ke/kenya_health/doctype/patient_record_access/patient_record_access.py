# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class PatientRecordAccess(Document):
	"""An audit entry: written once by royce_health_ke.access, never changed."""

	def validate(self):
		if not self.is_new():
			frappe.throw(_("Record access entries can't be changed."))

	def on_trash(self):
		frappe.throw(_("Record access entries can't be deleted."))
