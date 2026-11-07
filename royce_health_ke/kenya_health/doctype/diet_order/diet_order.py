# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

from frappe.model.document import Document

from royce_health_ke import kitchen


class DietOrder(Document):
	def validate(self):
		kitchen.validate_diet_order(self)

	def on_submit(self):
		kitchen.on_submit_diet_order(self)
