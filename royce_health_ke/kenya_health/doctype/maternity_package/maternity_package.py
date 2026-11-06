# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

from frappe.model.document import Document

from royce_health_ke import packages


class MaternityPackage(Document):
	def validate(self):
		packages.validate_package(self)
