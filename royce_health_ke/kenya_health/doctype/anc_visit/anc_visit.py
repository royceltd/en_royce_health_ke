# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

from frappe.model.document import Document

from royce_health_ke import maternity


class ANCVisit(Document):
	def validate(self):
		maternity.validate_anc_visit(self)
