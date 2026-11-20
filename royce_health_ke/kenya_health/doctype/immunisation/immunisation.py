# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

from frappe.model.document import Document

from royce_health_ke import immunisation


class Immunisation(Document):
	def validate(self):
		immunisation.validate_dose_given(self)
