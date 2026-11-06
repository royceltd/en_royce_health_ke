# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Kenyan reference lists used across the app."""

# The 47 counties in their official code order (001 Mombasa ... 047 Nairobi).
COUNTIES = (
	"Mombasa",
	"Kwale",
	"Kilifi",
	"Tana River",
	"Lamu",
	"Taita Taveta",
	"Garissa",
	"Wajir",
	"Mandera",
	"Marsabit",
	"Isiolo",
	"Meru",
	"Tharaka Nithi",
	"Embu",
	"Kitui",
	"Machakos",
	"Makueni",
	"Nyandarua",
	"Nyeri",
	"Kirinyaga",
	"Murang'a",
	"Kiambu",
	"Turkana",
	"West Pokot",
	"Samburu",
	"Trans Nzoia",
	"Uasin Gishu",
	"Elgeyo Marakwet",
	"Nandi",
	"Baringo",
	"Laikipia",
	"Nakuru",
	"Narok",
	"Kajiado",
	"Kericho",
	"Bomet",
	"Kakamega",
	"Vihiga",
	"Bungoma",
	"Busia",
	"Siaya",
	"Kisumu",
	"Homa Bay",
	"Migori",
	"Kisii",
	"Nyamira",
	"Nairobi",
)

ID_TYPES = (
	"National ID",
	"Maisha Namba",
	"Birth Certificate",
	"Passport",
	"Alien ID",
	"Refugee ID",
	"None",
)

NEXT_OF_KIN_RELATIONSHIPS = (
	"Spouse",
	"Parent",
	"Child",
	"Sibling",
	"Guardian",
	"Relative",
	"Friend",
	"Other",
)

CADRES = (
	"Medical Officer",
	"Specialist",
	"Clinical Officer",
	"Nurse",
	"Midwife",
	"Pharmacist",
	"Pharmaceutical Technologist",
	"Laboratory Technologist",
	"Radiographer",
	"Dentist",
	"Nutritionist",
	"Physiotherapist",
	"Other",
)

# Regulator for each cadre: KMPDC (doctors, dentists), NCK (nurses, midwives),
# COC (clinical officers), PPB (pharmacy), KMLTTB (laboratory).
REGULATORS = ("KMPDC", "NCK", "COC", "PPB", "KMLTTB", "Other")

KEPH_LEVELS = ("Level 2", "Level 3", "Level 4", "Level 5", "Level 6")
OWNERSHIP = ("Private", "Faith-based", "NGO", "Public")


def select(options, blank=True):
	return ("\n" if blank else "") + "\n".join(options)
