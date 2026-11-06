# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""MOH 711 monthly integrated summary: reproductive health (ANC, maternity,
PNC, family planning) and the sections the hospital doesn't capture yet.

Indicator names and definitions follow MOH 711 as implemented in KenyaEMR
(Moh711ReportBuilder). Where KenyaEMR splits a row by the mother's age, the
report does too (10-14, 15-19, 20-24, 25+), on her age at the visit or
delivery. Sections whose data isn't captured yet are listed with no value, so
the report shows exactly what still has to be filled in by hand.

- ANC: submitted ANC Visits in the month. New = contact 1. "Completed 4 / 8
  visits" = the 4th / 8th contact happened in the month. Syphilis testing
  comes from the booking screening on Pregnancy Records booked in the month.
- Maternity: submitted Delivery Records delivered in the month, and their
  babies. Perinatal / neonatal deaths: babies who died within 7 / 28 days of
  birth (Date of Death on the baby row).
- PNC: submitted PNC Visits in the month, by the MOH timing bucket.
- Family planning: submitted Family Planning Visits in the month."""

from collections import Counter

import frappe
from frappe.utils import get_datetime, getdate

from royce_health_ke.family_planning import LARC
from royce_health_ke.moh.moh705 import age_on, period

AGE_BANDS = ("10-14", "15-19", "20-24", "25+")
LOW_BIRTH_WEIGHT_G = 2500
PRETERM_WEEKS = 37
NOT_CAPTURED = "Not captured yet"

MODES = (
	("Spontaneous vaginal delivery", "Normal Deliveries"),
	("Caesarean section", "Caesarean Sections"),
	("Breech delivery", "Breech Delivery"),
	("Assisted vaginal delivery", "Assisted Vaginal Deliveries (Vacuum Extraction)"),
)
COMPLICATIONS = (
	("aph", "Ante Partum Haemorrhage (APH)"),
	("pph", "Post Partum Haemorrhage (PPH)"),
	("eclampsia", "Eclampsia"),
	("ruptured_uterus", "Ruptured Uterus"),
	("obstructed_labour", "Obstructed Labour"),
	("sepsis", "Sepsis"),
)
PNC_TIMINGS = (
	("Within 48 hours", "within 48 hrs"),
	("3 days to under 6 weeks", "between 3 days and 6 weeks"),
	("6 weeks and after", "after 6 weeks"),
)
POSTPARTUM_FP = ("Immediate postpartum (within 48 hours)", "Postpartum (3 days to 6 weeks)")
FP_BY_VISIT_TYPE = (
	("Progestin only pills", "Progestin only pills"),
	("Combined oral contraceptive pills", "Combined Oral Contraceptive pills"),
	("DMPA-IM", "DMPA-IM"),
	("DMPA-SC", "DMPA-SC"),
	("Male condoms", "Received Male condoms"),
	("Female condoms", "Received Female condoms"),
	("Male and female condoms", "Received Male and Female condoms"),
)
FP_INSERTIONS = (
	("Implant (1 rod)", "Implant 1 Rod"),
	("Implant (2 rods)", "Implant 2 Rods"),
	("Hormonal IUCD", "Hormonal IUCD"),
	("Non-hormonal IUCD", "Non hormonal IUCD"),
)

# Sections the hospital doesn't record yet: listed so the HRIO fills them in.
NOT_CAPTURED_SECTIONS = {
	"Cervical Cancer Screening": (
		"Clients receiving VIA / VILI / HPV",
		"Screened for Pap smear",
		"Screened for HPV test",
		"Positive VIA / VILI result",
		"Positive Pap smear result",
		"Positive HPV result",
		"Suspicious cancer lesions",
		"Treated using Cryotherapy",
		"Treated using LEEP",
		"HIV positive clients screened",
		"Women screened for breast cancer",
		"Screened for colorectal cancer",
	),
	"Child Health and Nutrition": (
		"Normal weight for age",
		"Underweight",
		"Severely underweight",
		"Overweight",
		"Obese",
		"Total weighed",
		"MUAC normal (green)",
		"MUAC moderate (yellow)",
		"MUAC severe (red)",
		"Stunted",
		"Total measured",
		"New enrolment (malnutrition)",
		"Follow-up: Kwashiorkor",
		"Follow-up: Marasmus",
		"Exclusive breastfeeding",
		"Dewormed",
		"MNPs supplementation",
		"Child mortality",
		"Children with disability (any form)",
		"Children with delayed developmental milestones",
		"LLINs distributed to under 1 year",
	),
	"Sexual and Gender Based Violence": (
		"Total SGBV survivors",
		"Survivors presenting within 72 hrs",
		"Eligible survivors initiating PEP",
		"Eligible survivors completed PEP",
		"Survivors seroconverting 3 months after exposure",
		"Survivors eligible for ECP",
		"Eligible survivors who received ECP",
		"Rape or defilement survivors pregnant after 4 weeks",
		"RC or IPV clients seen",
		"SGBV survivors with disability",
	),
	"TB Screening": (
		"Total number of people screened",
		"Presumptive TB cases",
		"Already on TB treatment",
		"Not screened",
	),
	"Psychiatry": (
		"Psychosocial counselling",
		"Alcohol and drug abuse",
		"Bipolar disorder",
		"Depression",
		"Schizophrenia and psychotic disorder",
		"Psychosocial assessments and investigation",
		"Psychosocial rehabilitation",
		"Outreach services and health talks",
		"Psychiatric referrals",
	),
	"Physiotherapy": (
		"Neurological disorders (New / Revisit)",
		"Peripheral nerve disorders (New / Revisit)",
		"Post traumatic injuries (New / Revisit)",
		"Degenerative orthopaedic disorders (New / Revisit)",
		"Cardio-respiratory disorders (New / Revisit)",
		"Pre and post natal physiotherapy (New / Revisit)",
	),
}


def age_band(age):
	"""Mother's age band as on MOH 711; None below 10 or unknown."""
	if age is None or age < 10:
		return None
	if age < 15:
		return "10-14"
	if age < 20:
		return "15-19"
	if age < 25:
		return "20-24"
	return "25+"


