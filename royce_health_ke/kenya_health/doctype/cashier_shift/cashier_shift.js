// Copyright (c) 2026, Royce Technologies LTD and contributors
// For license information, please see license.txt

frappe.ui.form.on("Cashier Shift", {
	setup(frm) {
		frm.set_query("cash_account", () => ({
			filters: { company: frm.doc.company, account_type: "Cash", is_group: 0 },
		}));
	},
	onload(frm) {
		if (frm.is_new() && !frm.doc.company) {
			frm.set_value("company", frappe.defaults.get_user_default("Company"));
		}
	},
	refresh(frm) {
		if (frm.doc.docstatus === 0 && !frm.is_new()) {
			frm.add_custom_button(__("Refresh Takings"), () => frm.save());
			frm.page.set_primary_action(__("Close Shift"), () => frm.savesubmit());
			frm.dashboard.add_comment(
				__("Open: payments you take are recorded on this shift. Enter what you counted, then Close Shift."),
				"blue",
				true
			);
		}
	},
});
