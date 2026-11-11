# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

from frappe.model.document import Document

from royce_health_ke import postop, theatre


class TreatmentSheet(Document):
	def validate(self):
		postop.validate(self)

	def after_insert(self):
		if self.theatre_booking:
			theatre.link_to_booking(self, "treatment_sheet")

	def before_submit(self):
		postop.before_submit(self)

	def on_submit(self):
		postop.on_submit(self)

	def on_cancel(self):
		postop.on_cancel(self)
