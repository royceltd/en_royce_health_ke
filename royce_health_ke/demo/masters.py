# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Demo master data: departments, rooms and beds, practitioners, lab tests,
medicines and prices for the fictional Kijani Valley Hospital."""

import frappe
from frappe.utils import getdate

from royce_health_ke.utils import installed

# KRA's sandbox only lists 26 item classifications (animals, zero-rated goods),
# none medical. Demo items use the exempt-band root code; a live hospital uses
# real health UNSPSC codes from KRA's production list.
CLS_EXEMPT = "1000000000"
CLS_STANDARD = "1010151700"

DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")

LAB_TESTS = (
	# code, name, rate, uom, normal range, sample
	(
		"LAB-BSMPS",
		"Malaria Blood Slide (BS for MPS)",
		500,
		None,
		"No malaria parasites seen",
		"Capillary Blood",
	),
	("LAB-HB", "Haemoglobin (Hb)", 400, "g/dL", "F 12.0 - 15.5 / M 13.5 - 17.5", "Whole Blood (EDTA)"),
	("LAB-WBC", "White Cell Count (WBC)", 400, "x10^9/L", "4.0 - 11.0", "Whole Blood (EDTA)"),
)

MEDICINES = (
	# generic name, class, strength (mg), form, item code, price per unit (KES), cost
	(
		"Artemether-Lumefantrine (AL) 20/120",
		"Artemether + Lumefantrine",
		120,
		"Tablet",
		"DRG-AL20120",
		25,
		12,
	),
	("Paracetamol", "Paracetamol", 500, "Tablet", "DRG-PCM500", 5, 1.5),
	("Amoxicillin", "Amoxicillin", 500, "Capsule", "DRG-AMX500", 15, 6),
)


def abbr(company):
	return frappe.db.get_value("Company", company, "abbr")


def ensure_company(company):
	"""Create and set up the demo hospital company the way a real client is
	provisioned: kenyan_accountant's provision() (company, wizard defaults,
	Kenyan chart and VAT), then royce_payroll_ke's when installed. The company
	must exist before either app's per-company setup can run."""
	if not frappe.db.exists("Company", company):
		if installed("kenyan_accountant"):
			from kenyan_accountant.setup.provision import provision

			provision(company)
		else:
			from frappe.desk.page.setup_wizard.setup_wizard import setup_complete

			setup_complete(
				{
					"language": "English",
					"country": "Kenya",
					"timezone": "Africa/Nairobi",
					"currency": "KES",
					"company_name": company,
					"company_abbr": "".join(w[0] for w in company.split()[:3]).upper(),
					"chart_of_accounts": "Standard",
					"fy_start_date": f"{getdate().year}-01-01",
					"fy_end_date": f"{getdate().year}-12-31",
					"setup_demo": 0,
				}
			)
	if installed("royce_payroll_ke") and not frappe.db.exists(
		"Salary Structure", {"company": company, "docstatus": 1}
	):
		from royce_payroll_ke.kenya_payroll.setup import provision as payroll_provision

		payroll_provision(company)


def ensure(doctype, name, data):
	if frappe.db.exists(doctype, name):
		return frappe.get_doc(doctype, name)
	doc = frappe.get_doc({"doctype": doctype, **data})
	doc.insert(ignore_permissions=True)
	return doc


def tax_template(company, kind):
	"""kenyan_accountant's item tax template for `kind` ("Exempt", "Standard 16%"),
	or None without it - an exempt item then simply carries no tax."""
	name = f"KE {kind} - {abbr(company)}"
	return name if frappe.db.exists("Item Tax Template", name) else None


def has_kra_class(code):
	"""royce_etims is installed and KRA's classification list (synced when
	eTIMS is activated) has `code`. Re-running the loader after activation
	fills in what was skipped before."""
	return installed("royce_etims") and bool(frappe.db.exists("eTIMS Item Classification", code))


def set_item_tax(company, item_code, kind="Exempt"):
	item = frappe.get_doc("Item", item_code)
	template = tax_template(company, kind)
	if template and not any(t.item_tax_template == template for t in item.taxes):
		item.set("taxes", [{"item_tax_template": template}])
	cls = CLS_STANDARD if kind == "Standard 16%" else CLS_EXEMPT
	if has_kra_class(cls):
		item.royce_etims_item_classification = item.royce_etims_item_classification or cls
		item.royce_etims_item_classification_code = item.royce_etims_item_classification
		if not item.get("royce_etims_id_mapping"):
			item.royce_etims_taxation_type = None  # re-derived from the template on save
	item.save(ignore_permissions=True)


