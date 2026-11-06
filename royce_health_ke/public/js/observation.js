// Copyright (c) 2026, Royce Technologies LTD and contributors
// For license information, please see license.txt

// Radiology actions on imaging observations: Performed -> Report -> Verify.
frappe.ui.form.on("Observation", {
	refresh(frm) {
		if (frm.doc.observation_category !== "Imaging" || frm.is_new() || frm.doc.parent_observation) return;
		const call = (method, args, message) =>
			frappe.call({ method, args: { observation: frm.doc.name, ...args }, freeze: true }).then(() => {
				frappe.show_alert({ message, indicator: "green" });
				frm.reload_doc();
			});
		const status = frm.doc.ke_exam_status;
		if (status === "Requested") {
			frm.add_custom_button(__("Exam Performed"), () =>
				frappe.prompt(
					[
						{ fieldname: "radiographer", fieldtype: "Data", label: __("Radiographer"), reqd: 1 },
						{ fieldname: "contrast", fieldtype: "Check", label: __("Contrast Given") },
						{ fieldname: "contrast_agent", fieldtype: "Data", label: __("Contrast Agent and Dose"), depends_on: "contrast" },
						{ fieldname: "radiation_dose", fieldtype: "Data", label: __("Radiation Dose") },
						{ fieldname: "pacs_link", fieldtype: "Data", label: __("PACS Viewer Link") },
					],
					(v) => call("royce_health_ke.radiology.mark_performed", v, __("Exam performed")),
					__("Exam Performed"),
				),
			).addClass("btn-primary");
		}
		if (status === "Performed" || status === "Reported") {
			frm.add_custom_button(__(status === "Performed" ? "Report" : "Edit Report"), () =>
				frappe.prompt(
					[
						{ fieldname: "findings", fieldtype: "Text Editor", label: __("Findings"), reqd: 1, default: frm.doc.result },
						{ fieldname: "impression", fieldtype: "Small Text", label: __("Impression"), reqd: 1, default: frm.doc.ke_impression },
						{ fieldname: "radiologist", fieldtype: "Link", options: "Healthcare Practitioner", label: __("Radiologist"), reqd: 1, default: frm.doc.ke_reported_by },
					],
					(v) => call("royce_health_ke.radiology.report", v, __("Reported")),
					__("Radiology Report"),
				),
			);
		}
		if (status === "Reported") {
			frm.add_custom_button(__("Verify and Release"), () =>
				frappe.prompt(
					{ fieldname: "radiologist", fieldtype: "Link", options: "Healthcare Practitioner", label: __("Verifying Radiologist"), reqd: 1 },
					(v) => call("royce_health_ke.radiology.verify", v, __("Report released")),
					__("Verify and Release"),
				),
			).addClass("btn-primary");
		}
	},
});
