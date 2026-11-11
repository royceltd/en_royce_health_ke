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
from royce_health_ke.radiology import EXAM_STATUSES as RADIOLOGY_STATUSES
from royce_health_ke.radiology import MODALITIES as RADIOLOGY_MODALITIES
from royce_health_ke.radiology import MOH717_IMAGING as RADIOLOGY_MOH717

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
		"fieldname": "ke_nationality",
		"fieldtype": "Link",
		"label": "Nationality",
		"options": "Country",
		"default": "Kenya",
		"insert_after": "ke_cr_id",
	},
	{
		"fieldname": "ke_county",
		"fieldtype": "Select",
		"label": "County of Residence",
		"options": select(COUNTIES),
		"insert_after": "ke_nationality",
		"fetch_from": "ke_residence.county",
		"fetch_if_empty": 1,
	},
	{
		"fieldname": "ke_sub_county",
		"fieldtype": "Data",
		"label": "Sub-County",
		"insert_after": "ke_county",
		"fetch_from": "ke_residence.sub_county",
		"fetch_if_empty": 1,
	},
	{
		"fieldname": "ke_residence",
		"fieldtype": "Link",
		"options": "Residence",
		"label": "Residence (estate, town or village)",
		"insert_after": "ke_sub_county",
		"in_standard_filter": 1,
		"description": "Pick from the list, or type a new place and choose Create.",
	},
	{
		"fieldname": "ke_next_of_kin_section",
		"fieldtype": "Section Break",
		"label": "Next of Kin",
		"insert_after": "ke_residence",
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
	{
		"fieldname": "ke_sms_consent",
		"fieldtype": "Check",
		"label": "Agrees to Receive SMS",
		"insert_after": "mobile",
		"description": "Appointment reminders, results-ready alerts and hospital announcements. "
		"Ask the patient at registration.",
	},
	{
		"fieldname": "ke_family_history",
		"fieldtype": "Small Text",
		"label": "Family History",
		"insert_after": "surgical_history",
		"description": "E.g. diabetes, hypertension, sickle cell, TB in the family.",
	},
	{
		"fieldname": "ke_social_history",
		"fieldtype": "Small Text",
		"label": "Social History",
		"insert_after": "ke_family_history",
		"description": "Living situation, alcohol, smoking, occupation hazards.",
	},
]

VITAL_SIGNS = [
	{
		"fieldname": "ke_spo2",
		"fieldtype": "Data",
		"label": "SpO2 (%)",
		"insert_after": "respiratory_rate",
		"in_list_view": 1,
	},
	{
		"fieldname": "ke_vitals_status",
		"fieldtype": "Select",
		"label": "Vitals",
		"options": "\nNormal\nAbnormal",
		"insert_after": "signs_time",
		"read_only": 1,
		"in_list_view": 1,
		"in_standard_filter": 1,
		"description": "Worked out on save from the readings and the patient's age.",
	},
	{
		"fieldname": "ke_vitals_flags",
		"fieldtype": "Small Text",
		"label": "Abnormal Readings",
		"insert_after": "ke_vitals_status",
		"read_only": 1,
		"depends_on": "eval:doc.ke_vitals_status == 'Abnormal'",
	},
	{
		"fieldname": "ke_patient_visit",
		"fieldtype": "Link",
		"label": "Patient Visit",
		"options": "Patient Visit",
		"insert_after": "encounter",
		"read_only": 1,
		"description": "The day's open visit, linked on save.",
	},
	{
		"fieldname": "ke_abnormal_fields",
		"fieldtype": "Data",
		"label": "Abnormal Fields",
		"insert_after": "ke_vitals_flags",
		"hidden": 1,
		"read_only": 1,
	},
]

