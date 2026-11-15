// Copyright (c) 2026, Royce Technologies LTD and contributors
// For license information, please see license.txt

frappe.ui.form.on("Kenya Health Settings", {
	add_clinical_services() {
		frappe.call({
			method: "royce_health_ke.clinical.setup_services",
			freeze: true,
		});
	},
	load_growth_standards() {
		frappe.call({
			method: "royce_health_ke.growth.sync",
			freeze: true,
			freeze_message: __("Downloading the WHO Child Growth Standards..."),
			callback: (r) => {
				if (r.message) frappe.msgprint(__("WHO Child Growth Standards loaded."));
			},
		});
	},
});
