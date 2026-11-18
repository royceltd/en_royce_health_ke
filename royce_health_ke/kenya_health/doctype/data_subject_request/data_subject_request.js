// Copyright (c) 2026, Royce Technologies LTD and contributors
// For license information, please see license.txt

frappe.ui.form.on("Data Subject Request", {
	refresh(frm) {
		if (frm.is_new() || ["Completed", "Refused"].includes(frm.doc.status)) return;
		if (frm.doc.request_type === "Access (copy of the record)") {
			frm.add_custom_button(__("Export Patient Record"), () =>
				frappe
					.xcall("royce_health_ke.dataprotection.export_record", {
						request: frm.doc.name,
					})
					.then(() => {
						frappe.show_alert({
							message: __("Record exported and attached"),
							indicator: "green",
						});
						frm.reload_doc();
					})
			).addClass("btn-primary");
		}
		if (frm.doc.request_type === "Correction" && frm.doc.patient) {
			frm.add_custom_button(__("Open Patient to Correct"), () =>
				frappe.set_route("Form", "Patient", frm.doc.patient)
			);
		}
	},
});
