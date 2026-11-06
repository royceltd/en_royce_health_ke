# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

from frappe.model.document import Document

from royce_health_ke import family_planning


class FamilyPlanningVisit(Document):
	def validate(self):
		family_planning.validate_visit(self)
