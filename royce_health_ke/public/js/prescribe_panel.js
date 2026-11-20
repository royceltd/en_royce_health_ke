/* global royce_health_ke */
// Copyright (c) 2026, Royce Technologies LTD and contributors
// For license information, please see license.txt

// The drug screen on the consultation's Prescription tab
// (royce_health_ke.DrugOrder in drug_order.js, royce_health_ke.prescribing).
// Each drug added is saved on the consultation as a draft, so the form is
// reloaded after every change (no "modified" clash on the doctor's next save).

frappe.ui.form.on("Patient Encounter", {
	refresh(frm) {
		ke_rx_panel(frm);
	},
});

function ke_rx_panel(frm) {
	const field = frm.fields_dict.ke_prescribe_html;
	if (!field) return;
	const $w = field.$wrapper.empty();
	if (frm.is_new()) {
		$w.html(
			`<p class="text-muted">${__("Save the consultation to prescribe from here.")}</p>`
		);
		return;
	}
	if (!(window.royce_health_ke && royce_health_ke.DrugOrder)) return;
	const order = new royce_health_ke.DrugOrder({
		wrapper: $w,
		get_encounter: async () => {
			if (frm.is_dirty()) await frm.save();
			return frm.doc.name;
		},
		on_sent: () => frm.reload_doc(),
		on_change: (info) => {
			frm.__ke_rx_note = info && info.mapping;
			frm.reload_doc();
		},
	});
	if (frm.__ke_rx_note) {
		order.show_mapping(frm.__ke_rx_note);
		frm.__ke_rx_note = null;
	}
}