class Sheet:
	def __init__(self):
		self.rows = []

	def section(self, title):
		self.rows.append({"indicator": title, "value": None, "is_section": 1})

	def add(self, indicator, value, note=None, bands=None):
		row = {"indicator": indicator, "value": value, "note": note}
		if bands is not None:
			for band in AGE_BANDS:
				row[band] = bands.get(band, 0)
		self.rows.append(row)


def compute(company, year, month):
	start, end = period(year, month)
	sheet = Sheet()
	_anc(company, start, end, sheet)
	_maternity(company, start, end, sheet)
	_pnc(company, start, end, sheet)
	_family_planning(company, start, end, sheet)
	for title, indicators in NOT_CAPTURED_SECTIONS.items():
		sheet.section(title)
		for indicator in indicators:
			sheet.add(indicator, None, NOT_CAPTURED)
	return sheet.rows


def _dobs(patients):
	return dict(
		frappe.get_all(
			"Patient", filters={"name": ["in", list(patients) or [""]]}, fields=["name", "dob"], as_list=True
		)
	)


def _bands(rows, dobs, date_field):
	return Counter(age_band(age_on(dobs.get(r.patient), getdate(r[date_field]))) for r in rows)


def _anc(company, start, end, sheet):
	visits = frappe.get_all(
		"ANC Visit",
		filters={"company": company, "docstatus": 1, "visit_date": ["between", [start, end]]},
		fields=[
			"patient",
			"pregnancy_record",
			"visit_date",
			"contact_number",
			"gestation_weeks",
			"ipt_dose",
			"haemoglobin",
			"iron_folate",
			"iron_folate_type",
			"itn_given",
			"breast_exam",
			"fgm_complications",
		],
	)
	dobs = _dobs({v.patient for v in visits})
	first = [v for v in visits if v.contact_number == 1]
	booking_hb = dict(
		frappe.get_all(
			"Pregnancy Record",
			filters={"name": ["in", [v.pregnancy_record for v in first] or [""]]},
			fields=["name", "haemoglobin"],
			as_list=True,
		)
	)
	pregnancies = frappe.get_all(
		"Pregnancy Record",
		filters={"company": company, "booking_date": ["between", [start, end]]},
		fields=["syphilis"],
	)

	def low_hb(v):
		hb = v.haemoglobin or (booking_hb.get(v.pregnancy_record) if v.contact_number == 1 else None)
		return bool(hb) and hb < 11

	def count(test):
		return sum(1 for v in visits if test(v))

	sheet.section("ANC / PMTCT")
	sheet.add("New ANC clients (1st ANC visit)", len(first), bands=_bands(first, dobs, "visit_date"))
	sheet.add("Revisiting ANC clients", count(lambda v: (v.contact_number or 0) > 1))
	for n, label in ((1, "1st"), (2, "2nd"), (3, "3rd")):
		sheet.add(f"Clients given IPT ({label} dose)", count(lambda v, n=n: v.ipt_dose == f"IPTp-SP {n}"))
	sheet.add("Clients with Hb less than 11 g/dl", len({v.patient for v in visits if low_hb(v)}))
	sheet.add(
		"Clients with 1st ANC contact within 12 weeks",
		sum(1 for v in first if v.gestation_weeks is not None and v.gestation_weeks <= 12),
	)
	sheet.add("Clients completed 4 antenatal visits", count(lambda v: v.contact_number == 4))
	sheet.add("Clients completed 8 antenatal visits", count(lambda v: v.contact_number == 8))
	sheet.add("LLINs distributed to ANC clients", count(lambda v: v.itn_given))
	sheet.add(
		"Clients tested for syphilis",
		sum(1 for p in pregnancies if p.syphilis in ("Non-reactive", "Reactive")),
		"Booking screening",
	)
	sheet.add("Clients tested positive for syphilis", sum(1 for p in pregnancies if p.syphilis == "Reactive"))
	sheet.add("Women done breast examination", count(lambda v: v.breast_exam))
	supplement = Counter(v.iron_folate_type or "Combined ferrous folate" for v in visits if v.iron_folate)
	sheet.add("Clients issued with iron", supplement["Iron only"])
	sheet.add("Clients issued with folic acid", supplement["Folic acid only"])
	sheet.add("Clients issued with combined ferrous folate", supplement["Combined ferrous folate"])
	sheet.add("Pregnant women presenting with FGM complications", count(lambda v: v.fgm_complications))


