# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Default quality measures: a starting set built on data the hospital
already records. The hospital's quality improvement committee sets which
measures to track and the targets; every measure is the hospital's to edit
once created (ADR-023). Targets here are placeholders to review."""

DIABETES = "E10, E11, E12, E13, E14, 5A10, 5A11, 5A12, 5A13, 5A14"
HYPERTENSION = "I10, I11, I12, I13, I15, BA00, BA01, BA02, BA03, BA04"
MALARIA = "B50, B51, B52, B53, B54, 1F40, 1F41, 1F42, 1F43, 1F44, 1F45, 1F4Z"

MEASURES = [
	{
		"measure_code": "QM-HTN-BP",
		"measure_name": "Hypertension: blood pressure recorded at the consultation",
		"domain": "Clinical Process",
		"method": "Vital Recorded at Consultation",
		"diagnosis_prefixes": HYPERTENSION,
		"min_age_years": 18,
		"vital_sign": "bp_systolic",
		"target_percent": 95,
		"description": "Numerator: consultations of adults with hypertension where BP was recorded that day. "
		"Denominator: consultations of adults with a hypertension diagnosis.",
	},
	{
		"measure_code": "QM-U5-WEIGHT",
		"measure_name": "Children under 5 weighed at the consultation",
		"domain": "Maternal and Child Health",
		"method": "Vital Recorded at Consultation",
		"max_age_years": 5,
		"vital_sign": "weight",
		"target_percent": 90,
		"description": "Numerator: consultations of children under 5 with a weight recorded that day. "
		"Denominator: consultations of children under 5.",
	},
	{
		"measure_code": "QM-DM-HBA1C",
		"measure_name": "Diabetes: HbA1c in the last 6 months",
		"domain": "Clinical Process",
		"method": "Lab Result for Diagnosis",
		"diagnosis_prefixes": DIABETES,
		"min_age_years": 18,
		"lab_result_names": "hba1c, glycated, glycosylated",
		"look_back_days": 182,
		"target_percent": 70,
		"description": "Numerator: adults with diabetes seen in the period with an HbA1c result in the 6 months "
		"before their last visit. Denominator: adults with diabetes seen in the period.",
	},
	{
		"measure_code": "QM-MAL-TEST",
		"measure_name": "Malaria cases confirmed by a test",
		"domain": "Clinical Process",
		"method": "Lab Result for Diagnosis",
		"diagnosis_prefixes": MALARIA,
		"lab_result_names": "malaria, mps, bs for, rdt, plasmodium",
		"look_back_days": 3,
		"target_percent": 100,
		"description": "Numerator: patients diagnosed with malaria who had a malaria test (mRDT or microscopy) in "
		"the 3 days before. Denominator: patients diagnosed with malaria.",
	},
	{
		"measure_code": "QM-LAB-TAT",
		"measure_name": "Lab results within 2 hours of the order",
		"domain": "Service Efficiency",
		"method": "Lab Turnaround Within Target",
		"target_minutes": 120,
		"target_percent": 80,
		"description": "Numerator: lab tests resulted within 120 minutes of the order. Denominator: lab tests resulted.",
	},
	{
		"measure_code": "QM-CDS-ANSWERED",
		"measure_name": "Clinical alerts answered by the clinician",
		"domain": "Patient Safety",
		"method": "Clinical Alerts Answered",
		"target_percent": 90,
		"description": "Numerator: clinical alerts marked acted on or overridden. Denominator: clinical alerts shown.",
	},
	{
		"measure_code": "QM-IP-DEATHS",
		"measure_name": "Inpatient deaths",
		"domain": "Clinical Outcome",
		"method": "Inpatient Deaths",
		"higher_is_better": 0,
		"target_percent": 3,
		"description": "Numerator: inpatients who died. Denominator: inpatients discharged (all outcomes). Lower is better.",
	},
	{
		"measure_code": "QM-ANC4",
		"measure_name": "Deliveries with 4 or more ANC contacts",
		"domain": "Maternal and Child Health",
		"method": "Deliveries with 4+ ANC Contacts",
		"target_percent": 80,
		"description": "Numerator: women delivering in the period who had 4 or more ANC contacts here. "
		"Denominator: deliveries in the period.",
	},
	{
		"measure_code": "QM-CLIENT-SAT",
		"measure_name": "Clients satisfied with the service (exit survey)",
		"domain": "Service Efficiency",
		"method": "Entered or Imported",
		"target_percent": 85,
		"description": "Numerator: exit-interview respondents satisfied. Denominator: respondents. Typed in or imported "
		"each period from the client satisfaction survey.",
	},
]
