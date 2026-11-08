# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

from royce_health_ke import sms


class PatientSMSCampaign(Document):
	def validate(self):
		if self.age_from and self.age_to and self.age_from > self.age_to:
			frappe.throw(frappe._("Age From can't be more than Age To."))
		if self.visited_from and self.visited_to and self.visited_from > self.visited_to:
			frappe.throw(frappe._("Visited From can't be after Visited To."))
		if self.docstatus == 0:
			self.status = "Draft"

	def before_submit(self):
		sms.before_submit_campaign(self)

	def on_submit(self):
		frappe.enqueue(
			"royce_health_ke.sms.send_campaign",
			queue="long",
			enqueue_after_commit=True,
			campaign_name=self.name,
		)
