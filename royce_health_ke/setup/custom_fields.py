# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Kenyan fields on Marley doctypes. Created in code (not fixtures) so every
install and migrate converges to this definition; all fieldnames start with
`ke_` so they never collide with Marley's own."""

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from royce_health_ke.kenya import (
	CADRES,
	COUNTIES,
	ID_TYPES,
	NEXT_OF_KIN_RELATIONSHIPS,
	REGULATORS,
	select,
)
from royce_health_ke.moh.moh717 import CLINICS as MOH717_CLINICS
from royce_health_ke.moh.moh717 import OUTCOMES as MOH717_OUTCOMES
from royce_health_ke.moh.moh717 import WARDS as MOH717_WARDS

MODULE = "Kenya Health"

PATIENT = [
	{
		"fieldname": "ke_identification_section",
		"fieldtype": "Section Break",
		"label": "Kenyan Identification",
		"insert_after": "phone",
		"collapsible": 0,
	},
	{
		"fieldname": "ke_id_type",
		"fieldtype": "Select",
		"label": "ID Type",
		"options": select(ID_TYPES),
		"insert_after": "ke_identification_section",
	},
	{
		"fieldname": "ke_id_number",
		"fieldtype": "Data",
		"label": "ID Number",
		"insert_after": "ke_id_type",
		"depends_on": "eval:doc.ke_id_type && doc.ke_id_type != 'None'",
		"mandatory_depends_on": "eval:doc.ke_id_type && doc.ke_id_type != 'None'",
		"description": "Copied to Marley's Identification Number (UID), which must be unique.",
		"in_standard_filter": 1,
	},
	{
		"fieldname": "ke_sha_number",
		"fieldtype": "Data",
		"label": "SHA Member Number",
		"insert_after": "ke_id_number",
		"in_standard_filter": 1,
	},
	{"fieldname": "ke_identification_cb", "fieldtype": "Column Break", "insert_after": "ke_sha_number"},
	{
		"fieldname": "ke_cr_id",
		"fieldtype": "Data",
		"label": "Client Registry ID",
		"insert_after": "ke_identification_cb",
		"read_only": 1,
		"description": "National Client Registry ID, filled from the Health Information Exchange.",
	},
	{
		"fieldname": "ke_county",
		"fieldtype": "Select",
		"label": "County of Residence",
		"options": select(COUNTIES),
		"insert_after": "ke_cr_id",
	},
	{"fieldname": "ke_sub_county", "fieldtype": "Data", "label": "Sub-County", "insert_after": "ke_county"},
	{
		"fieldname": "ke_next_of_kin_section",
		"fieldtype": "Section Break",
		"label": "Next of Kin",
		"insert_after": "ke_sub_county",
	},
	{
		"fieldname": "ke_nok_name",
		"fieldtype": "Data",
		"label": "Next of Kin Name",
		"insert_after": "ke_next_of_kin_section",
	},
	{
		"fieldname": "ke_nok_relationship",
		"fieldtype": "Select",
		"label": "Relationship",
		"options": select(NEXT_OF_KIN_RELATIONSHIPS),
		"insert_after": "ke_nok_name",
	},
	{"fieldname": "ke_nok_cb", "fieldtype": "Column Break", "insert_after": "ke_nok_relationship"},
	{
		"fieldname": "ke_nok_phone",
		"fieldtype": "Data",
		"label": "Next of Kin Phone",
		"options": "Phone",
		"insert_after": "ke_nok_cb",
	},
]

PRACTITIONER = [
	{
		"fieldname": "ke_registration_section",
		"fieldtype": "Section Break",
		"label": "Professional Registration",
		"insert_after": "office_phone",
	},
	{
		"fieldname": "ke_cadre",
		"fieldtype": "Select",
		"label": "Cadre",
		"options": select(CADRES),
		"insert_after": "ke_registration_section",
	},
	{
		"fieldname": "ke_regulator",
		"fieldtype": "Select",
		"label": "Regulator",
		"options": select(REGULATORS),
		"insert_after": "ke_cadre",
	},
	{
		"fieldname": "ke_registration_number",
		"fieldtype": "Data",
		"label": "Registration Number",
		"insert_after": "ke_regulator",
	},
	{
		"fieldname": "ke_registration_cb",
		"fieldtype": "Column Break",
		"insert_after": "ke_registration_number",
	},
	{
		"fieldname": "ke_licence_number",
		"fieldtype": "Data",
		"label": "Practising Licence Number",
		"insert_after": "ke_registration_cb",
	},
	{
		"fieldname": "ke_licence_expiry",
		"fieldtype": "Date",
		"label": "Licence Expiry",
		"insert_after": "ke_licence_number",
		"mandatory_depends_on": "eval:doc.ke_licence_number",
		"in_list_view": 1,
	},
	{
		"fieldname": "ke_hwr_id",
		"fieldtype": "Data",
		"label": "Health Worker Registry ID",
		"insert_after": "ke_licence_expiry",
		"read_only": 1,
		"description": "Filled from the national Health Worker Registry through the Health Information Exchange.",
	},
]


