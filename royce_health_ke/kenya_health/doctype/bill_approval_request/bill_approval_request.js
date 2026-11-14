// Copyright (c) 2026, Royce Technologies LTD and contributors
// For license information, please see license.txt

frappe.ui.form.on("Bill Approval Request", {
	setup(frm) {
		frm.set_query("sales_invoice", () => ({
			filters: {
				ke_patient_visit: frm.doc.patient_visit,
				is_return: 0,
				docstatus: frm.doc.request_type === "Discount" ? 0 : 1,
			},
		}));
	},
	refresh(frm) {
		const colours = { Pending: "orange", Approved: "green", Rejected: "red" };
		if (!frm.is_new()) frm.page.set_indicator(__(frm.doc.status), colours[frm.doc.status]);
		if (frm.is_new() || frm.doc.status !== "Pending") return;
		const managers = ["System Manager", "Healthcare Administrator", "Accounts Manager"];
		if (!managers.some((r) => frappe.user.has_role(r))) return;
		const act = (method, label, reqd) =>
			frappe.prompt(
				{ fieldname: "remarks", fieldtype: "Small Text", label: reqd ? __("Why?") : __("Remarks (optional)"), reqd },
				(v) =>
					frappe
						.call({ method: "royce_health_ke.approvals." + method, args: { name: frm.doc.name, remarks: v.remarks }, freeze: true })
						.then(() => frm.reload_doc()),
				label,
			);
		frm.add_custom_button(__("Approve"), () => act("approve", __("Approve {0}", [__(frm.doc.request_type)]), 0)).addClass("btn-primary");
		frm.add_custom_button(__("Reject"), () => act("reject", __("Reject"), 1));
	},
	request_type(frm) {
		frm.set_value("sales_invoice", null);
	},
});
