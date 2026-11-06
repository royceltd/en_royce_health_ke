# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Default MOH 705A/705B rows. Labels and order follow the MOH 705 summary
sheets as implemented in KenyaEMR (palladiumkenya/openmrs-module-kenyaemr,
MPL 2.0, read as a specification only). The ICD-10 mappings are Royce's own
first pass - REVIEW WITH THE HOSPITAL'S HEALTH RECORDS OFFICER before
relying on the report. Rows that can't be told apart from a code alone
(e.g. diarrhoea by dehydration, severe vs non-severe pneumonia) have no
codes: map them to the hospital's own Diagnosis records instead.

Matching: a diagnosis counts toward the row with the longest matching code
prefix, so 'F84' (autism) beats 'F' (mental disorders)."""


def rng(start, end):
	"""ICD-10 three-character range, e.g. rng("J12", "J18") -> J12..J18."""
	letter = start[0]
	return [f"{letter}{n:02d}" for n in range(int(start[1:]), int(end[1:]) + 1)]


# kind: Diagnosis (default), Lab Test, First Attendance, Re-Attendance,
# Referral In, Referral Out, All Other Diseases
DIAG = "Diagnosis"

FORM_A = [
	("DWND", "Diarrhoea with no dehydration", []),
	("DWSOD", "Diarrhoea with some dehydration", []),
	("DWSED", "Diarrhoea with severe dehydration", []),
	("CLC", "Cholera", ["A00"]),
	("DYC", "Dysentery", ["A03", "A06.0"]),
	("GAS", "Gastroenteritis", ["A08", "A09"]),
	("PNC", "Pneumonia", rng("J12", "J18")),
	("SP", "Severe pneumonia", []),
	("URC", "Upper Respiratory Tract Infections", ["J00", "J01", "J02", "J04", "J05", "J06"]),
	("LTI", "Lower Respiratory Tract Infections", ["J20", "J21", "J22"]),
	("ASC", "Asthma", ["J45", "J46"]),
	("TCP", "Presumed Tuberculosis", []),
	("SMC", "Suspected Malaria", ["B54"]),
	("TMC", "Tested Malaria", [], "Lab Test", ["LOINC:32700-7"]),
	("CMC", "Confirmed Malaria", ["B50", "B51", "B52", "B53"]),
	("EIC", "Ear Infections Conditions", ["H60", "H65", "H66"]),
	("MNC", "Malnutrition", rng("E40", "E46")),
	("ANC", "Anaemia", rng("D50", "D64")),
	("MCC", "Meningococcal Meningitis", ["A39"]),
	("OMC", "Other Meningitis", ["G00", "G01", "G02", "G03"]),
	("NS", "Neonatal Sepsis", ["P36"]),
	("NNC", "Neonatal Tetanus", ["A33"]),
	("PMC", "Poliomyelitis", ["A80"]),
	("CPC", "Chicken Pox", ["B01"]),
	("MSC", "Measles", ["B05"]),
	("HPC", "Hepatitis", rng("B15", "B19")),
	("AM", "Amoebiasis", ["A06"]),
	("MPC", "Mumps", ["B26"]),
	("TYC", "Typhoid Fever", ["A01"]),
	("BLC", "Bilharzia", ["B65"]),
	("IWC", "Intestinal worms", rng("B76", "B83")),
	("EC", "Eye Infections", ["H10"]),
	("TSC", "Tonsillitis", ["J03"]),
	("UTC", "Urinary Tract Infection", ["N10", "N30", "N39.0"]),
	("MDC", "Mental Disorders", ["F"]),
	("DDC", "Dental Disorders", rng("K00", "K14")),
	("JIC", "Jiggers Infestation", ["B88.1"]),
	("DOC", "Diseases of the Skin", ["L"]),
	("DS", "Down's syndrome", ["Q90"]),
	("PC", "Poisoning", rng("T36", "T65")),
	("RTC", "Road Traffic Injuries", []),
	("DRTC", "Deaths due to Road Traffic Injuries", []),
	("VRC", "Violence related injuries", []),
	("OIC", "Other Injuries", ["S", "T0", "T1"]),
	("SAC", "Sexual Assault", ["T74.2"]),
	("BC", "Burns", rng("T20", "T32")),
	("SBC", "Snake Bites", ["T63.0"]),
	("DBC", "Dog Bites", ["W54"]),
	("OBC", "Other Bites", []),
	("DTC", "Diabetes", rng("E10", "E14")),
	("EPC", "Epilepsy", ["G40", "G41"]),
	("OCDC", "Other Convulsive Disorders", ["R56"]),
	("RF", "Rheumatic Fever", ["I00", "I01", "I02"]),
	("BRC", "Brucellosis", ["A23"]),
	("RKC", "Rickets", ["E55.0"]),
	("CRPC", "Cerebral Palsy", ["G80"]),
	("ATC", "Autism", ["F84.0"]),
	("TRC", "Trypanosomiasis", ["B56"]),
	("YFC", "Yellow Fever", ["A95"]),
	("VHC", "Viral Haemorrhagic Fever", ["A96", "A98", "A99"]),
	("RVF", "Rift Valley Fever", ["A92.4"]),
	("CKU", "Chikungunya fever", ["A92.0"]),
	("DENF", "Dengue fever", ["A90", "A91", "A97"]),
	("KLC", "Kala-azar (Leishmaniasis)", ["B55.0"]),
	("CL", "Cutaneous Leishmaniasis", ["B55.1"]),
	("ANT", "Suspected Anthrax", ["A22"]),
	("SCC", "Suspected Childhood Cancers", ["C"]),
	("HYPO", "Hypoxaemia (SpO2 < 90%)", ["R09.0"]),
	("TC", "Tuberculosis", rng("A15", "A19")),
	("OVC", "Overweight", ["E66"]),
	("AODC", "All other diseases", [], "All Other Diseases"),
	("NFAC", "No. of First Attendances", [], "First Attendance"),
	("RAC", "Re-Attendances", [], "Re-Attendance"),
	("RFHC", "Referrals from other health facility", [], "Referral In"),
	("RFCC", "Referrals to other health facility", [], "Referral Out"),
]

FORM_B = [
	("DA", "Diarrhoea", ["A08", "A09"]),
	("TBA", "Tuberculosis", rng("A15", "A19")),
	("DYA", "Dysentery", ["A03", "A06.0"]),
	("CLA", "Cholera", ["A00"]),
	("MMA", "Meningococcal Meningitis", ["A39"]),
	("MOA", "Other Meningitis", ["G00", "G01", "G02", "G03"]),
	("NTA", "Tetanus", ["A33", "A34", "A35"]),
	("PMA", "Poliomyelitis", ["A80"]),
	("CPA", "Chicken Pox", ["B01"]),
	("MEA", "Measles", ["B05"]),
	("HEA", "Hepatitis", rng("B15", "B19")),
	("MPSA", "Mumps", ["B26"]),
	("TMA", "Tested Malaria", [], "Lab Test", ["LOINC:32700-7"]),
	("SUA", "Suspected malaria", ["B54"]),
	("COA", "Confirmed Malaria positive", ["B50", "B51", "B52", "B53"]),
	("MPA", "Malaria in Pregnancy", ["O98.6"]),
	("AMA", "Amoebiasis", ["A06"]),
	("TYA", "Typhoid Fever", ["A01"]),
	("STIA", "STI", rng("A50", "A64")),
	("URA", "Urinary tract infection", ["N10", "N30", "N39.0"]),
	("BIA", "Bilharzia", ["B65"]),
	("INA", "Intestinal worms", rng("B76", "B83")),
	("MLA", "Malnutrition", rng("E40", "E46")),
	("ANEA", "Anaemia", rng("D50", "D64")),
	("EYA", "Eye Infections", ["H10"]),
	("EIA", "Ear Infection Conditions", ["H60", "H65", "H66"]),
	("UPA", "Upper Respiratory Tract Infections", ["J00", "J01", "J02", "J03", "J04", "J05", "J06"]),
	("ASA", "Asthma", ["J45", "J46"]),
	("PNA", "Pneumonia", rng("J12", "J18")),
	("OTRA", "Other Diseases of Respiratory System", ["J"]),
	("ABA", "Abortion", rng("O00", "O08")),
	("DPA", "Diseases of Puerperium & Childbirth", rng("O85", "O92")),
	("HYA", "Hypertension", rng("I10", "I15")),
	("MDA", "Mental Disorders", ["F"]),
	("DEA", "Dental Disorders", rng("K00", "K14")),
	("JIA", "Jiggers Infestation", ["B88.1"]),
	("DSA", "Diseases of the Skin", ["L"]),
	("AJPA", "Arthritis, Joint Pains", [*rng("M05", "M19"), "M25.5"]),
	("POA", "Poisoning", rng("T36", "T65")),
	("ROA", "Road Traffic Injuries", []),
	("DRA", "Deaths due to road traffic injuries", []),
	("OIA", "Other Injuries", ["S", "T0", "T1"]),
	("SEA", "Sexual Assault", ["T74.2"]),
	("VRA", "Violence Related Injuries", []),
	("BUA", "Burns", rng("T20", "T32")),
	("SNA", "Snake Bites", ["T63.0"]),
	("DOA", "Dog Bites", ["W54"]),
	("OBA", "Other Bites", []),
	("DTA", "Diabetes", rng("E10", "E14")),
	("EPA", "Epilepsy", ["G40", "G41"]),
	("BRLA", "Brucellosis", ["A23"]),
	("CAA", "Cardiovascular Conditions", ["I"]),
	("CNSA", "Central Nervous System Conditions", ["G"]),
	("OVA", "Overweight", ["E66"]),
	("PHA", "Physical Disability", []),
	("TRA", "Trypanosomiasis", ["B56"]),
	("RVFA", "Rift Valley Fever", ["A92.4"]),
	("YEA", "Yellow Fever", ["A95"]),
	("VHA", "Viral Haemorrhagic Fever", ["A96", "A98", "A99"]),
	("CKUA", "Chikungunya fever", ["A92.0"]),
	("DENA", "Dengue fever", ["A90", "A91", "A97"]),
	("KAA", "Kala-azar (Leishmaniasis)", ["B55.0"]),
	("CLA2", "Cutaneous Leishmaniasis", ["B55.1"]),
	("ANTA", "Suspected Anthrax", ["A22"]),
	("MSA", "Musculoskeletal Conditions", ["M"]),
	("FIA", "Fistula (Birth Related)", ["N82"]),
	("NSA", "Neoplasms", ["C", "D0", "D1", "D2", "D3", "D4"]),
	("AODA", "All other diseases", [], "All Other Diseases"),
	("NFAA", "No. of First Attendances", [], "First Attendance"),
	("RETA", "Re-Attendances", [], "Re-Attendance"),
	("RFHA", "Referrals from other health facility", [], "Referral In"),
	("RFCA", "Referrals to other health facility", [], "Referral Out"),
]


def rows():
	"""(form, sequence, code, label, kind, [(code_system, prefix)])"""
	for form, spec in (("705A", FORM_A), ("705B", FORM_B)):
		for seq, row in enumerate(spec, start=1):
			code, label, icd10 = row[0], row[1], row[2]
			kind = row[3] if len(row) > 3 else DIAG
			extra = row[4] if len(row) > 4 else []
			codes = [("ICD-10", p) for p in icd10] + [tuple(e.split(":", 1)) for e in extra]
			yield form, seq, code, label, kind, codes
