# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Diagnoses made before ICD-11 was loaded get the code whose title is the
same name (Bethesda, 21 Nov 2026: a ward diagnosis showed no code). The ward
now refuses a diagnosis without a code (inpatient.add_diagnosis)."""

from royce_health_ke import diagnosis


def execute():
	diagnosis.code_uncoded_by_title()
