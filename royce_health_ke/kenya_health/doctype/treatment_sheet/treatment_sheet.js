// Copyright (c) 2026, Royce Technologies LTD and contributors
// For license information, please see license.txt

frappe.ui.form.on("Treatment Sheet", {
	setup(frm) {
		const drugs = () => ({ filters: { disabled: 0, is_stock_item: 1 } });
		frm.set_query("drug", "drugs", drugs);
		frm.set_query("drug", "once_only", drugs);
		frm.set_query("inpatient_record", () => ({ filters: { patient: frm.doc.patient } }));
	},
	refresh(frm) {
		if (frm.doc.medication_order) {
			frm.add_custom_button(__("Ward Medication Order"), () =>
				frappe.set_route("Form", "Inpatient Medication Order", frm.doc.medication_order),
			);
		}
		if (frm.doc.docstatus === 0 && !frm.doc.inpatient_record && frm.doc.patient) {
			frm.dashboard.add_comment(
				__("No admission: submitting keeps the sheet as a record but makes no ward medication order."),
				"orange",
				true,
			);
		}
	},
});
