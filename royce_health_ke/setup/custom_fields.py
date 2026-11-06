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


def apply():
	for fields in (PATIENT, PRACTITIONER):
		for field in fields:
			field.setdefault("module", MODULE)
	create_custom_fields({"Patient": PATIENT, "Healthcare Practitioner": PRACTITIONER}, update=True)
