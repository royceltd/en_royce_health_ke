// Copyright (c) 2026, Royce Technologies LTD and contributors
// For license information, please see license.txt

// Abnormal readings (worked out on save, royce_health_ke.vitals) shown in red,
// with a headline listing them.
frappe.ui.form.on("Vital Signs", {
	refresh(frm) {
		const abnormal = (frm.doc.ke_abnormal_fields || "").split(",").filter(Boolean);
		for (const df of frm.meta.fields) {
			const field = frm.fields_dict[df.fieldname];
			if (field && field.$wrapper) field.$wrapper.toggleClass("ke-vital-abnormal", abnormal.includes(df.fieldname));
		}
		frm.dashboard.clear_headline();
		if (frm.doc.ke_vitals_status === "Abnormal") {
			frm.dashboard.set_headline(
				`<b>${__("Abnormal vitals")}:</b> ${frappe.utils.escape_html(frm.doc.ke_vitals_flags || "").replace(/\n/g, " · ")}`,
				"red",
			);
		}
	},
});

frappe.dom.set_style(`
	.ke-vital-abnormal .control-label { color: var(--red-600); font-weight: 600; }
	.ke-vital-abnormal .control-input, .ke-vital-abnormal .control-value { color: var(--red-600); font-weight: 600; }
	.ke-vital-abnormal input { border-color: var(--red-400); }
`);
