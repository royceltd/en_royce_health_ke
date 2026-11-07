# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class MOH706Indicator(Document):
	def validate(self):
		if self.kind == "Numeric range" and self.range_high and self.range_high <= (self.range_low or 0):
			frappe.throw(frappe._("'Below' must be more than 'From'."))
