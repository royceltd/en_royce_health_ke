// Copyright (c) 2026, Royce Technologies LTD and contributors
// For license information, please see license.txt

// Triage list: the Vitals column shows Abnormal in red and Normal in green,
// with the abnormal readings on hover (royce_health_ke.vitals).
frappe.listview_settings["Vital Signs"] = {
	add_fields: ["ke_vitals_status", "ke_vitals_flags"],
	formatters: {
		ke_vitals_status(value, df, doc) {
			if (!value) return "";
			const colour = value === "Abnormal" ? "red" : "green";
			const title = frappe.utils.escape_html((doc.ke_vitals_flags || "").replace(/\n/g, " · "));
			return `<span class="indicator-pill ${colour} filterable" title="${title}"
				data-filter="ke_vitals_status,=,${value}"><span>${__(value)}</span></span>`;
		},
	},
};
