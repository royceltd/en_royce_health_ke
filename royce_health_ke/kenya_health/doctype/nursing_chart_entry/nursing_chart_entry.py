# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

from frappe.model.document import Document

from royce_health_ke import charts


class NursingChartEntry(Document):
	def validate(self):
		charts.validate_entry(self)
