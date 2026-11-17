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
		// Take Payment: amount received and the change (Bethesda, 17 Nov 2026).
		const due = frm.doc.docstatus === 0 ? ke_patient_share(frm.doc) : frm.doc.outstanding_amount;
		if (
			frm.doc.patient &&
			!frm.is_new() &&
			!frm.doc.is_return &&
			!frm.doc.is_pos &&
			frm.doc.docstatus < 2 &&
			due > 0 &&
			!frappe.boot.ke_payment_blocked
		) {
			frm.add_custom_button(__("Take Payment"), () =>
				royce_health_ke.take_payment({
					invoice: frm.doc.name,
					company: frm.doc.company,
					due,
					currency: frm.doc.currency,
					on_paid: () => frm.reload_doc(),
				}),
			).addClass("btn-primary");
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

// What the patient owes on a draft bill: the total less the insurer's share.
function ke_patient_share(doc) {
	return flt((doc.rounded_total || doc.grand_total) - flt(doc.total_insurance_coverage_amount));
}