ENCOUNTER = [
	{
		"fieldname": "ke_patient_visit",
		"fieldtype": "Link",
		"label": "Patient Visit",
		"options": "Patient Visit",
		"insert_after": "appointment",
		"read_only": 1,
		"description": "The day's open visit, linked on save.",
	},
	# Clerking, before Marley's symptoms and diagnosis
	{
		"fieldname": "ke_clerking_section",
		"fieldtype": "Section Break",
		"label": "Presenting Complaint",
		"insert_after": "submit_orders_on_save",
	},
	{
		"fieldname": "ke_chief_complaint",
		"fieldtype": "Small Text",
		"label": "Chief Complaint",
		"insert_after": "ke_clerking_section",
		"in_preview": 1,
		"description": "In the patient's words, with how long (e.g. fever and headache for 3 days).",
	},
	{
		"fieldname": "ke_hpi",
		"fieldtype": "Text",
		"label": "History of Presenting Illness",
		"insert_after": "ke_chief_complaint",
	},
	{"fieldname": "ke_clerking_cb", "fieldtype": "Column Break", "insert_after": "ke_hpi"},
	{
		"fieldname": "ke_review_of_systems",
		"fieldtype": "Small Text",
		"label": "Review of Systems",
		"insert_after": "ke_clerking_cb",
	},
	{
		"fieldname": "ke_examination",
		"fieldtype": "Text",
		"label": "Physical Examination",
		"insert_after": "ke_review_of_systems",
		"description": "General and systemic examination findings.",
	},
	# The patient's history, shown and editable here; saved back to the patient
	{
		"fieldname": "ke_history_section",
		"fieldtype": "Section Break",
		"label": "Medical History",
		"insert_after": "ke_examination",
		"description": "From the patient's record. Changes made here update the patient's record when you save.",
	},
	*[
		{
			"fieldname": f"ke_hx_{field}",
			"fieldtype": "Small Text",
			"label": label,
			"insert_after": after,
			"fetch_from": f"patient.{source}",
			"fetch_if_empty": 1,
		}
		for field, source, label, after in (
			("allergies", "allergies", "Allergies", "ke_history_section"),
			("medication", "medication", "Current Medication", "ke_hx_allergies"),
			("medical", "medical_history", "Past Medical History", "ke_hx_medication"),
		)
	],
	{"fieldname": "ke_history_cb", "fieldtype": "Column Break", "insert_after": "ke_hx_medical"},
	*[
		{
			"fieldname": f"ke_hx_{field}",
			"fieldtype": "Small Text",
			"label": label,
			"insert_after": after,
			"fetch_from": f"patient.{source}",
			"fetch_if_empty": 1,
		}
		for field, source, label, after in (
			("surgical", "surgical_history", "Past Surgical History", "ke_history_cb"),
			("family", "ke_family_history", "Family History", "ke_hx_surgical"),
			("social", "ke_social_history", "Social History", "ke_hx_family"),
		)
	],
]

INSURANCE_POLICY = [
	{
		"fieldname": "ke_relation",
		"fieldtype": "Select",
		"label": "Relation to Principal",
		"options": "Principal\nSpouse\nChild\nOther",
		"default": "Principal",
		"insert_after": "policy_number",
	},
	{
		"fieldname": "ke_principal_member",
		"fieldtype": "Data",
		"label": "Principal Member Name",
		"insert_after": "ke_relation",
		"depends_on": "eval:doc.ke_relation != 'Principal'",
	},
	{
		"fieldname": "ke_principal_member_number",
		"fieldtype": "Data",
		"label": "Principal Member No.",
		"insert_after": "ke_principal_member",
		"depends_on": "eval:doc.ke_relation != 'Principal'",
	},
]