def item(company, code, name, group, rate, kind="Exempt", stock=0):
	if not frappe.db.exists("Item", code):
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": code,
				"item_name": name,
				"item_group": group,
				"stock_uom": "Nos",
				"is_stock_item": stock,
				"include_item_in_manufacturing": 0,
				"standard_rate": rate,
			}
		).insert(ignore_permissions=True)
	set_item_tax(company, code, kind)


def load(company):
	a = abbr(company)

	if has_kra_class(CLS_EXEMPT):
		for group in ("Services", "Laboratory", "Drug"):
			if not frappe.db.get_value("Item Group", group, "royce_etims_item_classification"):
				frappe.db.set_value("Item Group", group, "royce_etims_item_classification", CLS_EXEMPT)

	for dept in ("General Medicine", "Pathology", "Pharmacy"):
		ensure("Medical Department", dept, {"department": dept})

	# Services. The admission kit is a stock product from the start: KRA keeps
	# an item's type from its first registration (see royce_etims item guard).
	item(company, "CONS-GP", "General Consultation (OPD)", "Services", 1500)
	item(company, "CONS-IP", "Inpatient Ward Round", "Services", 2000)
	item(company, "NURS-IP", "Nursing Care per Day", "Services", 1200)
	item(company, "KIT-ADM", "Admission Comfort Kit (toiletries)", "Products", 850, "Standard 16%", stock=1)

	_service_units(company, a)
	_practitioners(a)
	_lab(company)
	_pharmacy(company)

	for dx in ("Malaria, uncomplicated (ICD-10 B54)", "Anaemia, unspecified (ICD-10 D64.9)"):
		ensure("Diagnosis", dx, {"diagnosis": dx})
	for complaint in ("Fever", "Headache", "Chills", "Joint pains", "Vomiting"):
		ensure("Complaint", complaint, {"complaints": complaint})

	settings = frappe.get_single("Healthcare Settings")
	settings.op_consulting_charge_item = settings.op_consulting_charge_item or "CONS-GP"
	settings.inpatient_visit_charge_item = settings.inpatient_visit_charge_item or "CONS-IP"
	settings.save(ignore_permissions=True)


def _service_units(company, a):
	ensure(
		"Healthcare Service Unit Type",
		"Consultation Room",
		{"service_unit_type": "Consultation Room", "allow_appointments": 1},
	)
	if not frappe.db.exists("Healthcare Service Unit Type", "General Ward Bed"):
		frappe.get_doc(
			{
				"doctype": "Healthcare Service Unit Type",
				"service_unit_type": "General Ward Bed",
				"inpatient_occupancy": 1,
				"is_billable": 1,
				"item_code": "WARD-GEN",
				"item_group": "Services",
				"uom": "Nos",
				"rate": 4500,
				"no_of_hours": 24,
				"minimum_billable_qty": 1,
				"description": "General ward bed, per day",
			}
		).insert(ignore_permissions=True)
	set_item_tax(company, "WARD-GEN")

	root = frappe.db.get_value(
		"Healthcare Service Unit", {"is_group": 1, "parent_healthcare_service_unit": ["in", ["", None]]}
	)
	hospital = ensure(
		"Healthcare Service Unit",
		f"Kijani Valley Hospital - {a}",
		{
			"healthcare_service_unit_name": "Kijani Valley Hospital",
			"is_group": 1,
			"parent_healthcare_service_unit": root,
			"company": company,
		},
	)
	ensure(
		"Healthcare Service Unit",
		f"OPD Room 1 - {a}",
		{
			"healthcare_service_unit_name": "OPD Room 1",
			"parent_healthcare_service_unit": hospital.name,
			"service_unit_type": "Consultation Room",
			"allow_appointments": 1,
			"company": company,
		},
	)
	ward = ensure(
		"Healthcare Service Unit",
		f"General Ward - {a}",
		{
			"healthcare_service_unit_name": "General Ward",
			"is_group": 1,
			"parent_healthcare_service_unit": hospital.name,
			"company": company,
		},
	)
	for i in range(1, 5):
		ensure(
			"Healthcare Service Unit",
			f"GW Bed 0{i} - {a}",
			{
				"healthcare_service_unit_name": f"GW Bed 0{i}",
				"parent_healthcare_service_unit": ward.name,
				"service_unit_type": "General Ward Bed",
				"inpatient_occupancy": 1,
				"occupancy_status": "Vacant",
				"company": company,
			},
		)


