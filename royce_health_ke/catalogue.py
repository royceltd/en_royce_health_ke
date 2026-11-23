# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""A starter service list for a new hospital: common lab tests, imaging
exams, ward and minor procedures and theatre operations, each with its item
and a cash price, so requests can be made, priced, billed and routed from
day one (Bethesda, 23 Nov 2026: "for the price list, let's use random values
for now").

The prices are placeholders: each item's description says so, and the
hospital replaces them (Item Price, or each template's rate) before real
billing, with its insurers' prices. Nothing the hospital already has is
touched: a template of the same name is left as it is (ADR-023).

Each kind is routed by the request types (routing.py): lab tests to the
Laboratory, imaging to Radiology, ward procedures (item group Nursing
Procedures) to Nursing, minor procedures to the Procedure Room, operations
(item group Surgical Procedures) to Theatre."""

import frappe
from frappe import _

PLACEHOLDER = "Starter price: replace with the hospital's own price before billing."

# name, code, cash price, unit, normal range, sample
LAB = (
	(
		"Malaria Blood Slide (BS for MPS)",
		"LAB-BSMPS",
		300,
		None,
		"No malaria parasites seen",
		"Capillary Blood",
	),
	("Malaria Rapid Test (mRDT)", "LAB-MRDT", 300, None, "Negative", "Capillary Blood"),
	("Haemoglobin (Hb)", "LAB-HB", 300, "g/dL", "F 12.0 - 15.5 / M 13.5 - 17.5", "Whole Blood (EDTA)"),
	("Random Blood Sugar (RBS)", "LAB-RBS", 200, "mmol/L", "3.9 - 7.8", "Capillary Blood"),
	("Fasting Blood Sugar (FBS)", "LAB-FBS", 200, "mmol/L", "3.9 - 5.6", "Capillary Blood"),
	("HbA1c", "LAB-HBA1C", 1500, "%", "Below 5.7", "Whole Blood (EDTA)"),
	("Urinalysis", "LAB-URINE", 300, None, "Normal", "Urine"),
	("Stool Microscopy (O/C)", "LAB-STOOL", 300, None, "No ova or cysts seen", "Stool"),
	("Pregnancy Test (Urine hCG)", "LAB-PDT", 200, None, "Negative", "Urine"),
	("Blood Group and Rhesus", "LAB-BGRH", 300, None, None, "Whole Blood (EDTA)"),
	("Erythrocyte Sedimentation Rate (ESR)", "LAB-ESR", 300, "mm/hr", "0 - 20", "Whole Blood (EDTA)"),
	("Widal Test", "LAB-WIDAL", 400, None, "Below 1:80", "Serum"),
	("Salmonella Typhi Antigen (Stool)", "LAB-STAG", 800, None, "Negative", "Stool"),
	("H. pylori Antigen (Stool)", "LAB-HPYL", 800, None, "Negative", "Stool"),
	("Brucella Test", "LAB-BRUC", 500, None, "Negative", "Serum"),
	("VDRL / RPR", "LAB-VDRL", 300, None, "Non-reactive", "Serum"),
	("HIV Rapid Test", "LAB-HIV", 0, None, "Negative", "Capillary Blood"),
	("Hepatitis B Surface Antigen (HBsAg)", "LAB-HBSAG", 500, None, "Negative", "Serum"),
	("C-Reactive Protein (CRP)", "LAB-CRP", 1000, "mg/L", "Below 5", "Serum"),
	("Urea, Electrolytes and Creatinine (UEC)", "LAB-UEC", 1500, None, None, "Serum"),
	("Liver Function Tests (LFT)", "LAB-LFT", 1800, None, None, "Serum"),
	("Lipid Profile", "LAB-LIPID", 1800, None, None, "Serum"),
	("Uric Acid", "LAB-URIC", 600, "umol/L", "F 140 - 360 / M 200 - 430", "Serum"),
	("Thyroid Stimulating Hormone (TSH)", "LAB-TSH", 1500, "mIU/L", "0.4 - 4.0", "Serum"),
	("Sputum for AFB / GeneXpert", "LAB-AFB", 0, None, "MTB not detected", "Sputum"),
)
# name, code, modality, MOH 717 row, cash price
IMAGING = (
	("Chest X-ray (PA)", "IMG-CXR", "X-ray", "Plain XRay without contrast enhancement", 1500),
	("X-ray Abdomen", "IMG-XAB", "X-ray", "Plain XRay without contrast enhancement", 1500),
	("X-ray Skull", "IMG-XSK", "X-ray", "Plain XRay without contrast enhancement", 1500),
	("X-ray Lumbosacral Spine", "IMG-XLS", "X-ray", "Plain XRay without contrast enhancement", 2000),
	("X-ray Pelvis", "IMG-XPV", "X-ray", "Plain XRay without contrast enhancement", 1500),
	("X-ray Limb (one part)", "IMG-XLB", "X-ray", "Plain XRay without contrast enhancement", 1200),
	("Abdominal ultrasound", "IMG-ABUS", "Ultrasound", "General ultrasound", 2500),
	("Pelvic ultrasound", "IMG-PVUS", "Ultrasound", "General ultrasound", 2500),
	("Obstetric ultrasound", "IMG-OBUS", "Ultrasound", "Obstetric ultrasound", 2000),
	("Breast ultrasound", "IMG-BRUS", "Ultrasound", "General ultrasound", 2500),
	("Thyroid / neck ultrasound", "IMG-NKUS", "Ultrasound", "General ultrasound", 2500),
	("Scrotal ultrasound", "IMG-SCUS", "Ultrasound", "General ultrasound", 2500),
)
# name, code, kind (nursing / minor / theatre), cash price
PROCEDURES = (
	("Wound Dressing", "PROC-DRESS", "nursing", 300),
	("Injection (IM / IV)", "PROC-INJ", "nursing", 100),
	("IV Cannulation", "PROC-CANN", "nursing", 300),
	("Urinary Catheterisation", "PROC-CATH", "nursing", 500),
	("Nasogastric Tube Insertion", "PROC-NGT", "nursing", 500),
	("Nebulisation", "PROC-NEB", "nursing", 300),
	("Suturing (minor wound)", "PROC-SUT", "minor", 1000),
	("Incision and Drainage", "PROC-IND", "minor", 1500),
	("Plaster of Paris (POP) Application", "PROC-POP", "minor", 2500),
	("Electrocardiogram (ECG)", "PROC-ECG", "minor", 1000),
	("Removal of Foreign Body", "PROC-RFB", "minor", 1000),
	("Caesarean Section", "PROC-CS", "theatre", 60000),
	("Appendicectomy (open)", "PROC-APPX", "theatre", 85000),
	("Herniorrhaphy", "PROC-HERN", "theatre", 45000),
	("Exploratory Laparotomy", "PROC-LAP", "theatre", 90000),
	("Evacuation of Retained Products (MVA)", "PROC-MVA", "theatre", 8000),
	("Bilateral Tubal Ligation", "PROC-BTL", "theatre", 20000),
	("Male Circumcision", "PROC-CIRC", "theatre", 5000),
	("Total Abdominal Hysterectomy", "PROC-TAH", "theatre", 120000),
)
GROUPS = {"nursing": "Nursing Procedures", "minor": "Services", "theatre": "Surgical Procedures"}
DEPARTMENTS = {"nursing": "Nursing", "minor": "General Medicine", "theatre": "General Surgery"}


def _ensure(doctype, name, values):
	if not frappe.db.exists(doctype, name):
		frappe.get_doc({"doctype": doctype, **values}).insert(ignore_permissions=True)


def _department(name):
	_ensure("Medical Department", name, {"department": name})
	return name


def _group(name):
	return name if frappe.db.exists("Item Group", name) else "Services"


def _mark(item_code, company):
	"""The item's note that its price is a placeholder, and its VAT (exempt)."""
	if not item_code or not frappe.db.exists("Item", item_code):
		return
	description = frappe.db.get_value("Item", item_code, "description") or ""
	if PLACEHOLDER not in description:
		frappe.db.set_value("Item", item_code, "description", f"{description} {PLACEHOLDER}".strip())
	from royce_health_ke.demo.masters import set_item_tax

	try:
		set_item_tax(company, item_code)
	except frappe.ValidationError:
		frappe.clear_last_message()


def _insert(values, skipped):
	"""Insert one template; one the site refuses (a clash with its own data) is
	skipped and reported, not stopping the rest."""
	frappe.db.savepoint("ke_catalogue")
	try:
		return frappe.get_doc(values).insert(ignore_permissions=True)
	except frappe.ValidationError as e:
		frappe.db.rollback(save_point="ke_catalogue")
		frappe.clear_last_message()
		skipped.append(
			f"{values.get('lab_test_name') or values.get('observation') or values.get('template')}: {e}"
		)
		return None


def _taken(doctype, name, code):
	return frappe.db.exists(doctype, name) or frappe.db.exists("Item", code)


def load(company: str) -> dict:
	"""Add the starter services the hospital doesn't have yet. Returns the
	names added, by kind."""
	added = {"lab": [], "imaging": [], "procedures": []}
	skipped = []
	for sample in {row[5] for row in LAB}:
		_ensure("Lab Test Sample", sample, {"sample": sample})
	for uom in {row[3] for row in LAB if row[3]} | {"mL"}:
		_ensure("Lab Test UOM", uom, {"lab_test_uom": uom})
	pathology = _department("Pathology")
	for name, code, rate, uom, normal, sample in LAB:
		if _taken("Lab Test Template", name, code):
			continue
		doc = _insert(
			{
				"doctype": "Lab Test Template",
				"lab_test_name": name,
				"lab_test_code": code,
				"lab_test_group": _group("Laboratory"),
				"department": pathology,
				"lab_test_template_type": "Single",
				# programme tests (HIV, TB) are free: not billed
				"is_billable": 1 if rate else 0,
				"lab_test_rate": rate,
				"lab_test_uom": uom,
				"lab_test_normal_range": normal,
				"sample": sample,
				"sample_qty": 2,
				"sample_uom": "mL",
			},
			skipped,
		)
		if not doc:
			continue
		_mark(doc.item, company)
		added["lab"].append(name)
	from royce_health_ke import lab

	if not _taken("Lab Test Template", "Full Haemogram", "LAB-FHG"):
		lab.add_from_library("Full Haemogram", 1000)
		_mark("LAB-FHG", company)
		added["lab"].append("Full Haemogram")

	radiology = _department("Radiology")
	for name, code, modality, moh_row, rate in IMAGING:
		if _taken("Observation Template", name, code):
			continue
		doc = _insert(
			{
				"doctype": "Observation Template",
				"observation": name,
				# unique; initials repeat (X-ray Limb / X-ray Lumbosacral Spine)
				"abbr": code.removeprefix("IMG-"),
				"observation_category": "Imaging",
				"permitted_data_type": "Text",
				"medical_department": radiology,
				"is_billable": 1,
				"item_code": code,
				"item_group": "Services",
				"rate": rate,
				"ke_modality": modality,
				"ke_moh717_imaging": moh_row,
			},
			skipped,
		)
		if not doc:
			continue
		_mark(doc.item or code, company)
		added["imaging"].append(name)

	for name, code, kind, rate in PROCEDURES:
		if _taken("Clinical Procedure Template", name, code):
			continue
		doc = _insert(
			{
				"doctype": "Clinical Procedure Template",
				"template": name,
				"item_code": code,
				"item_group": _group(GROUPS[kind]),
				"medical_department": _department(DEPARTMENTS[kind]),
				"is_billable": 1,
				"rate": rate,
				"description": name,
			},
			skipped,
		)
		if not doc:
			continue
		_mark(doc.item_code or code, company)
		added["procedures"].append(name)
	if skipped:
		added["skipped"] = skipped
	return added


@frappe.whitelist()
def load_starter_services() -> dict:
	"""Kenya Health Settings: load the starter services (System Manager)."""
	frappe.only_for(("System Manager", "Healthcare Administrator"))
	company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value(
		"Global Defaults", "default_company"
	)
	if not company:
		frappe.throw(_("Set the default company first."))
	return load(company)
