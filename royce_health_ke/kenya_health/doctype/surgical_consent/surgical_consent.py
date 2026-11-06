# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

from frappe.model.document import Document

from royce_health_ke import theatre


class SurgicalConsent(Document):
	def on_submit(self):
		theatre.link_to_booking(self, "surgical_consent")