def _maternity(company, start, end, sheet):
	deliveries = frappe.get_all(
		"Delivery Record",
		filters={
			"company": company,
			"docstatus": 1,
			"delivery_datetime": ["between", [f"{start} 00:00:00", f"{end} 23:59:59"]],
		},
		fields=[
			"name",
			"patient",
			"pregnancy_record",
			"delivery_datetime",
			"place_of_delivery",
			"mode_of_delivery",
			"gestation_weeks",
			"uterotonic",
			"maternal_condition",
			"maternal_death_audited",
			*(field for field, _label in COMPLICATIONS),
		],
	)
	by_name = {d.name: d for d in deliveries}
	babies = frappe.get_all(
		"Delivery Newborn",
		filters={"parenttype": "Delivery Record", "parent": ["in", list(by_name) or [""]]},
		fields=[
			"parent",
			"outcome",
			"birth_weight_g",
			"deformity",
			"vitamin_k",
			"teo",
			"chlorhexidine",
			"kangaroo_care",
			"breastfeeding_1hr",
			"condition_at_discharge",
			"died_on",
		],
	)
	hiv = dict(
		frappe.get_all(
			"Pregnancy Record",
			filters={"name": ["in", [d.pregnancy_record for d in deliveries if d.pregnancy_record] or [""]]},
			fields=["name", "hiv_status"],
			as_list=True,
		)
	)
	live = [b for b in babies if b.outcome == "Live birth"]

	def days_lived(b):
		if not b.died_on:
			return None
		return (get_datetime(b.died_on) - get_datetime(by_name[b.parent].delivery_datetime)).days

	sheet.section("Maternity and Newborn")
	here = [d for d in deliveries if d.place_of_delivery != "Born before arrival"]
	modes = Counter(d.mode_of_delivery for d in here)
	for mode, label in MODES:
		sheet.add(label, modes[mode])
	uterotonic = Counter(d.uterotonic for d in here)
	sheet.add("Mothers given uterotonics - oxytocin", uterotonic["Oxytocin"])
	sheet.add("Mothers given uterotonics - carbetocin", uterotonic["Carbetocin"])
	sheet.add("Live births", len(live))
	sheet.add(
		"Low birth weight babies (below 2500 g)",
		sum(1 for b in live if b.birth_weight_g and b.birth_weight_g < LOW_BIRTH_WEIGHT_G),
	)
	sheet.add("Births with deformities", sum(1 for b in babies if b.deformity))
	sheet.add("Neonates given Vitamin K", sum(1 for b in live if b.vitamin_k))
	sheet.add("Babies applied chlorhexidine for cord care", sum(1 for b in live if b.chlorhexidine))
	sheet.add("Infants initiated on Kangaroo Mother Care", sum(1 for b in live if b.kangaroo_care))
	sheet.add("Babies given tetracycline at birth", sum(1 for b in live if b.teo))
	sheet.add(
		"Pre-term babies",
		sum(
			1
			for b in live
			if by_name[b.parent].gestation_weeks and by_name[b.parent].gestation_weeks < PRETERM_WEEKS
		),
	)
	sheet.add("Babies discharged alive", sum(1 for b in live if b.condition_at_discharge == "Alive"))
	sheet.add("Infants initiated on breastfeeding within 1 hour", sum(1 for b in live if b.breastfeeding_1hr))
	sheet.add(
		"Total deliveries from HIV+ mothers",
		sum(1 for d in deliveries if hiv.get(d.pregnancy_record) in ("Positive", "Known Positive")),
	)
	sheet.add(
		"Perinatal deaths (fresh stillbirth)", sum(1 for b in babies if b.outcome == "Fresh stillbirth")
	)
	sheet.add(
		"Perinatal deaths (macerated stillbirth)",
		sum(1 for b in babies if b.outcome == "Macerated stillbirth"),
	)
	lived = [days_lived(b) for b in live if b.condition_at_discharge == "Died"]
	sheet.add("Perinatal deaths 0 to 7 days", sum(1 for d in lived if d is not None and d <= 7))
	sheet.add("Neonatal deaths 0 to 28 days", sum(1 for d in lived if d is not None and d <= 28))

	died = [d for d in deliveries if d.maternal_condition == "Died"]
	dobs = _dobs({d.patient for d in died})
	sheet.add("Maternal deaths", len(died), bands=_bands(died, dobs, "delivery_datetime"))
	sheet.add(
		"Maternal deaths audited",
		sum(1 for d in died if d.maternal_death_audited),
		"MOH asks for audits within 7 days; the audit date isn't recorded",
	)
	for field, label in COMPLICATIONS:
		with_it = [d for d in deliveries if d.get(field)]
		sheet.add(f"{label} - alive", sum(1 for d in with_it if d.maternal_condition != "Died"))
		sheet.add(f"{label} - dead", sum(1 for d in with_it if d.maternal_condition == "Died"))