SALES_INVOICE = [
	{
		"fieldname": "ke_patient_visit",
		"fieldtype": "Link",
		"label": "Patient Visit",
		"options": "Patient Visit",
		"insert_after": "patient_name",
		"read_only": 1,
		"search_index": 1,
		"depends_on": "patient",
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
		"fieldname": "ke_incision",
		"fieldtype": "Data",
		"label": "Incision",
		"insert_after": "ke_findings",
	},
	{
		"fieldname": "ke_procedure_details",
		"fieldtype": "Text Editor",
		"label": "Procedure Details",
		"insert_after": "ke_incision",
		"description": "Steps and closure. Required to complete a theatre booking.",
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


IMAGING_TEMPLATE = [
	{
		"fieldname": "ke_modality",
		"fieldtype": "Select",
		"label": "Modality",
		"options": select(RADIOLOGY_MODALITIES),
		"insert_after": "observation_category",
		"depends_on": "eval:doc.observation_category=='Imaging'",
	},
	{
		"fieldname": "ke_moh717_imaging",
		"fieldtype": "Select",
		"label": "MOH 717 Imaging Row",
		"options": select(RADIOLOGY_MOH717),
		"insert_after": "ke_modality",
		"depends_on": "eval:doc.observation_category=='Imaging'",
	},
]
_imaging = "eval:doc.observation_category=='Imaging'"
IMAGING_OBSERVATION = [
	{
		"fieldname": "ke_radiology_section",
		"fieldtype": "Section Break",
		"label": "Radiology",
		"insert_after": "observation_category",
		"depends_on": _imaging,
	},
	{
		"fieldname": "ke_accession_number",
		"fieldtype": "Data",
		"label": "Accession Number",
		"insert_after": "ke_radiology_section",
		"read_only": 1,
		"in_standard_filter": 1,
		"search_index": 1,
	},
	{
		"fieldname": "ke_modality",
		"fieldtype": "Select",
		"label": "Modality",
		"options": select(RADIOLOGY_MODALITIES),
		"insert_after": "ke_accession_number",
	},
	{
		"fieldname": "ke_priority",
		"fieldtype": "Select",
		"label": "Priority",
		"options": "Routine\nUrgent\nSTAT",
		"default": "Routine",
		"insert_after": "ke_modality",
	},
	{
		"fieldname": "ke_exam_status",
		"fieldtype": "Select",
		"label": "Exam Status",
		"options": select(RADIOLOGY_STATUSES),
		"insert_after": "ke_priority",
		"read_only": 1,
		"in_standard_filter": 1,
	},
	{"fieldname": "ke_radiology_cb1", "fieldtype": "Column Break", "insert_after": "ke_exam_status"},
	{
		"fieldname": "ke_radiographer",
		"fieldtype": "Data",
		"label": "Radiographer",
		"insert_after": "ke_radiology_cb1",
	},
	{
		"fieldname": "ke_performed_at",
		"fieldtype": "Datetime",
		"label": "Performed At",
		"insert_after": "ke_radiographer",
		"read_only": 1,
	},
	{
		"fieldname": "ke_contrast",
		"fieldtype": "Check",
		"label": "Contrast Given",
		"insert_after": "ke_performed_at",
	},
	{
		"fieldname": "ke_contrast_agent",
		"fieldtype": "Data",
		"label": "Contrast Agent and Dose",
		"insert_after": "ke_contrast",
		"depends_on": "ke_contrast",
	},
	{
		"fieldname": "ke_radiation_dose",
		"fieldtype": "Data",
		"label": "Radiation Dose",
		"insert_after": "ke_contrast_agent",
	},
	{"fieldname": "ke_radiology_cb2", "fieldtype": "Column Break", "insert_after": "ke_radiation_dose"},
	{"fieldname": "ke_images", "fieldtype": "Attach", "label": "Images", "insert_after": "ke_radiology_cb2"},
	{
		"fieldname": "ke_pacs_link",
		"fieldtype": "Data",
		"label": "PACS Viewer Link",
		"options": "URL",
		"insert_after": "ke_images",
	},
	{
		"fieldname": "ke_report_section",
		"fieldtype": "Section Break",
		"label": "Radiology Report",
		"insert_after": "ke_pacs_link",
		"depends_on": _imaging,
		"description": "Findings are kept in the observation's Result.",
	},
	{
		"fieldname": "ke_impression",
		"fieldtype": "Small Text",
		"label": "Impression",
		"insert_after": "ke_report_section",
	},
	{"fieldname": "ke_report_cb", "fieldtype": "Column Break", "insert_after": "ke_impression"},
	{
		"fieldname": "ke_reported_by",
		"fieldtype": "Link",
		"label": "Reported By",
		"options": "Healthcare Practitioner",
		"insert_after": "ke_report_cb",
		"read_only": 1,
	},
	{
		"fieldname": "ke_reported_at",
		"fieldtype": "Datetime",
		"label": "Reported At",
		"insert_after": "ke_reported_by",
		"read_only": 1,
	},
	{
		"fieldname": "ke_verified_by",
		"fieldtype": "Link",
		"label": "Verified By",
		"options": "Healthcare Practitioner",
		"insert_after": "ke_reported_at",
		"read_only": 1,
	},
]
for _field in IMAGING_OBSERVATION:
	_field["allow_on_submit"] = 1


ITEM_GROUP = [
	{
		"fieldname": "ke_revenue_department",
		"fieldtype": "Data",
		"label": "Revenue Department",
		"insert_after": "parent_item_group",
		"description": "Department the management dashboard counts this group's sales under. Blank = worked out from what was ordered (consultation, lab test, imaging, procedure, medicine, bed).",
	},
]


INVOICE_ITEM = [
	{
		"fieldname": "ke_diet_order",
		"fieldtype": "Link",
		"label": "Diet Order",
		"options": "Diet Order",
		"insert_after": "reference_dn",
		"read_only": 1,
		"no_copy": 1,
	},
	{
		"fieldname": "ke_meal_from",
		"fieldtype": "Date",
		"label": "Meals From",
		"insert_after": "ke_diet_order",
		"read_only": 1,
		"no_copy": 1,
		"depends_on": "ke_diet_order",
	},
	{
		"fieldname": "ke_meal_to",
		"fieldtype": "Date",
		"label": "Meals To",
		"insert_after": "ke_meal_from",
		"read_only": 1,
		"no_copy": 1,
		"depends_on": "ke_diet_order",
	},
]

SERVICE_UNIT = [
	{
		"fieldname": "ke_linen_warehouse",
		"fieldtype": "Link",
		"label": "Ward Linen Store",
		"options": "Warehouse",
		"insert_after": "warehouse",
		"depends_on": "is_group",
		"description": "Where this ward's clean linen is kept (laundry module).",
	},
]


def apply():
	for fields in (
		ITEM_GROUP,
		INVOICE_ITEM,
		SERVICE_UNIT,
		PATIENT,
		VITAL_SIGNS,
		ENCOUNTER,
		INSURANCE_POLICY,
		SALES_INVOICE,
		PRACTITIONER,
		CLAIM_COVERAGE,
		OPERATION_NOTE,
		IMAGING_TEMPLATE,
		IMAGING_OBSERVATION,
		*MOH.values(),
	):
		for field in fields:
			field.setdefault("module", MODULE)
	fields = {
		"Patient": PATIENT,
		"Vital Signs": VITAL_SIGNS,
		"Patient Insurance Policy": INSURANCE_POLICY,
		"Healthcare Practitioner": PRACTITIONER,
		"Insurance Claim Coverage": CLAIM_COVERAGE,
		"Clinical Procedure": OPERATION_NOTE,
		"Observation Template": IMAGING_TEMPLATE,
		"Observation": IMAGING_OBSERVATION,
		"Item Group": ITEM_GROUP,
		"Sales Invoice Item": INVOICE_ITEM,
		"Sales Invoice": SALES_INVOICE,
		"Healthcare Service Unit": SERVICE_UNIT,
	}
	# MOH has its own Patient Encounter fields: combine, don't replace.
	for doctype, extra in MOH.items():
		fields[doctype] = [*fields.get(doctype, []), *extra]
	fields["Patient Encounter"] = [*fields.get("Patient Encounter", []), *ENCOUNTER]
	create_custom_fields(fields, update=True)
