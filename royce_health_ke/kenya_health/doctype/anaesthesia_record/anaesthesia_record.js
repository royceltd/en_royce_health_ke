// Copyright (c) 2026, Royce Technologies LTD and contributors
// For license information, please see license.txt

frappe.ui.form.on("Anaesthesia Record", {
	refresh(frm) {
		if (frm.doc.docstatus !== 0 || !frm.doc.patient) return;
		frm.add_custom_button(__("Fetch Lab Results"), () =>
			frappe
				.call({
					method: "royce_health_ke.theatre.latest_labs",
					args: { patient: frm.doc.patient },
				})
				.then(({ message }) => {
					const found = Object.keys(message || {});
					if (!found.length) {
						frappe.show_alert({
							message: __("No matching lab results in the last 30 days."),
							indicator: "orange",
						});
						return;
					}
					frm.set_value(message);
					frappe.show_alert({
						message: __("{0} lab results filled in.", [found.length]),
						indicator: "green",
					});
				}),
		);
	},
	gcs_e: (frm) => frm.trigger("gcs"),
	gcs_m: (frm) => frm.trigger("gcs"),
	gcs_v: (frm) => frm.trigger("gcs"),
	gcs(frm) {
		const { gcs_e, gcs_m, gcs_v } = frm.doc;
		frm.set_value("gcs_total", gcs_e && gcs_m && gcs_v ? gcs_e + gcs_m + gcs_v : 0);
	},
});
