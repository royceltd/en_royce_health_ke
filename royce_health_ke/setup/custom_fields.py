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
		# filled from the residence only when empty (identity.fill_from_residence):
		# Frappe's form ignores "fetch if empty" and blanked a chosen county
		"fetch_from": "",
		"fetch_if_empty": 0,
	},
	{
		"fieldname": "ke_sub_county",
		"fieldtype": "Data",
		"label": "Sub-County",
		"description": "Choose the county first: its sub-counties are offered as you type.",
		"insert_after": "ke_county",
		# filled from the residence only when empty (identity.fill_from_residence):
		# Frappe's form ignores "fetch if empty" and blanked a chosen county
		"fetch_from": "",
		"fetch_if_empty": 0,
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
	# Consent at registration (dataprotection.py, Data Protection Act)
	{
		"fieldname": "ke_consent_section",
		"fieldtype": "Section Break",
		"label": "Consent (Data Protection)",
		"insert_after": "ke_nok_phone",
	},
	{
		"fieldname": "ke_privacy_notice",
		"fieldtype": "Check",
		"label": "Privacy Notice Given",
		"insert_after": "ke_consent_section",
		"description": "Tell the patient: their information is used for their care, billing, insurance claims "
		"and Ministry of Health reports; it is kept confidential and shared only as the law allows; they may "
		"ask for a copy, a correction or deletion. Tick once told.",
	},
	{
		"fieldname": "ke_consent_given_by",
		"fieldtype": "Data",
		"label": "Consent Given By",
		"insert_after": "ke_privacy_notice",
		"description": "Blank when the patient answered. For a child or a patient who can't: the parent or guardian's name.",
	},
	{
		"fieldname": "ke_consent_relation",
		"fieldtype": "Select",
		"label": "Relation to the Patient",
		"options": select(NEXT_OF_KIN_RELATIONSHIPS),
		"insert_after": "ke_consent_given_by",
		"depends_on": "ke_consent_given_by",
	},
	{"fieldname": "ke_consent_cb", "fieldtype": "Column Break", "insert_after": "ke_consent_relation"},
	{
		"fieldname": "ke_consent_at",
		"fieldtype": "Datetime",
		"label": "Consent Recorded At",
		"insert_after": "ke_consent_cb",
		"read_only": 1,
		"no_copy": 1,
	},
	{
		"fieldname": "ke_consent_recorded_by",
		"fieldtype": "Link",
		"label": "Consent Recorded By",
		"options": "User",
		"insert_after": "ke_consent_at",
		"read_only": 1,
		"no_copy": 1,
		"description": "Every change is kept in the Patient Consent Log.",
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
	# Height is taken in centimetres; Marley's Height (in metres), which BMI
	# and the growth charts use, is worked out from it (royce_health_ke.vitals).
	{
		"fieldname": "ke_height_cm",
		"fieldtype": "Float",
		"label": "Height (cm)",
		"insert_after": "height",
		"precision": "1",
		"in_list_view": 1,
	},
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
	# Child growth (royce_health_ke.growth): WHO z-scores for children under 5.
	{
		"fieldname": "ke_growth_section",
		"fieldtype": "Section Break",
		"label": "Child Growth (WHO)",
		"insert_after": "nutrition_note",
		"collapsible": 1,
		"depends_on": "eval:doc.ke_nutrition_status",
		"description": "Z-scores against the WHO Child Growth Standards, worked out on save for children under 5.",
	},
	{
		"fieldname": "ke_nutrition_status",
		"fieldtype": "Data",
		"label": "Nutrition Status",
		"insert_after": "ke_growth_section",
		"read_only": 1,
		"in_list_view": 1,
	},
	{
		"fieldname": "ke_wflh_z",
		"fieldtype": "Float",
		"label": "Weight-for-Length/Height (z)",
		"insert_after": "ke_nutrition_status",
		"read_only": 1,
		"precision": "2",
	},
	{
		"fieldname": "ke_growth_cb",
		"fieldtype": "Column Break",
		"insert_after": "ke_wflh_z",
	},
	{
		"fieldname": "ke_wfa_z",
		"fieldtype": "Float",
		"label": "Weight-for-Age (z)",
		"insert_after": "ke_growth_cb",
		"read_only": 1,
		"precision": "2",
	},
	{
		"fieldname": "ke_lhfa_z",
		"fieldtype": "Float",
		"label": "Length/Height-for-Age (z)",
		"insert_after": "ke_wfa_z",
		"read_only": 1,
		"precision": "2",
	},
	{
		"fieldname": "ke_bmi_z",
		"fieldtype": "Float",
		"label": "BMI-for-Age (z)",
		"insert_after": "ke_lhfa_z",
		"read_only": 1,
		"precision": "2",
	},
]

MEDICATION = [
	# Clinical decision support (royce_health_ke.cds): alerts when prescribed.
	{
		"fieldname": "ke_cds_section",
		"fieldtype": "Section Break",
		"label": "Safety Alerts",
		"insert_after": "is_orderable",
		"collapsible": 1,
	},
	{
		"fieldname": "ke_recalled",
		"fieldtype": "Check",
		"label": "Recalled",
		"insert_after": "ke_cds_section",
		"description": "A recall notice from the Pharmacy and Poisons Board or the manufacturer: prescribers get a critical alert.",
	},
	{
		"fieldname": "ke_recall_note",
		"fieldtype": "Data",
		"label": "Recall Notice",
		"insert_after": "ke_recalled",
		"depends_on": "ke_recalled",
		"description": "Reference, batches affected and what to use instead.",
	},
	{
		"fieldname": "ke_cds_cb",
		"fieldtype": "Column Break",
		"insert_after": "ke_recall_note",
	},
	{
		"fieldname": "ke_side_effects",
		"fieldtype": "Small Text",
		"label": "Side Effects to Explain",
		"insert_after": "ke_cds_cb",
		"description": "Shown to the prescriber as a reminder to counsel the patient, e.g. nausea, vomiting.",
	},
]

THERAPY_SESSION = [
	{
		"fieldname": "ke_session_notes",
		"fieldtype": "Text Editor",
		"label": "Session Notes",
		"insert_after": "exercises",
		"description": "What was done, the patient's response and the plan (physiotherapy, occupational therapy, counselling, social work).",
	},
]

# The consultation in the hospital's order (consultation.py sets the order of
# the fields once): Patient, Observation, Requests, Results, Diagnosis,
# Prescription, Complete. Positions below only matter if the hospital already
# ordered the form itself.
CONSULTATION_TABS = [
	{
		"fieldname": "ke_tab_patient",
		"fieldtype": "Tab Break",
		"label": "Patient",
		"insert_after": "ke_patient_visit",
	},
	{
		"fieldname": "ke_tab_observation",
		"fieldtype": "Tab Break",
		"label": "Observation",
		"insert_after": "submit_orders_on_save",
	},
	{
		"fieldname": "ke_obs_section",
		"fieldtype": "Section Break",
		"label": "",
		"insert_after": "ke_hx_social",
		"depends_on": "eval:doc.patient_sex != 'Male'",
	},
	{
		"fieldname": "ke_obs_gynae",
		"fieldtype": "Text",
		"label": "OBS/Gynae",
		"insert_after": "ke_obs_section",
		"description": "LMP, gravida/para, contraception, menstrual and gynaecological history.",
	},
	# The clerking order (Bethesda, 18 Nov 2026): CC, HPI, ROS, PMH/PSH, FH, SH,
	# OBS/Gynae, then the examination last
	{
		"fieldname": "ke_exam_section",
		"fieldtype": "Section Break",
		"label": "",
		"insert_after": "ke_obs_gynae",
	},
	{
		"fieldname": "ke_examination",
		"fieldtype": "Text",
		"label": "Physical Examination",
		"insert_after": "ke_exam_section",
		"description": "General and systemic examination findings.",
	},
	# Request Type picker (requests.py): the Requests tab shows that category only
	{
		"fieldname": "ke_request_type_section",
		"fieldtype": "Section Break",
		"insert_after": "ke_tab_requests",
	},
	{
		"fieldname": "ke_request_type",
		"fieldtype": "Link",
		"label": "Request Type",
		"options": "Request Category",
		"insert_after": "ke_request_type_section",
		"description": "Choose a type to list only its requests, with this patient's price. Blank = all.",
	},
	{
		"fieldname": "ke_tab_requests",
		"fieldtype": "Tab Break",
		"label": "Requests",
		"insert_after": "drug_prescription",
	},
	{"fieldname": "ke_requests_section", "fieldtype": "Section Break", "insert_after": "therapies"},
	{
		"fieldname": "ke_send_requests",
		"fieldtype": "Button",
		"label": "Send Requests",
		"insert_after": "ke_requests_section",
		"depends_on": "eval:!doc.__islocal && doc.docstatus == 0",
		"description": "Sends the lab, imaging and procedure requests now: they go on the bill and to "
		"their service point, and the consultation stays open for the results.",
	},
	{
		"fieldname": "ke_tab_results",
		"fieldtype": "Tab Break",
		"label": "Results",
		"insert_after": "ke_send_requests",
	},
	{"fieldname": "ke_results_section", "fieldtype": "Section Break", "insert_after": "ke_tab_results"},
	{
		"fieldname": "ke_results_html",
		"fieldtype": "HTML",
		"label": "Results",
		"insert_after": "ke_results_section",
	},
	{
		"fieldname": "ke_tab_diagnosis",
		"fieldtype": "Tab Break",
		"label": "Diagnosis",
		"insert_after": "ke_results_html",
	},
	{
		"fieldname": "ke_tab_prescription",
		"fieldtype": "Tab Break",
		"label": "Prescription",
		"insert_after": "codification_table",
	},
	{"fieldname": "ke_pharmacy_section", "fieldtype": "Section Break", "insert_after": "ke_tab_prescription"},
	{
		"fieldname": "ke_pharmacy_html",
		"fieldtype": "HTML",
		"label": "Pharmacy",
		"insert_after": "ke_pharmacy_section",
	},
	{
		"fieldname": "ke_prescribe_html",
		"fieldtype": "HTML",
		"label": "Order Drug",
		"insert_after": "ke_pharmacy_html",
	},
	{
		"fieldname": "ke_tab_complete",
		"fieldtype": "Tab Break",
		"label": "Complete",
		"insert_after": "therapies",
	},
	{
		"fieldname": "ke_referral_section",
		"fieldtype": "Section Break",
		"label": "Referral",
		"insert_after": "referring_practitioner",
	},
	{"fieldname": "ke_complete_section", "fieldtype": "Section Break", "insert_after": "amended_from"},
	{
		"fieldname": "ke_complete_consultation",
		"fieldtype": "Button",
		"label": "Complete Consultation",
		"insert_after": "ke_complete_section",
		"depends_on": "eval:!doc.__islocal && doc.docstatus == 0",
		"description": "Places any orders not sent yet, closes the consultation and sends the patient on.",
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
	# Clerking, before Marley's symptoms and diagnosis. Two fields side by side
	# in Bethesda's order, one continuous form without headings (20 Nov 2026):
	# Chief Complaint | HPI, Review of Systems | Past Medical and Surgical
	# History, Family | Social History; then OBS/Gynae and the examination.
	{
		"fieldname": "ke_clerking_section",
		"fieldtype": "Section Break",
		"label": "",
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
	{"fieldname": "ke_clerking_cb", "fieldtype": "Column Break", "insert_after": "ke_chief_complaint"},
	{
		"fieldname": "ke_hpi",
		"fieldtype": "Text",
		"label": "History of Presenting Illness",
		"insert_after": "ke_clerking_cb",
	},
	# The patient's history is shown and editable here and saved back to the
	# patient (visits.py), without saying so on the form.
	{
		"fieldname": "ke_history_section",
		"fieldtype": "Section Break",
		"label": "",
		"description": "",
		"insert_after": "ke_hpi",
	},
	{
		"fieldname": "ke_review_of_systems",
		"fieldtype": "Small Text",
		"label": "Review of Systems",
		"insert_after": "ke_history_section",
	},
	{"fieldname": "ke_history_cb", "fieldtype": "Column Break", "insert_after": "ke_review_of_systems"},
	*[
		{
			"fieldname": f"ke_hx_{field}",
			"fieldtype": "Small Text",
			"label": label,
			"insert_after": after,
			"fetch_from": f"patient.{source}",
			"fetch_if_empty": 1,
			"hidden": hidden,
		}
		for field, source, label, after, hidden in (
			("medical", "medical_history", "Past Medical History", "ke_history_cb", 0),
			("surgical", "surgical_history", "Past Surgical History", "ke_hx_medical", 0),
			# kept on the patient's record, not asked on the consultation
			("allergies", "allergies", "Allergies", "ke_hx_surgical", 1),
			("medication", "medication", "Current Medication", "ke_hx_allergies", 1),
		)
	],
	{
		"fieldname": "ke_social_section",
		"fieldtype": "Section Break",
		"label": "",
		"insert_after": "ke_hx_medication",
	},
	{
		"fieldname": "ke_hx_family",
		"fieldtype": "Small Text",
		"label": "Family History",
		"insert_after": "ke_social_section",
		"fetch_from": "patient.ke_family_history",
		"fetch_if_empty": 1,
	},
	{"fieldname": "ke_social_cb", "fieldtype": "Column Break", "insert_after": "ke_hx_family"},
	{
		"fieldname": "ke_hx_social",
		"fieldtype": "Small Text",
		"label": "Social History",
		"insert_after": "ke_social_cb",
		"fetch_from": "patient.ke_social_history",
		"fetch_if_empty": 1,
	},
	*CONSULTATION_TABS,
]

LAB_TEST = [
	{
		"fieldname": "ke_result_at",
		"fieldtype": "Datetime",
		"label": "Result Time",
		"insert_after": "submitted_date",
		"read_only": 1,
		"no_copy": 1,
		"description": "When the result was submitted (for turnaround time).",
	},
	{
		"fieldname": "ke_patient_visit",
		"fieldtype": "Link",
		"label": "Patient Visit",
		"options": "Patient Visit",
		"insert_after": "practitioner_name",
		"read_only": 1,
		"no_copy": 1,
	},
	{
		"fieldname": "ke_lab_work_section",
		"fieldtype": "Section Break",
		"label": "Sample and Validation",
		"insert_after": "ke_result_at",
		"collapsible": 1,
	},
	{
		"fieldname": "ke_sample_collected_at",
		"fieldtype": "Datetime",
		"label": "Sample Collected At",
		"insert_after": "ke_lab_work_section",
		"read_only": 1,
		"no_copy": 1,
	},
	{
		"fieldname": "ke_sample_collected_by",
		"fieldtype": "Link",
		"label": "Sample Collected By",
		"options": "User",
		"insert_after": "ke_sample_collected_at",
		"read_only": 1,
		"no_copy": 1,
	},
	{
		"fieldname": "ke_results_by",
		"fieldtype": "Link",
		"label": "Results Entered By",
		"options": "User",
		"insert_after": "ke_sample_collected_by",
		"read_only": 1,
		"no_copy": 1,
	},
	{"fieldname": "ke_lab_work_cb", "fieldtype": "Column Break", "insert_after": "ke_results_by"},
	{
		"fieldname": "ke_seen_at",
		"fieldtype": "Datetime",
		"label": "Seen by Clinician At",
		"insert_after": "ke_lab_work_cb",
		"read_only": 1,
		"no_copy": 1,
	},
	{
		"fieldname": "ke_seen_by",
		"fieldtype": "Link",
		"label": "Seen by Clinician",
		"options": "User",
		"insert_after": "ke_seen_at",
		"read_only": 1,
		"no_copy": 1,
	},
]


# One payment status per order (payment_status.py): what the worklists read.
def payment_fields(insert_after):
	return [
		{
			"fieldname": "ke_payment_status",
			"fieldtype": "Select",
			"label": "Payment",
			"options": "\nNot Billed\nBilled\nPaid\nExempt",
			"insert_after": insert_after,
			"read_only": 1,
			"no_copy": 1,
			"in_standard_filter": 1,
			"search_index": 1,
			"description": "Kept up to date when the order is billed or paid, or when the patient "
			"is served before paying (insured, inpatient, casualty, approved).",
		},
		{
			"fieldname": "ke_payment_exemption",
			"fieldtype": "Data",
			"label": "Served Before Payment Because",
			"insert_after": "ke_payment_status",
			"read_only": 1,
			"no_copy": 1,
			"depends_on": "eval:doc.ke_payment_status == 'Exempt'",
		},
	]


# A user account valid until a date (security.py: disabled the day after).
USER = [
	{
		"fieldname": "ke_valid_until",
		"fieldtype": "Date",
		"label": "Valid Until",
		"insert_after": "enabled",
		"description": "The account is disabled automatically after this date (a locum, an intern, "
		"a contract). Leave empty for no end date.",
	},
]


SERVICE_REQUEST = [
	{
		"fieldname": "ke_patient_visit",
		"fieldtype": "Link",
		"label": "Patient Visit",
		"options": "Patient Visit",
		"insert_after": "order_group",
		"read_only": 1,
		"no_copy": 1,
	},
	*payment_fields("ke_patient_visit"),
	{
		# put on the cash visit's draft bill once (visit_bill.draft_cash_bill); a
		# line the cashier then takes off is not put back
		"fieldname": "ke_auto_billed",
		"fieldtype": "Check",
		"label": "Put on the Draft Bill",
		"insert_after": "ke_patient_visit",
		"read_only": 1,
		"hidden": 1,
		"no_copy": 1,
	},
	{
		"fieldname": "ke_cancel_reason",
		"fieldtype": "Data",
		"label": "Cancelled Because",
		"insert_after": "ke_auto_billed",
		"read_only": 1,
		"no_copy": 1,
		"depends_on": "ke_cancel_reason",
	},
]

LAB_TEST_TEMPLATE = [
	{
		"fieldname": "ke_target_tat_minutes",
		"fieldtype": "Int",
		"label": "Target Turnaround (minutes)",
		"insert_after": "lab_test_group",
		"description": "From order to result, for the Turnaround Time report. Blank = no target.",
	},
]

PAYMENT_ENTRY = [
	{
		"fieldname": "ke_cashier_shift",
		"fieldtype": "Link",
		"label": "Cashier Shift",
		"options": "Cashier Shift",
		"insert_after": "mode_of_payment",
		"read_only": 1,
		"no_copy": 1,
		"depends_on": "ke_cashier_shift",
		"description": "The cashier's shift this payment was taken on.",
	},
	{
		"fieldname": "ke_amount_received",
		"fieldtype": "Currency",
		"label": "Amount Received",
		"options": "paid_from_account_currency",
		"insert_after": "ke_cashier_shift",
		"read_only": 1,
		"no_copy": 1,
		"depends_on": "ke_amount_received",
		"description": "Cash handed over by the patient (Take Payment).",
	},
	{
		"fieldname": "ke_change",
		"fieldtype": "Currency",
		"label": "Change Given",
		"options": "paid_from_account_currency",
		"insert_after": "ke_amount_received",
		"read_only": 1,
		"no_copy": 1,
		"depends_on": "ke_change",
	},
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
		"fieldname": "ke_cashier_shift",
		"fieldtype": "Link",
		"label": "Cashier Shift",
		"options": "Cashier Shift",
		"insert_after": "is_pos",
		"read_only": 1,
		"no_copy": 1,
		"depends_on": "ke_cashier_shift",
	},
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
	{
		"fieldname": "ke_bill_for",
		"fieldtype": "Select",
		"label": "Bill For",
		"options": "\nInsurer\nPatient",
		"insert_after": "ke_patient_visit",
		"read_only": 1,
		"no_copy": 1,
		"depends_on": "ke_bill_for",
		"description": "An insured visit's two bills: the insurer's (what the scheme covers) and the patient's (what it doesn't, paid first).",
	},
]

# Prescribing in dispensing units (dispensing.py, v0.45): the dose is written
# in clinical units (ml, mg, tablets) and the quantity is worked out in the
# unit the pharmacy hands over and bills (the drug Item's stock unit).
ROUTES = (
	"Oral",
	"Intravenous (IV)",
	"Intramuscular (IM)",
	"Subcutaneous (SC)",
	"Topical",
	"Inhaled",
	"Nebulised",
	"Sublingual",
	"Rectal (PR)",
	"Vaginal (PV)",
	"Eye",
	"Ear",
	"Nasal",
	"Other",
)

MEDICATION_DISPENSING = [
	{
		"fieldname": "ke_dispensing_section",
		"fieldtype": "Section Break",
		"label": "Dose and Dispensing Unit",
		"insert_after": "dosage_form",
		"description": "How a prescription's quantity is worked out: dose x times a day x days, "
		"in the dose unit, then rounded up to whole dispensing units (the Item's stock unit). "
		"E.g. a 100 ml bottle: dose unit ml, pack size 100.",
	},
	{
		"fieldname": "ke_dose_uom",
		"fieldtype": "Link",
		"label": "Dose Unit",
		"options": "UOM",
		"insert_after": "ke_dispensing_section",
		"description": "The unit the doctor writes the dose in (ml, mg, tablet).",
	},
	{
		"fieldname": "ke_pack_size",
		"fieldtype": "Float",
		"label": "Pack Size (in Dose Units)",
		"insert_after": "ke_dose_uom",
		"description": "How much of the dose unit one dispensing unit holds: 100 for a 100 ml "
		"bottle, 1 for a tablet. Blank: the strength when the dose is in the strength unit, else 1.",
	},
	{"fieldname": "ke_dispensing_cb", "fieldtype": "Column Break", "insert_after": "ke_pack_size"},
	{
		"fieldname": "ke_default_route",
		"fieldtype": "Select",
		"label": "Default Route",
		"options": select(ROUTES),
		"insert_after": "ke_dispensing_cb",
	},
	{
		"fieldname": "ke_prescription_only",
		"fieldtype": "Check",
		"label": "Prescription Only (POM)",
		"insert_after": "ke_default_route",
		"description": "Sold at the counter only against a prescription: the prescriber is recorded (PPB).",
	},
]

DRUG_PRESCRIPTION = [
	{
		"fieldname": "ke_dose",
		"fieldtype": "Float",
		"label": "Dose",
		"insert_after": "drug_name",
		"in_list_view": 1,
		"columns": 1,
		"description": "Per administration, in the dose unit.",
	},
	{
		"fieldname": "ke_dose_uom",
		"fieldtype": "Link",
		"label": "Dose Unit",
		"options": "UOM",
		"insert_after": "ke_dose",
		"fetch_from": "medication.ke_dose_uom",
		"fetch_if_empty": 1,
	},
	{
		"fieldname": "ke_route",
		"fieldtype": "Select",
		"label": "Route",
		"options": select(ROUTES),
		"insert_after": "ke_dose_uom",
		"fetch_from": "medication.ke_default_route",
		"fetch_if_empty": 1,
	},
	{
		"fieldname": "ke_start_date",
		"fieldtype": "Date",
		"label": "Start Date",
		"insert_after": "comment",
	},
	{
		"fieldname": "ke_start_time",
		"fieldtype": "Time",
		"label": "Start Time",
		"insert_after": "ke_start_date",
	},
	{
		"fieldname": "ke_quantity",
		"fieldtype": "Float",
		"label": "Quantity",
		"insert_after": "ke_start_time",
		"in_list_view": 1,
		"columns": 1,
		"description": "In dispensing units, worked out from the dose, frequency and duration; "
		"change it if needed. This is what the pharmacy dispenses and bills.",
	},
	{
		"fieldname": "ke_dispensing_unit",
		"fieldtype": "Data",
		"label": "Dispensing Unit",
		"insert_after": "ke_quantity",
		"read_only": 1,
	},
	# The Order Drug panel (prescribing.py)
	{
		"fieldname": "ke_buy_externally",
		"fieldtype": "Check",
		"label": "Buy Externally",
		"insert_after": "ke_dispensing_unit",
		"description": "The patient buys it outside: on the prescription, not dispensed or billed here.",
	},
	{
		"fieldname": "ke_chronic",
		"fieldtype": "Check",
		"label": "Chronic",
		"insert_after": "ke_buy_externally",
		"description": "A long-term medicine: listed under Chronic on the patient's next consultations.",
	},
	{
		"fieldname": "ke_draft",
		"fieldtype": "Check",
		"label": "Draft",
		"insert_after": "ke_chronic",
		"read_only": 1,
		"description": "Saved to draft on the Order Drug panel: not sent to the pharmacy until Submit.",
	},
]

MEDICATION_REQUEST_DOSE = [
	{
		"fieldname": "ke_dose_section",
		"fieldtype": "Section Break",
		"label": "Dose",
		"insert_after": "dosage",
	},
	{
		"fieldname": "ke_dose",
		"fieldtype": "Float",
		"label": "Dose",
		"insert_after": "ke_dose_section",
		"read_only": 1,
	},
	{
		"fieldname": "ke_dose_uom",
		"fieldtype": "Link",
		"label": "Dose Unit",
		"options": "UOM",
		"insert_after": "ke_dose",
		"read_only": 1,
	},
	{
		"fieldname": "ke_route",
		"fieldtype": "Data",
		"label": "Route",
		"insert_after": "ke_dose_uom",
		"read_only": 1,
	},
	{"fieldname": "ke_dose_cb", "fieldtype": "Column Break", "insert_after": "ke_route"},
	{
		"fieldname": "ke_start",
		"fieldtype": "Datetime",
		"label": "Start",
		"insert_after": "ke_dose_cb",
		"read_only": 1,
	},
	{
		"fieldname": "ke_chronic",
		"fieldtype": "Check",
		"label": "Chronic",
		"insert_after": "ke_start",
		"read_only": 1,
	},
]

# ICD-11 on the consultation's diagnosis row (diagnosis.py): name or code,
# either one searched, the other filled in.
ENCOUNTER_DIAGNOSIS = [
	{
		"fieldname": "ke_icd11_code",
		"fieldtype": "Link",
		"label": "ICD-11 Code",
		"options": "Code Value",
		"insert_after": "diagnosis",
		"in_list_view": 1,
		"columns": 3,
	},
]

# Request routing (requests.py): each request's category and the service point it goes to
SERVICE_REQUEST_ROUTING = [
	{
		"fieldname": "ke_request_category",
		"fieldtype": "Link",
		"label": "Request Category",
		"options": "Request Category",
		"insert_after": "ke_cancel_reason",
		"read_only": 1,
		"no_copy": 1,
	},
	{
		"fieldname": "ke_service_point",
		"fieldtype": "Data",
		"label": "Service Point",
		"insert_after": "ke_request_category",
		"read_only": 1,
		"no_copy": 1,
		"in_standard_filter": 1,
		"search_index": 1,
	},
	{
		"fieldname": "ke_done_at",
		"fieldtype": "Datetime",
		"label": "Done At",
		"insert_after": "ke_service_point",
		"read_only": 1,
		"no_copy": 1,
		"depends_on": "ke_done_at",
	},
	{
		"fieldname": "ke_done_by",
		"fieldtype": "Link",
		"label": "Done By",
		"options": "User",
		"insert_after": "ke_done_at",
		"read_only": 1,
		"no_copy": 1,
		"depends_on": "ke_done_at",
	},
	{
		"fieldname": "ke_done_note",
		"fieldtype": "Small Text",
		"label": "Done Note",
		"insert_after": "ke_done_by",
		"read_only": 1,
		"no_copy": 1,
		"depends_on": "ke_done_at",
	},
]

# Counter prescriptions (pharmacy.counter_sale, PPB): who prescribed, and the script
COUNTER_PRESCRIPTION = [
	{
		"fieldname": "ke_prescriber_name",
		"fieldtype": "Data",
		"label": "Prescriber",
		"insert_after": "ke_walk_in_name",
		"depends_on": "ke_pharmacy_sale",
	},
	{
		"fieldname": "ke_prescriber_reg",
		"fieldtype": "Data",
		"label": "Prescriber Registration No.",
		"insert_after": "ke_prescriber_name",
		"depends_on": "ke_prescriber_name",
	},
	{
		"fieldname": "ke_prescriber_facility",
		"fieldtype": "Data",
		"label": "Prescribing Facility",
		"insert_after": "ke_prescriber_reg",
		"depends_on": "ke_prescriber_name",
	},
	{
		"fieldname": "ke_prescription_date",
		"fieldtype": "Date",
		"label": "Prescription Date",
		"insert_after": "ke_prescriber_facility",
		"depends_on": "ke_prescriber_name",
	},
	{
		"fieldname": "ke_prescription_image",
		"fieldtype": "Attach Image",
		"label": "Prescription (photo)",
		"insert_after": "ke_prescription_date",
		"depends_on": "ke_pharmacy_sale",
	},
]

COUNTER_PRESCRIPTION_ITEM = [
	{
		"fieldname": "ke_dose",
		"fieldtype": "Float",
		"label": "Dose",
		"insert_after": "ke_instructions",
		"depends_on": "ke_dose",
	},
	{
		"fieldname": "ke_dosage",
		"fieldtype": "Link",
		"label": "Frequency",
		"options": "Prescription Dosage",
		"insert_after": "ke_dose",
		"depends_on": "ke_dosage",
	},
	{
		"fieldname": "ke_period",
		"fieldtype": "Link",
		"label": "Duration",
		"options": "Prescription Duration",
		"insert_after": "ke_dosage",
		"depends_on": "ke_period",
	},
]

# Admission from the consultation and the payer's pre-authorisation (inpatient.py)
INPATIENT_RECORD = [
	{
		"fieldname": "ke_admission_section",
		"fieldtype": "Section Break",
		"label": "Admission Request",
		"insert_after": "admission_instruction",
	},
	{
		"fieldname": "ke_ward",
		"fieldtype": "Link",
		"label": "Ward",
		"options": "Healthcare Service Unit",
		"insert_after": "ke_admission_section",
		"in_standard_filter": 1,
	},
	{
		"fieldname": "ke_urgency",
		"fieldtype": "Select",
		"label": "Urgency",
		"options": "\nRoutine\nUrgent\nEmergency",
		"insert_after": "ke_ward",
		"in_list_view": 1,
	},
	{
		"fieldname": "ke_admission_reason",
		"fieldtype": "Small Text",
		"label": "Admission Reason",
		"insert_after": "ke_urgency",
	},
	{"fieldname": "ke_admission_cb", "fieldtype": "Column Break", "insert_after": "ke_admission_reason"},
	{
		"fieldname": "ke_patient_visit",
		"fieldtype": "Link",
		"label": "Patient Visit",
		"options": "Patient Visit",
		"insert_after": "ke_admission_cb",
		"read_only": 1,
	},
	{
		"fieldname": "ke_preauth_status",
		"fieldtype": "Select",
		"label": "Pre-authorisation",
		"options": "\nPending\nReceived",
		"insert_after": "ke_patient_visit",
		"description": "The payer's approval of the admission. Pending holds the claim, never the care.",
	},
	{
		"fieldname": "ke_preauth_code",
		"fieldtype": "Data",
		"label": "Pre-authorisation Code",
		"insert_after": "ke_preauth_status",
		"depends_on": "ke_preauth_status",
	},
	{
		"fieldname": "ke_preauth_due",
		"fieldtype": "Datetime",
		"label": "Pre-authorisation Due",
		"insert_after": "ke_preauth_code",
		"read_only": 1,
		"depends_on": "eval:doc.ke_preauth_status=='Pending'",
	},
	# a move to another ward, asked by the ward the patient is on and taken up
	# by the receiving ward (Bethesda, 20 Nov 2026: "ward to theatre or maternity")
	{
		"fieldname": "ke_transfer_section",
		"fieldtype": "Section Break",
		"label": "Transfer Request",
		"insert_after": "ke_preauth_due",
		"collapsible": 1,
		"depends_on": "ke_transfer_to",
	},
	{
		"fieldname": "ke_transfer_to",
		"fieldtype": "Link",
		"label": "Transfer To Ward",
		"options": "Healthcare Service Unit",
		"insert_after": "ke_transfer_section",
		"read_only": 1,
	},
	{
		"fieldname": "ke_transfer_reason",
		"fieldtype": "Small Text",
		"label": "Transfer Reason",
		"insert_after": "ke_transfer_to",
		"read_only": 1,
	},
	{"fieldname": "ke_transfer_cb", "fieldtype": "Column Break", "insert_after": "ke_transfer_reason"},
	{
		"fieldname": "ke_transfer_urgency",
		"fieldtype": "Select",
		"label": "Transfer Urgency",
		"options": "\nRoutine\nUrgent\nEmergency",
		"insert_after": "ke_transfer_cb",
		"read_only": 1,
	},
	{
		"fieldname": "ke_transfer_requested_by",
		"fieldtype": "Link",
		"label": "Transfer Requested By",
		"options": "User",
		"insert_after": "ke_transfer_urgency",
		"read_only": 1,
	},
	{
		"fieldname": "ke_transfer_requested_at",
		"fieldtype": "Datetime",
		"label": "Transfer Requested At",
		"insert_after": "ke_transfer_requested_by",
		"read_only": 1,
	},
]

# The ward's notes carry the patient's condition (Bethesda's notes, PDF (9))
PATIENT_STATUSES = ("Stable", "Improving", "Unchanged", "Deteriorating", "Critical")
CLINICAL_NOTE = [
	{
		"fieldname": "ke_patient_status",
		"fieldtype": "Select",
		"label": "Patient Status",
		"options": select(PATIENT_STATUSES),
		"insert_after": "clinical_note_type",
		"in_list_view": 1,
	},
]

INPATIENT_DISPOSITION = [
	{
		"fieldname": "ke_referred_to",
		"fieldtype": "Data",
		"label": "Referred To",
		"insert_after": "ke_discharge_outcome",
		"depends_on": "eval:doc.ke_discharge_outcome=='Referred Out'",
	},
	{
		"fieldname": "ke_disposition_note",
		"fieldtype": "Small Text",
		"label": "Disposition Note",
		"insert_after": "ke_referred_to",
	},
]

INSURANCE_PAYOR = [
	{
		"fieldname": "ke_admission_preauth",
		"fieldtype": "Check",
		"label": "Admissions Need Pre-authorisation",
		"insert_after": "insurance_payor_name",
		"description": "Insured admissions wait for this payer's code; the claim is held until it is recorded.",
	},
	{
		"fieldname": "ke_preauth_hours",
		"fieldtype": "Int",
		"label": "Pre-authorisation Within (hours)",
		"insert_after": "ke_admission_preauth",
		"depends_on": "ke_admission_preauth",
		"default": "24",
	},
]

MEDICATION_REQUEST = [
	{
		"fieldname": "ke_insurance_coverage",
		"fieldtype": "Link",
		"label": "Insurance Coverage",
		"options": "Patient Insurance Coverage",
		"insert_after": "billing_status",
		"read_only": 1,
		"no_copy": 1,
		"description": "The scheme's cover for this drug, from an insured consultation.",
	},
	{
		"fieldname": "ke_pharmacy_section",
		"fieldtype": "Section Break",
		"label": "Pharmacy",
		"insert_after": "ke_insurance_coverage",
		"collapsible": 1,
	},
	{
		"fieldname": "ke_pharmacy_status",
		"fieldtype": "Select",
		"label": "Pharmacy Status",
		"options": "\nPartly Dispensed\nDispensed\nBuy Outside\nSent Back",
		"insert_after": "ke_pharmacy_section",
		"read_only": 1,
		"no_copy": 1,
		"allow_on_submit": 1,
		"in_standard_filter": 1,
	},
	{
		"fieldname": "ke_dispensed_qty",
		"fieldtype": "Float",
		"label": "Dispensed Quantity",
		"insert_after": "ke_pharmacy_status",
		"read_only": 1,
		"no_copy": 1,
		"allow_on_submit": 1,
	},
	{
		"fieldname": "ke_pharmacy_note",
		"fieldtype": "Small Text",
		"label": "Pharmacy Note",
		"insert_after": "ke_dispensed_qty",
		"read_only": 1,
		"no_copy": 1,
		"allow_on_submit": 1,
		"description": "Why the drug is bought outside, or what the doctor is asked to change.",
	},
	*payment_fields("ke_pharmacy_note"),
]

DELIVERY_NOTE = [
	{
		"fieldname": "ke_patient",
		"fieldtype": "Link",
		"label": "Patient",
		"options": "Patient",
		"insert_after": "customer_name",
		"read_only": 1,
		"no_copy": 1,
	},
	{
		"fieldname": "ke_patient_visit",
		"fieldtype": "Link",
		"label": "Patient Visit",
		"options": "Patient Visit",
		"insert_after": "ke_patient",
		"read_only": 1,
		"no_copy": 1,
	},
	{
		"fieldname": "ke_walk_in_name",
		"fieldtype": "Data",
		"label": "Walk-in Name",
		"insert_after": "ke_patient_visit",
		"read_only": 1,
		"depends_on": "ke_walk_in_name",
	},
]

DELIVERY_NOTE_ITEM = [
	{
		"fieldname": "ke_medication_request",
		"fieldtype": "Link",
		"label": "Medication Request",
		"options": "Medication Request",
		"insert_after": "against_sales_invoice",
		"read_only": 1,
	},
	{
		"fieldname": "ke_instructions",
		"fieldtype": "Small Text",
		"label": "Instructions (label)",
		"insert_after": "description",
	},
]

PHARMACY_SALE = [
	{
		"fieldname": "ke_pharmacy_sale",
		"fieldtype": "Check",
		"label": "Pharmacy Counter Sale",
		"insert_after": "ke_patient_visit",
		"read_only": 1,
		"no_copy": 1,
	},
	{
		"fieldname": "ke_walk_in_name",
		"fieldtype": "Data",
		"label": "Walk-in Name",
		"insert_after": "ke_pharmacy_sale",
		"depends_on": "ke_pharmacy_sale",
	},
]

PHARMACY_SALE_ITEM = [
	{
		"fieldname": "ke_instructions",
		"fieldtype": "Small Text",
		"label": "Instructions (label)",
		"insert_after": "description",
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
			# its own section: Marley's Source section is hidden (forms.py)
			"insert_after": "ke_referral_section",
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
		"fieldname": "ke_target_tat_minutes",
		"fieldtype": "Int",
		"label": "Target Turnaround (minutes)",
		"insert_after": "observation_category",
		"description": "From order to report, for the Turnaround Time report. Blank = no target.",
	},
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
	{
		"fieldname": "ke_seen_at",
		"fieldtype": "Datetime",
		"label": "Seen by Clinician At",
		"insert_after": "ke_verified_by",
		"read_only": 1,
		"no_copy": 1,
	},
	{
		"fieldname": "ke_seen_by",
		"fieldtype": "Link",
		"label": "Seen by Clinician",
		"options": "User",
		"insert_after": "ke_seen_at",
		"read_only": 1,
		"no_copy": 1,
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
		MEDICATION_REQUEST,
		PAYMENT_ENTRY,
		LAB_TEST,
		SERVICE_REQUEST,
		DELIVERY_NOTE,
		DELIVERY_NOTE_ITEM,
		PHARMACY_SALE,
		PHARMACY_SALE_ITEM,
		LAB_TEST_TEMPLATE,
		PRACTITIONER,
		THERAPY_SESSION,
		MEDICATION,
		CLAIM_COVERAGE,
		OPERATION_NOTE,
		IMAGING_TEMPLATE,
		IMAGING_OBSERVATION,
		USER,
		MEDICATION_DISPENSING,
		DRUG_PRESCRIPTION,
		MEDICATION_REQUEST_DOSE,
		ENCOUNTER_DIAGNOSIS,
		SERVICE_REQUEST_ROUTING,
		COUNTER_PRESCRIPTION,
		COUNTER_PRESCRIPTION_ITEM,
		INPATIENT_RECORD,
		INSURANCE_PAYOR,
		CLINICAL_NOTE,
		INPATIENT_DISPOSITION,
		*MOH.values(),
	):
		for field in fields:
			field.setdefault("module", MODULE)
	fields = {
		"Patient": PATIENT,
		"Vital Signs": VITAL_SIGNS,
		"Therapy Session": THERAPY_SESSION,
		"Medication": MEDICATION,
		"Patient Insurance Policy": INSURANCE_POLICY,
		"Healthcare Practitioner": PRACTITIONER,
		"Insurance Claim Coverage": CLAIM_COVERAGE,
		"Clinical Procedure": OPERATION_NOTE,
		"Observation Template": IMAGING_TEMPLATE,
		"Observation": IMAGING_OBSERVATION,
		"Item Group": ITEM_GROUP,
		"Sales Invoice Item": INVOICE_ITEM,
		"Sales Invoice": SALES_INVOICE,
		"Medication Request": MEDICATION_REQUEST,
		"Payment Entry": PAYMENT_ENTRY,
		"Lab Test": LAB_TEST,
		"Service Request": SERVICE_REQUEST,
		"Delivery Note": DELIVERY_NOTE,
		"Delivery Note Item": DELIVERY_NOTE_ITEM,
		"Lab Test Template": LAB_TEST_TEMPLATE,
		"Healthcare Service Unit": SERVICE_UNIT,
		"User": USER,
	}
	# MOH has its own Patient Encounter fields: combine, don't replace.
	for doctype, extra in MOH.items():
		fields[doctype] = [*fields.get(doctype, []), *extra]
	fields["Patient Encounter"] = [*fields.get("Patient Encounter", []), *ENCOUNTER]
	fields["Sales Invoice"] = [*fields["Sales Invoice"], *PHARMACY_SALE]
	fields["Sales Invoice Item"] = [
		*fields["Sales Invoice Item"],
		*PHARMACY_SALE_ITEM,
		*COUNTER_PRESCRIPTION_ITEM,
	]
	fields["Sales Invoice"] = [*fields["Sales Invoice"], *COUNTER_PRESCRIPTION]
	fields["Medication"] = [*fields["Medication"], *MEDICATION_DISPENSING]
	fields["Medication Request"] = [*fields["Medication Request"], *MEDICATION_REQUEST_DOSE]
	fields["Service Request"] = [*fields["Service Request"], *SERVICE_REQUEST_ROUTING]
	fields["Drug Prescription"] = DRUG_PRESCRIPTION
	fields["Patient Encounter Diagnosis"] = ENCOUNTER_DIAGNOSIS
	fields["Inpatient Record"] = [*fields.get("Inpatient Record", []), *INPATIENT_RECORD]
	fields["Insurance Payor"] = INSURANCE_PAYOR
	fields["Clinical Note"] = CLINICAL_NOTE
	fields["Inpatient Record"] = [*fields["Inpatient Record"], *INPATIENT_DISPOSITION]
	create_custom_fields(fields, update=True)