CLAIM_COVERAGE = [
	{
		"fieldname": "ke_rejection_settlement",
		"fieldtype": "Select",
		"label": "Rejection Settled By",
		"options": "\nBill Patient\nWrite Off",
		"insert_after": "payment_error_reason",
		"read_only": 1,
		"allow_on_submit": 1,
		"in_list_view": 1,
	},
	{
		"fieldname": "ke_settlement_entry",
		"fieldtype": "Link",
		"label": "Settlement Entry",
		"options": "Journal Entry",
		"insert_after": "ke_rejection_settlement",
		"read_only": 1,
		"allow_on_submit": 1,
	},
]


MOH = {
	"Medical Department": [
		{
			"fieldname": "ke_moh717_clinic",
			"fieldtype": "Select",
			"label": "MOH 717 Clinic",
			"options": select(MOH717_CLINICS),
			"insert_after": "department",
			"description": "Where this department's outpatient visits count on MOH 717. Blank = General Outpatient.",
		}
	],
	"Healthcare Service Unit Type": [
		{
			"fieldname": "ke_moh717_ward",
			"fieldtype": "Select",
			"label": "MOH 717 Ward",
			"options": select(MOH717_WARDS),
			"insert_after": "inpatient_occupancy",
			"depends_on": "inpatient_occupancy",
			"description": "Ward category for MOH 717 admissions and discharges. Blank = Other Wards.",
		}
	],
	"Inpatient Record": [
		{
			"fieldname": "ke_discharge_outcome",
			"fieldtype": "Select",
			"label": "Discharge Outcome",
			"options": select(MOH717_OUTCOMES),
			"insert_after": "discharge_datetime",
			"description": "Counts on MOH 717 as a discharge, death, abscondee or referral out. Blank = Discharged.",
		}
	],
	"Patient Encounter": [
		{
			"fieldname": "ke_referred_out",
			"fieldtype": "Check",
			"label": "Referred to Another Facility",
			"insert_after": "source",
			"allow_on_submit": 1,
		},
		{
			"fieldname": "ke_referred_to",
			"fieldtype": "Data",
			"label": "Referred To",
			"insert_after": "ke_referred_out",
			"depends_on": "ke_referred_out",
			"allow_on_submit": 1,
		},
	],
}


OPERATION_NOTE = [
	{
		"fieldname": "ke_theatre_booking",
		"fieldtype": "Link",
		"label": "Theatre Booking",
		"options": "Theatre Booking",
		"insert_after": "service_request",
		"read_only": 1,
	},
	{
		"fieldname": "ke_operation_note_section",
		"fieldtype": "Section Break",
		"label": "Operation Note",
		"insert_after": "notes",
	},
	{
		"fieldname": "ke_indication",
		"fieldtype": "Small Text",
		"label": "Indication",
		"insert_after": "ke_operation_note_section",
	},
	{
		"fieldname": "ke_findings",
		"fieldtype": "Small Text",
		"label": "Findings",
		"insert_after": "ke_indication",
	},
	{
		"fieldname": "ke_procedure_details",
		"fieldtype": "Text Editor",
		"label": "Procedure Details",
		"insert_after": "ke_findings",
		"description": "Incision, steps, closure. Required to complete a theatre booking.",
	},
	{
		"fieldname": "ke_operation_note_cb",
		"fieldtype": "Column Break",
		"insert_after": "ke_procedure_details",
	},
	{
		"fieldname": "ke_estimated_blood_loss_ml",
		"fieldtype": "Int",
		"label": "Estimated Blood Loss (ml)",
		"insert_after": "ke_operation_note_cb",
	},
	{
		"fieldname": "ke_specimens",
		"fieldtype": "Small Text",
		"label": "Specimens Sent",
		"insert_after": "ke_estimated_blood_loss_ml",
	},
	{
		"fieldname": "ke_implants",
		"fieldtype": "Small Text",
		"label": "Implants / Drains",
		"insert_after": "ke_specimens",
	},
	{
		"fieldname": "ke_intraop_complications",
		"fieldtype": "Small Text",
		"label": "Complications",
		"insert_after": "ke_implants",
	},
	{
		"fieldname": "ke_post_op_instructions",
		"fieldtype": "Small Text",
		"label": "Post-operative Instructions",
		"insert_after": "ke_intraop_complications",
	},
]
for _field in OPERATION_NOTE:
	_field["allow_on_submit"] = 1  # the procedure is submitted when theatre starts


def apply():
	for fields in (PATIENT, PRACTITIONER, CLAIM_COVERAGE, OPERATION_NOTE, *MOH.values()):
		for field in fields:
			field.setdefault("module", MODULE)
	create_custom_fields(
		{
			"Patient": PATIENT,
			"Healthcare Practitioner": PRACTITIONER,
			"Insurance Claim Coverage": CLAIM_COVERAGE,
			"Clinical Procedure": OPERATION_NOTE,
			**MOH,
		},
		update=True,
	)