def _pnc(company, start, end, sheet):
	visits = frappe.get_all(
		"PNC Visit",
		filters={"company": company, "docstatus": 1, "visit_date": ["between", [start, end]]},
		fields=[
			"patient",
			"visit_number",
			"timing",
			"fp_counselled",
			"fp_method",
			"baby_reviewed",
			"fistula_screening",
			"referred_from_community",
		],
	)

	def count(test):
		return sum(1 for v in visits if test(v))

	sheet.section("PNC")
	sheet.add("New PNC clients", count(lambda v: v.visit_number == 1))
	sheet.add("Revisiting PNC clients", count(lambda v: (v.visit_number or 0) > 1))
	for timing, label in PNC_TIMINGS:
		sheet.add(f"Mothers received postpartum care {label}", count(lambda v, t=timing: v.timing == t))
	sheet.add("Mothers counselled on postpartum FP", count(lambda v: v.fp_counselled))
	# a method noted on the PNC visit, or a postpartum Family Planning Visit
	postpartum_fp = {v.patient for v in visits if v.fp_method} | set(
		frappe.get_all(
			"Family Planning Visit",
			filters={
				"company": company,
				"docstatus": 1,
				"visit_date": ["between", [start, end]],
				"timing": ["in", POSTPARTUM_FP],
				"procedure": ["!=", "Removal"],
			},
			pluck="patient",
		)
	)
	sheet.add("Mothers received postpartum FP", len(postpartum_fp))
	for timing, label in PNC_TIMINGS:
		sheet.add(
			f"Babies received postpartum care {label}",
			count(lambda v, t=timing: v.baby_reviewed and v.timing == t),
		)
	sheet.add("Cases of fistula", count(lambda v: v.fistula_screening == "Suspected fistula"))
	sheet.add("Referred from the community unit for PNC", count(lambda v: v.referred_from_community))


