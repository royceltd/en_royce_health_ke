# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

from frappe.model.document import Document

from royce_health_ke import maternity


class DeliveryRecord(Document):
	def validate(self):
		maternity.validate_delivery(self)

	def on_submit(self):
		maternity.on_submit_delivery(self)

	def on_cancel(self):
		maternity.on_cancel_delivery(self)
