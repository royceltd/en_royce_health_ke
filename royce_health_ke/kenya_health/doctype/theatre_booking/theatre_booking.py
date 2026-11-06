# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

from frappe.model.document import Document

from royce_health_ke import theatre


class TheatreBooking(Document):
	def validate(self):
		theatre.validate_booking(self)
