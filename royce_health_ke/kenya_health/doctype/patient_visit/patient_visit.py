# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

from frappe.model.document import Document

from royce_health_ke import visits


class PatientVisit(Document):
	def validate(self):
		visits.validate_visit(self)

	def before_insert(self):
		visits.before_insert_visit(self)

	def after_insert(self):
		visits.after_insert_visit(self)

	def on_update(self):
		if self.status == "Completed" and self.has_value_changed("status"):
			from royce_health_ke.visit_bill import finalize_insured_bill

			finalize_insured_bill(self)
