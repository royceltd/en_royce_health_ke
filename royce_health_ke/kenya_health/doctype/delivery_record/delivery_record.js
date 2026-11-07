// Copyright (c) 2026, Royce Technologies LTD and contributors
// For license information, please see license.txt

frappe.ui.form.on("Delivery Record", {
	refresh(frm) {
		royce_health_ke_render_lcg(frm);
		if (!frm.is_new()) {
			frm.add_custom_button(__("Print Labour Care Guide"), () => {
				const url = `/printview?doctype=${encodeURIComponent(frm.doctype)}&name=${encodeURIComponent(frm.doc.name)}&format=${encodeURIComponent("Labour Care Guide")}&no_letterhead=1&trigger_print=1`;
				window.open(url, "_blank");
			});
		}
	},
});

function royce_health_ke_render_lcg(frm) {
	const field = frm.get_field("labour_care_guide");
	if (!field) return;
	if (frm.is_new() || !(frm.doc.labour_observations || []).length) {
		field.$wrapper.html(`<p class="text-muted small">${__("The Labour Care Guide chart appears here once observations are saved.")}</p>`);
		return;
	}
	frappe
		.xcall("royce_health_ke.lcg.labour_care_guide_html", { delivery: frm.doc.name })
		.then((html) => field.$wrapper.html(`<div style="overflow-x:auto">${html}</div>`));
}