def _family_planning(company, start, end, sheet):
	visits = frappe.get_all(
		"Family Planning Visit",
		filters={"company": company, "docstatus": 1, "visit_date": ["between", [start, end]]},
		fields=["method", "procedure", "visit_type", "first_ever_user", "timing"],
	)
	by = Counter((v.method, v.visit_type) for v in visits)
	larc = Counter((v.method, v.procedure) for v in visits if v.method in LARC)
	methods = Counter(v.method for v in visits)
	given = [v for v in visits if v.procedure != "Removal"]

	sheet.section("Family Planning")
	sheet.add("First ever users of contraceptives", sum(1 for v in visits if v.first_ever_user))
	for method, label in FP_BY_VISIT_TYPE:
		sheet.add(f"{label} (New)", by[(method, "New")])
		sheet.add(f"{label} (Revisit)", by[(method, "Revisit")])
	sheet.add("Emergency contraceptive pill", methods["Emergency contraceptive pill"])
	sheet.add("Counselled on natural FP", methods["Natural FP counselling"])
	sheet.add("Given cycle beads", methods["Cycle beads"])
	for method, label in FP_INSERTIONS:
		sheet.add(f"{label} (1st time insertion)", larc[(method, "Insertion")])
		sheet.add(f"{label} (Reinsertion)", larc[(method, "Reinsertion")])
	sheet.add("BTL", methods["BTL"])
	sheet.add("Vasectomy", methods["Vasectomy"])
	sheet.add(
		"IUCD removal",
		sum(larc[(m, "Removal")] for m in ("Hormonal IUCD", "Non-hormonal IUCD")),
	)
	sheet.add("Implant removal", sum(larc[(m, "Removal")] for m in ("Implant (1 rod)", "Implant (2 rods)")))
	for timing, label in (
		("Immediate postpartum (within 48 hours)", "Receiving immediate postpartum FP (within 48 hrs)"),
		("Postpartum (3 days to 6 weeks)", "Receiving postpartum FP (3 days to 6 weeks)"),
		("Post abortion", "Receiving post abortion FP method"),
	):
		sheet.add(label, sum(1 for v in given if v.timing == timing))
