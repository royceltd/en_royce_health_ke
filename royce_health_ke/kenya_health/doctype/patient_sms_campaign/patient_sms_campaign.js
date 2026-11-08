// Copyright (c) 2026, Royce Technologies LTD and contributors
// For license information, please see license.txt

frappe.ui.form.on("Patient SMS Campaign", {
	refresh(frm) {
		if (frm.doc.docstatus === 0 && !frm.is_new()) {
			frm.add_custom_button(__("Preview Recipients & Cost"), () => preview(frm));
		}
		show_length(frm);
	},
	message(frm) {
		show_length(frm);
	},
	preview_recipients(frm) {
		preview(frm);
	},
});

function units(text) {
	const n = (text || "").length;
	if (n <= 160) return 1;
	if (n <= 306) return 2;
	return Math.ceil(n / 153);
}

function show_length(frm) {
	const n = (frm.doc.message || "").length;
	frm.set_df_property(
		"message",
		"description",
		__("{0} characters = {1} SMS per patient. Don't include results or diagnoses: phones are not private.", [
			n,
			units(frm.doc.message),
		])
	);
}

function preview(frm) {
	if (!frm.doc.message) {
		frappe.msgprint(__("Type the message first."));
		return;
	}
	if (frm.is_dirty()) {
		frappe.msgprint(__("Save your changes before previewing."));
		return;
	}
	frappe.call({
		method: "royce_health_ke.sms.preview_campaign",
		args: { name: frm.doc.name },
		freeze: true,
		freeze_message: __("Finding patients..."),
		callback(r) {
			if (!r.message) return;
			const d = r.message;
			frm.reload_doc();
			frappe.msgprint({
				title: __("Who will receive it"),
				indicator: d.recipient_count ? "blue" : "orange",
				message: __(
					"<b>{0}</b> patients (who agreed to SMS) match these filters.<br>Estimated <b>{1}</b> SMS units, about <b>KES {2}</b>.",
					[d.recipient_count, d.total_units, format_number(d.estimated_cost, null, 2)]
				),
			});
		},
	});
}
