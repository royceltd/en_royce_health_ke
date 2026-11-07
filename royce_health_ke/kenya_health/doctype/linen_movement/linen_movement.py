# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

from frappe.model.document import Document

from royce_health_ke import laundry


class LinenMovement(Document):
	def validate(self):
		laundry.validate_movement(self)

	def on_submit(self):
		laundry.on_submit_movement(self)

	def on_cancel(self):
		laundry.on_cancel_movement(self)
