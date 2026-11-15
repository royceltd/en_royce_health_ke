# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Default clinical alert rules: a starting set, each tied to a published
guideline. REVIEW WITH THE HOSPITAL'S CLINICIANS (medical superintendent /
pharmacy and therapeutics committee) before relying on them: thresholds,
wording and which ones are on are theirs to decide, and every rule is the
hospital's to edit once created (ADR-023).

Each rule: (name, severity, sex, min age, under age, recommendation, source,
[(condition, {fields})])."""

ANY = "Any"

RULES = [
	(
		"Fever in a child under 5",
		"Warning",
		ANY,
		None,
		5,
		"Test for malaria (mRDT or microscopy) before giving antimalarials; look for danger signs and other causes of fever.",
		"Kenya National Guidelines for the Diagnosis, Treatment and Prevention of Malaria; WHO IMCI",
		[("Vital Sign", {"vital_sign": "temperature", "operator": ">=", "value": 37.5})],
	),
	(
		"Low oxygen saturation",
		"Critical",
		ANY,
		None,
		None,
		"SpO2 below 90%: give oxygen to keep SpO2 at 90% or above and assess for respiratory distress and shock.",
		"WHO Emergency Triage Assessment and Treatment (ETAT); WHO oxygen therapy for children",
		[("Vital Sign", {"vital_sign": "ke_spo2", "operator": "<", "value": 90})],
	),
	(
		"Raised blood pressure (systolic)",
		"Warning",
		ANY,
		18,
		None,
		"Systolic BP 140 or above: repeat after 5 minutes' rest. If raised on two visits, diagnose hypertension, "
		"assess cardiovascular risk and start lifestyle advice and treatment as per guideline.",
		"Kenya National Guidelines for Cardiovascular Diseases Management; WHO HEARTS",
		[("Vital Sign", {"vital_sign": "bp_systolic", "operator": ">=", "value": 140})],
	),
	(
		"Raised blood pressure (diastolic)",
		"Warning",
		ANY,
		18,
		None,
		"Diastolic BP 90 or above: repeat after 5 minutes' rest. If raised on two visits, diagnose hypertension, "
		"assess cardiovascular risk and start lifestyle advice and treatment as per guideline.",
		"Kenya National Guidelines for Cardiovascular Diseases Management; WHO HEARTS",
		[("Vital Sign", {"vital_sign": "bp_diastolic", "operator": ">=", "value": 90})],
	),
	(
		"Severe acute malnutrition",
		"Critical",
		ANY,
		None,
		5,
		"Weight-for-length/height below -3 SD: check appetite, oedema and medical complications; admit for "
		"inpatient care if complicated, otherwise enrol in the Outpatient Therapeutic Programme (OTP).",
		"Kenya Guidelines for Integrated Management of Acute Malnutrition (IMAM); WHO",
		[("Vital Sign", {"vital_sign": "ke_wflh_z", "operator": "<", "value": -3, "look_back_days": 1})],
	),
	(
		"Severe anaemia",
		"Critical",
		ANY,
		None,
		None,
		"Haemoglobin below 7 g/dL: assess for signs of decompensation and need for transfusion; find and treat the cause. "
		"(Check the lab reports haemoglobin in g/dL.)",
		"WHO haemoglobin concentrations for the diagnosis of anaemia; Kenya clinical guidelines",
		[
			(
				"Lab Result",
				{"lab_result_name": "haemoglobin", "operator": "<", "value": 7, "look_back_days": 7},
			)
		],
	),
	(
		"Diabetes: routine care",
		"Info",
		ANY,
		18,
		None,
		"Patient has diabetes: HbA1c every 3 months, blood pressure and foot check at every visit, yearly eye "
		"examination and kidney function (creatinine, urine protein).",
		"Kenya National Clinical Guidelines for the Management of Diabetes",
		[
			(
				"Diagnosis",
				{
					"code_prefix": "E10, E11, E12, E13, E14, 5A10, 5A11, 5A12, 5A13, 5A14",
					"look_back_days": 3650,
				},
			)
		],
	),
	(
		"Penicillin allergy: penicillin prescribed",
		"Critical",
		ANY,
		None,
		None,
		"The patient is recorded as allergic to penicillin and a penicillin is being prescribed. Choose a non-penicillin "
		"antibiotic unless the allergy has been ruled out.",
		"WHO Model Formulary; Kenya Essential Medicines List",
		[
			("Allergy", {"text": "penicillin"}),
			(
				"Medication",
				{
					"text": "amoxicillin, ampicillin, amoxiclav, augmentin, co-amoxiclav, cloxacillin, flucloxacillin, "
					"benzylpenicillin, benzathine, phenoxymethylpenicillin, piperacillin"
				},
			),
		],
	),
	(
		"Check immunisation status (under 5)",
		"Info",
		ANY,
		None,
		5,
		"Check the child's immunisation and vitamin A status in the Mother and Child Health booklet; give or refer for "
		"any missed vaccines.",
		"Kenya Expanded Programme on Immunization (KEPI) schedule",
		[],
	),
]


def rows():
	for name, severity, sex, min_age, max_age, recommendation, source, conditions in RULES:
		yield {
			"rule_name": name,
			"severity": severity,
			"sex": sex,
			"min_age_years": min_age,
			"max_age_years": max_age,
			"recommendation": recommendation,
			"evidence_source": source,
			"conditions": [{"condition": kind, **fields} for kind, fields in conditions],
		}
