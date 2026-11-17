# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Where royce_health_ke meets Marley Health (the `healthcare` app) beyond its
doctypes: the Marley version we support, and the Marley rule we replace.

Supported version: SUPPORTED, pinned in the hospital release file
(deploy/apps.health.json: the image build and CI use it) and on developers'
benches. test_marley checks it and the Marley functions we rely on, so a
Marley upgrade is a planned change: move SUPPORTED and the release file
together, run the tests, read what failed.

Replaced rule: the outpatient consultation fee (fees.py). Marley's invoice
helpers (Get Items From > Healthcare Services and the visit bill) price a
consultation with `healthcare.healthcare.utils.get_appointment_billing_item_and_rate`.
It is replaced for good, in every process, before each request and background
job (hooks: before_request, before_job) and on import of this module. It used
to be swapped in and out around each call, which leaked between requests
served at the same time by one worker's threads. Inpatient charges still go to
Marley's own rule (`original_billing_item_and_rate`)."""

from healthcare.healthcare import utils as _utils

SUPPORTED = "16.8.0"

# Marley's own rule, kept before it is replaced (a reload of this module must
# not mistake our rule for Marley's).
_ORIGINAL = getattr(_utils, "_ke_original_billing_rule", None) or _utils.get_appointment_billing_item_and_rate
_utils._ke_original_billing_rule = _ORIGINAL


def original_billing_item_and_rate(doc):
	"""Marley's consultation rule, unchanged."""
	return _ORIGINAL(doc)


def install(*args, **kwargs):
	"""Marley's invoice helpers use our consultation fee rule. Idempotent and
	cheap: an attribute check per request."""
	from royce_health_ke.fees import billing_item_and_rate

	if _utils.get_appointment_billing_item_and_rate is not billing_item_and_rate:
		_utils.get_appointment_billing_item_and_rate = billing_item_and_rate


def installed_version():
	import healthcare

	return healthcare.__version__


install()
