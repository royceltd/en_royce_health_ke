# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class KenyaHealthSettings(Document):
	def validate(self):
		# Our reminder respects SMS consent; Marley's doesn't. Running both would
		# race on the same `reminded` flag, so ours switches Marley's off.
		if self.sms_appointment_reminders and frappe.db.get_single_value(
			"Healthcare Settings", "send_appointment_reminder"
		):
			frappe.db.set_single_value("Healthcare Settings", "send_appointment_reminder", 0)
			frappe.msgprint(
				frappe._("Marley's own appointment reminder (Healthcare Settings) has been switched off."),
				alert=True,
			)
