// Copyright (c) 2026, Royce Technologies LTD and contributors
// For license information, please see license.txt

frappe.ui.form.on("Insurance Claim", {
	refresh(frm) {
		if (frm.doc.docstatus !== 1) return;
		const unsettled = (frm.doc.coverages || []).filter(
			(row) => row.status === "Rejected" && row.rejected_amount > 0 && !row.ke_settlement_entry,
		);
		if (!unsettled.length) return;
		const total = unsettled.reduce((sum, row) => sum + row.rejected_amount, 0);
		frm.add_custom_button(__("Settle Rejected Lines"), () => {
			frappe.prompt(
				[
					{
						fieldname: "action",
						fieldtype: "Select",
						label: __("Settle {0} rejected by the insurer", [format_currency(total)]),
						options: ["Bill Patient", "Write Off"],
						default: "Bill Patient",
						reqd: 1,
						description: __(
							"Bill Patient moves the amount to the patient's account. Write Off charges it to the insurer's Rejected Claims expense account.",
						),
					},
				],
				(values) =>
					frappe.call({
						method: "royce_health_ke.claims.settle_rejected",
						args: { claim: frm.doc.name, action: values.action },
						freeze: true,
						callback: (r) => {
							frappe.show_alert({
								message: __("Settled with {0}", [(r.message || []).join(", ")]),
								indicator: "green",
							});
							frm.reload_doc();
						},
					}),
				__("Settle Rejected Lines"),
				__("Settle"),
			);
		});
	},
});
