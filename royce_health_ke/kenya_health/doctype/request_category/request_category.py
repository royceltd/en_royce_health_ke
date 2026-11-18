# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class RequestCategory(Document):
	def validate(self):
		from royce_health_ke.flow import STATIONS

		if self.service_point not in STATIONS:
			frappe.throw(_("Unknown service point {0}.").format(self.service_point))
		from royce_health_ke import routing

		routing.clear_cache()

	def on_trash(self):
		from royce_health_ke import routing

		routing.clear_cache()
