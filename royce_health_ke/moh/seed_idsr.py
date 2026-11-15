# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Default notifiable diseases for Integrated Disease Surveillance and Response
(IDSR). The list and categories follow WHO AFRO's IDSR Technical Guidelines
(3rd edition), which Kenya's IDSR guidelines adapt; the IHR flags follow
Annex 2 of the International Health Regulations (2005).

REVIEW WITH THE COUNTY DISEASE SURVEILLANCE OFFICER before relying on the
alerts: the county decides which diseases are immediately reportable, the
outbreak thresholds and the case definitions. Every row is the hospital's to
edit once created (ADR-023).

Codes: ICD-10 prefixes, plus ICD-11 codes checked against the WHO ICD-11 MMS
2026-01 release. A diagnosis matches a disease when one of its codes starts
with a prefix here (or the Diagnosis record is linked to the disease directly).
Events that are not a diagnosis (maternal and neonatal deaths, adverse events
following immunisation, clusters of unexplained illness) are recorded as
Public Health Events instead.

Threshold: `alert` cases within `days` days raise an outbreak alert (a Public
Health Event). Immediately reportable diseases alert on every case anyway;
0 means no automatic outbreak alert (set the county's own threshold)."""

IMMEDIATE = "Immediately Reportable"
WEEKLY = "Weekly Reportable"

# (name, category, IHR, alert, days, ICD-10 prefixes, ICD-11 prefixes)
DISEASES = [
	("Acute Flaccid Paralysis (Polio)", IMMEDIATE, 1, 1, 7, ["A80"], ["1C81"]),
	("Anthrax", IMMEDIATE, 0, 1, 7, ["A22"], ["1B97"]),
	("Chikungunya", IMMEDIATE, 0, 1, 7, ["A92.0"], ["1D40"]),
	("Cholera", IMMEDIATE, 1, 1, 7, ["A00"], ["1A00"]),
	("COVID-19", IMMEDIATE, 0, 1, 7, ["U07.1", "U07.2"], ["RA01"]),
	("Dengue Fever", IMMEDIATE, 0, 1, 7, ["A90", "A91", "A97"], ["1D20", "1D21", "1D22", "1D2Z"]),
	("Dysentery (Bloody Diarrhoea)", IMMEDIATE, 0, 1, 7, ["A03", "A06.0"], ["1A02"]),
	("Guinea Worm (Dracunculiasis)", IMMEDIATE, 0, 1, 7, ["B72"], ["1F64"]),
	("Measles", IMMEDIATE, 0, 1, 7, ["B05"], ["1F03"]),
	("Meningococcal Meningitis", IMMEDIATE, 0, 1, 7, ["A39"], ["1C1C"]),
	("Middle East Respiratory Syndrome (MERS)", IMMEDIATE, 1, 1, 7, [], ["1D64"]),
	("Mpox", IMMEDIATE, 0, 1, 7, ["B04"], ["1E71"]),
	("Neonatal Tetanus", IMMEDIATE, 0, 1, 7, ["A33"], ["1C15"]),
	("New Subtype Human Influenza", IMMEDIATE, 1, 1, 7, ["J09"], ["1E31"]),
	("Plague", IMMEDIATE, 1, 1, 7, ["A20"], ["1B93"]),
	("Rabies", IMMEDIATE, 0, 1, 7, ["A82"], ["1C82"]),
	("Rift Valley Fever", IMMEDIATE, 0, 1, 7, ["A92.4"], ["1D44"]),
	("SARS", IMMEDIATE, 1, 1, 7, ["U04"], ["1D65"]),
	("Smallpox", IMMEDIATE, 1, 1, 7, ["B03"], ["1E70"]),
	(
		"Viral Haemorrhagic Fever (Ebola, Marburg, Lassa, CCHF)",
		IMMEDIATE,
		1,
		1,
		7,
		["A98", "A96.2", "A99"],
		["1D60", "1D61.2", "1D49", "1D86"],
	),
	("Yellow Fever", IMMEDIATE, 1, 1, 7, ["A95"], ["1D47"]),
	("Zika Virus Disease", IMMEDIATE, 0, 1, 7, ["A92.5", "U06"], ["1D48"]),
	(
		"Malaria",
		WEEKLY,
		0,
		0,
		7,
		["B50", "B51", "B52", "B53", "B54"],
		["1F40", "1F41", "1F42", "1F43", "1F44", "1F45", "1F4Z"],
	),
	("Typhoid Fever", WEEKLY, 0, 5, 7, ["A01.0"], ["1A07"]),
	("Brucellosis", WEEKLY, 0, 0, 7, ["A23"], ["1B95"]),
	("Visceral Leishmaniasis (Kala-azar)", WEEKLY, 0, 0, 7, ["B55.0"], ["1F54.0"]),
	("Trypanosomiasis", WEEKLY, 0, 0, 7, ["B56"], ["1F51"]),
]


def rows():
	"""(disease, category, ihr, alert, days, [(code_system, prefix)])"""
	for name, category, ihr, alert, days, icd10, icd11 in DISEASES:
		codes = [("ICD-10", p) for p in icd10] + [("ICD-11", p) for p in icd11]
		yield name, category, ihr, alert, days, codes