def _practitioners(a):
	ensure(
		"Appointment Type",
		"General Consultation",
		{
			"appointment_type": "General Consultation",
			"default_duration": 15,
			"allow_booking_for": "Practitioner",
		},
	)
	ensure(
		"Practitioner Schedule",
		"OPD Daily 08-17",
		{
			"schedule_name": "OPD Daily 08-17",
			"time_slots": [
				{"day": d, "from_time": "08:00:00", "to_time": "17:00:00", "duration": 15} for d in DAYS
			],
		},
	)
	for first, last, gender in (("Amina", "Achieng", "Female"), ("Brian", "Kiprotich", "Male")):
		if frappe.db.exists("Healthcare Practitioner", {"first_name": first, "last_name": last}):
			continue
		frappe.get_doc(
			{
				"doctype": "Healthcare Practitioner",
				"first_name": first,
				"last_name": last,
				"gender": gender,
				"status": "Active",
				"department": "General Medicine",
				"op_consulting_charge_item": "CONS-GP",
				"op_consulting_charge": 1500,
				"inpatient_visit_charge_item": "CONS-IP",
				"inpatient_visit_charge": 2000,
				"practitioner_schedules": [
					{"schedule": "OPD Daily 08-17", "service_unit": f"OPD Room 1 - {a}"}
				],
			}
		).insert(ignore_permissions=True)


def _lab(company):
	for sample in ("Whole Blood (EDTA)", "Capillary Blood"):
		ensure("Lab Test Sample", sample, {"sample": sample})
	for uom in ("g/dL", "x10^9/L", "mL"):
		ensure("Lab Test UOM", uom, {"lab_test_uom": uom})
	for code, name, rate, uom, normal_range, sample in LAB_TESTS:
		if not frappe.db.exists("Lab Test Template", name):
			frappe.get_doc(
				{
					"doctype": "Lab Test Template",
					"lab_test_name": name,
					"lab_test_code": code,
					"lab_test_group": "Laboratory",
					"department": "Pathology",
					"lab_test_template_type": "Single",
					"is_billable": 1,
					"lab_test_rate": rate,
					"lab_test_uom": uom,
					"lab_test_normal_range": normal_range,
					"sample": sample,
					"sample_qty": 2,
					"sample_uom": "mL",
				}
			).insert(ignore_permissions=True)
		set_item_tax(company, frappe.db.get_value("Lab Test Template", name, "item"))


def _pharmacy(company):
	for dosage in ("1-0-1 (twice daily)", "1-1-1 (three times daily)"):
		ensure("Prescription Dosage", dosage, {"dosage": dosage})
	for days in (3, 5):
		ensure("Prescription Duration", f"{days} Day", {"number": days, "period": "Day"})
	if not frappe.db.exists("UOM", "mg"):
		frappe.get_doc({"doctype": "UOM", "uom_name": "mg"}).insert(ignore_permissions=True)
	for generic, med_class, strength, form, code, rate, _cost in MEDICINES:
		ensure("Medication Class", med_class, {"medication_class": med_class})
		if not frappe.db.exists("Medication", {"generic_name": generic}):
			# Marley names a Medication "<form> <generic name> <strength><uom>",
			# e.g. "Tablet Paracetamol 500mg", and creates the Item itself.
			frappe.get_doc(
				{
					"doctype": "Medication",
					"generic_name": generic,
					"medication_class": med_class,
					"strength": strength,
					"strength_uom": "mg",
					"dosage_form": form,
					"linked_items": [
						{
							"item_code": code,
							"item_group": "Drug",
							"stock_uom": "Nos",
							"rate": rate,
							"is_billable": 1,
						}
					],
				}
			).insert(ignore_permissions=True)
		set_item_tax(company, code)


def medication(item_code):
	return frappe.db.get_value(
		"Medication Linked Item", {"item": item_code}, "parent"
	) or frappe.db.get_value("Medication Linked Item", {"item_code": item_code}, "parent")
