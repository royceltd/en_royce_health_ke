# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class PatientConsentLog(Document):
	def validate(self):
		if not self.is_new():
			frappe.throw(_("A consent entry is never changed: record a new one instead."))

	def on_trash(self):
		frappe.throw(_("A consent entry is never deleted."))
