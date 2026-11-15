# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate


class QualityMeasureResult(Document):
	def validate(self):
		if getdate(self.period_end) < getdate(self.period_start):
			frappe.throw(_("Period To is before Period From."))
		if (self.numerator or 0) > (self.denominator or 0) and self.denominator:
			frappe.throw(_("The numerator cannot be more than the denominator."))
		from royce_health_ke.quality import score

		self.rate, self.target_percent, self.met_target = score(
			self.measure, self.numerator, self.denominator
		)
