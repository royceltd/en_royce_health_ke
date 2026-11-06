# Copyright (c) 2026, Royce Technologies LTD and contributors
# For license information, please see license.txt

"""Radiology on Marley's imaging Observations (Observation Template category
'Imaging', ordered from an encounter like a lab test).

Exam status: Requested -> Performed (radiographer, contrast, dose, images)
-> Reported (radiologist's findings and impression; findings go to Marley's
result, so the observation shows as Preliminary) -> Verified (status Final,
observation submitted, which completes the service request).

Each imaging observation gets an accession number, the key a PACS or
modality worklist uses to match images to the request. Images can be
attached or linked (PACS viewer URL) until a DICOM/HL7 integration with the
hospital's equipment is built."""

import frappe
from frappe import _
from frappe.model.naming import make_autoname
from frappe.utils import now_datetime

IMAGING = "Imaging"
MODALITIES = ("X-ray", "Ultrasound", "CT", "MRI", "Mammography", "Fluoroscopy", "Contrast study")
MOH717_IMAGING = (
	"Plain XRay without contrast enhancement",
	"General ultrasound",
	"Contrast enhanced examinations",
	"Magnetic Resonance Imaging",
	"Computerized Tomography",
	"Mammography",
	"Obstetric ultrasound",
)
EXAM_STATUSES = ("Requested", "Performed", "Reported", "Verified")


def is_imaging(doc):
	return doc.get("observation_category") == IMAGING or (
		doc.get("observation_template")
		and frappe.db.get_value("Observation Template", doc.observation_template, "observation_category")
		== IMAGING
	)


def before_insert_observation(doc, method=None):
	"""Observation before_insert: accession number and starting status for imaging."""
	if not is_imaging(doc) or doc.get("parent_observation"):
		return
	doc.ke_accession_number = doc.ke_accession_number or make_autoname("RAD-.YYYY..MM..DD.-.####")
	doc.ke_exam_status = doc.ke_exam_status or "Requested"
	doc.ke_modality = doc.ke_modality or frappe.db.get_value(
		"Observation Template", doc.observation_template, "ke_modality"
	)


def _imaging(name):
	doc = frappe.get_doc("Observation", name)
	doc.check_permission("write")
	if not is_imaging(doc):
		frappe.throw(_("{0} is not an imaging observation.").format(name))
	return doc


@frappe.whitelist()
def mark_performed(
	observation: str,
	radiographer: str,
	contrast: int = 0,
	contrast_agent: str | None = None,
	radiation_dose: str | None = None,
	images: str | None = None,
	pacs_link: str | None = None,
):
	doc = _imaging(observation)
	if doc.ke_exam_status != "Requested":
		frappe.throw(_("This exam is already {0}.").format(doc.ke_exam_status))
	doc.update(
		{
			"ke_exam_status": "Performed",
			"ke_radiographer": radiographer,
			"ke_performed_at": now_datetime(),
			"ke_contrast": int(contrast or 0),
			"ke_contrast_agent": contrast_agent,
			"ke_radiation_dose": radiation_dose,
			"ke_images": images or doc.ke_images,
			"ke_pacs_link": pacs_link or doc.ke_pacs_link,
		}
	)
	doc.save()
	return doc.ke_exam_status


@frappe.whitelist()
def report(observation: str, findings: str, impression: str, radiologist: str):
	doc = _imaging(observation)
	if doc.ke_exam_status not in ("Performed", "Reported"):
		frappe.throw(_("Mark the exam performed before reporting it."))
	if not (findings and impression):
		frappe.throw(_("Findings and impression are both required."))
	doc.update(
		{
			"result": findings,
			"ke_impression": impression,
			"ke_reported_by": radiologist,
			"ke_reported_at": now_datetime(),
			"ke_exam_status": "Reported",
		}
	)
	doc.save()
	return doc.ke_exam_status


@frappe.whitelist()
def verify(observation: str, radiologist: str):
	"""Release the report: status Final, observation submitted."""
	doc = _imaging(observation)
	if doc.ke_exam_status != "Reported":
		frappe.throw(_("Only a reported exam can be verified."))
	doc.update({"ke_verified_by": radiologist, "ke_exam_status": "Verified", "status": "Final"})
	doc.save()
	doc.submit()
	return doc.ke_exam_status
