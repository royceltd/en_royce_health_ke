// Copyright (c) 2026, Royce Technologies LTD and contributors
// For license information, please see license.txt

// "Only cashiers take payments" (Kenya Health Settings): service points can
// bill but not receive money, so the payment options are hidden for them.
// The server refuses the payment anyway (royce_health_ke.cashier).
frappe.ui.form.on("Sales Invoice", {
	refresh(frm) {
		// A patient's paid invoice: the 80 mm Patient Receipt for the EPOS printer.
		if (frm.doc.docstatus === 1 && frm.doc.patient) {
			frm.add_custom_button(__("Patient Receipt"), () => {
				const params = new URLSearchParams({
					doctype: frm.doctype,
					name: frm.doc.name,
					format: "Patient Receipt",
					no_letterhead: 1,
					trigger_print: 1,
				});
				window.open(`/printview?${params}`, "_blank");
			});
		}
		if (!frappe.boot.ke_payment_blocked) return;
		frm.set_df_property("is_pos", "hidden", 1);
		// ERPNext adds its buttons in the same refresh: remove them after.
		setTimeout(() => {
			frm.remove_custom_button(__("Payment"), __("Create"));
			frm.remove_custom_button(__("Payment Request"), __("Create"));
		}, 0);
	},
});
