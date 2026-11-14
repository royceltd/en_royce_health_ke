# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""A discount, waiver or pay-later asked for at the Cashier and decided by a
manager. The rules are in royce_health_ke.approvals."""

from frappe.model.document import Document


class BillApprovalRequest(Document):
	def validate(self):
		from royce_health_ke.approvals import validate_request

		validate_request(self)
