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

import importlib

from healthcare.healthcare import utils as _utils

SUPPORTED = "16.8.0"

# Every Marley function or class royce_health_ke uses, by the name we use
# (no other module imports from `healthcare`; test_marley checks both). Loaded
# when first used: `from royce_health_ke.marley import make_lab_test`.
USES = {
	# billing
	"get_healthcare_services_to_invoice": ("utils", "get_healthcare_services_to_invoice"),
	"get_drugs_to_invoice": ("utils", "get_drugs_to_invoice"),
	"get_appointment_type_billing_details": ("utils", "get_appointment_type_billing_details"),
	# insurance
	"make_insurance_coverage": (
		"doctype.patient_insurance_coverage.patient_insurance_coverage",
		"make_insurance_coverage",
	),
	"get_item_price_list_rate": (
		"doctype.patient_insurance_coverage.patient_insurance_coverage",
		"get_item_price_list_rate",
	),
	"CoverageNotFoundError": (
		"doctype.patient_insurance_coverage.patient_insurance_coverage",
		"CoverageNotFoundError",
	),
	"get_insurance_price_lists": (
		"doctype.patient_insurance_policy.patient_insurance_policy",
		"get_insurance_price_lists",
	),
	"create_claim_payment_entry": ("doctype.insurance_claim.insurance_claim", "create_payment_entry"),
	# orders and results
	"make_lab_test": ("doctype.service_request.service_request", "make_lab_test"),
	"make_observation": ("doctype.service_request.service_request", "make_observation"),
	"get_observation_details": ("doctype.observation.observation", "get_observation_details"),
	"get_procedure_consumables": (
		"doctype.clinical_procedure.clinical_procedure",
		"get_procedure_consumables",
	),
	# medicines
	"insert_item": ("doctype.medication.medication", "insert_item"),
	"make_item_price": ("doctype.medication.medication", "make_item_price"),
	# inpatients
	"schedule_inpatient": ("doctype.inpatient_record.inpatient_record", "schedule_inpatient"),
	"schedule_discharge": ("doctype.inpatient_record.inpatient_record", "schedule_discharge"),
	"make_discharge_summary": ("doctype.inpatient_record.inpatient_record", "make_discharge_summary"),
	"create_inpatient_record": ("doctype.inpatient_record.inpatient_record", "create_inpatient_record"),
	# ward medication and nursing (inpatient.py, charts.py)
	"manages_medication_stock": (
		"doctype.healthcare_service_unit.healthcare_service_unit",
		"manages_medication_stock",
	),
	"get_intake_output_summary": ("api.intake_output", "get_intake_output_summary"),
	"get_medical_codes": ("utils", "get_medical_codes"),
}


def __getattr__(name):
	if name in USES:
		module, attr = USES[name]
		return getattr(importlib.import_module(f"healthcare.healthcare.{module}"), attr)
	raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


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
