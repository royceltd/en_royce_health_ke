# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Every lab, imaging, procedure and drug order gets its stored payment status
(payment_status.py), worked out by the same rule the worklists used before.
Custom fields are created in after_migrate, which runs after patches, so they
are applied here first."""

from royce_health_ke import payment_status
from royce_health_ke.setup import custom_fields


def execute():
	custom_fields.apply()
	payment_status.backfill()
