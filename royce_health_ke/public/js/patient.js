// Copyright (c) 2026, Royce Technologies LTD and contributors
// For license information, please see license.txt

frappe.ui.form.on("Patient", {
	refresh(frm) {
		if (frm.is_new() || !frappe.model.can_read("Patient Record Access")) return;
		frm.add_custom_button(
			__("Who Opened This Record"),
			() => frappe.set_route("List", "Patient Record Access", { patient: frm.doc.name }),
			__("View")
		);
	},
});
