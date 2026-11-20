# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

from frappe.model.document import Document

from royce_health_ke.moh import cold_chain


class FridgeTemperatureReading(Document):
	def validate(self):
		cold_chain.validate_reading(self)
