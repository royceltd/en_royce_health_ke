# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class HealthFacility(Document):
	def validate(self):
		self.kmhfl_code = (self.kmhfl_code or "").strip() or None
		if self.kmhfl_code and not self.kmhfl_code.isdigit():
			frappe.throw(_("KMHFL Code must be numeric, as on the Master Facility List."))
		if self.branch and frappe.db.exists(
			"Health Facility", {"branch": self.branch, "name": ["!=", self.name]}
		):
			frappe.throw(_("Branch {0} already belongs to another facility.").format(self.branch))
