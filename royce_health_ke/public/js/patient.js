// Copyright (c) 2026, Royce Technologies LTD and contributors
// For license information, please see license.txt

frappe.ui.form.on("Patient", {
	refresh(frm) {
		if (frm.is_new()) return;
		if (frappe.model.can_read("Patient Record Access")) {
			frm.add_custom_button(
				__("Who Opened This Record"),
				() => frappe.set_route("List", "Patient Record Access", { patient: frm.doc.name }),
				__("View")
			);
		}
		if (frappe.boot.ke_sms) {
			if (frm.perm[0] && frm.perm[0].write) {
				frm.add_custom_button(__("Send SMS"), () => send_sms_dialog(frm), __("SMS"));
			}
			if (frappe.model.can_read("Bulk SMS Log")) {
				frm.add_custom_button(
					__("SMS History"),
					() =>
						frappe.set_route("List", "Bulk SMS Log", {
							reference_doctype: "Patient",
							reference_name: frm.doc.name,
						}),
					__("SMS")
				);
			}
		}
	},
});

function sms_units(text) {
	const n = (text || "").length;
	if (n <= 160) return 1;
	if (n <= 306) return 2;
	return Math.ceil(n / 153);
}

// Ready-made wording for the commonest one-off messages; staff can edit.
function sms_templates(info) {
	const name = info.first_name || "";
	const at = info.facility || info.hospital || __("the hospital");
	const call = info.phone ? " " + __("Call {0}.", [info.phone]) : "";
	return {
		[__("Please call us")]: __("Dear {0}, {1} would like to speak with you.", [name, at]) + call,
		[__("Results ready")]: __("Dear {0}, your results are ready at {1}. Please see your clinician.", [
			name,
			at,
		]) + call,
		[__("Missed appointment")]: __(
			"Dear {0}, we missed you at your appointment at {1}. Please contact us to book another.",
			[name, at]
		) + call,
		[__("Medicine ready")]: __("Dear {0}, your medicine is ready for collection at {1}.", [name, at]) + call,
	};
}

function send_sms_dialog(frm) {
	frappe.call({
		method: "royce_health_ke.sms.patient_sms_info",
		args: { patient: frm.doc.name },
		callback(r) {
			const info = r.message || {};
			if (!info.enabled) {
				frappe.msgprint(__("SMS is switched off. Enable it in Bulk SMS Settings first."));
				return;
			}
			if (!info.mobile) {
				frappe.msgprint(__("This patient has no mobile number. Add one to the record first."));
				return;
			}
			const templates = sms_templates(info);
			const warning = info.consent
				? ""
				: `<div class="alert alert-warning" style="margin-bottom:0">${__(
						"This patient has not agreed to receive SMS. Send only if it's about their care."
				  )}</div>`;

			const d = new frappe.ui.Dialog({
				title: __("SMS to {0}", [frm.doc.patient_name]),
				fields: [
					{ fieldtype: "Data", fieldname: "to", label: __("To"), read_only: 1, default: info.mobile },
					{ fieldtype: "HTML", fieldname: "warning", options: warning },
					{
						fieldtype: "Select",
						fieldname: "template",
						label: __("Start From"),
						options: [""].concat(Object.keys(templates)),
						change() {
							const t = d.get_value("template");
							if (t) d.set_value("message", templates[t]);
						},
					},
					{
						fieldtype: "Small Text",
						fieldname: "message",
						label: __("Message"),
						reqd: 1,
						description: __("Don't include results or diagnoses: phones are not private."),
					},
					{ fieldtype: "HTML", fieldname: "count" },
				],
				primary_action_label: __("Send"),
				primary_action(values) {
					d.get_primary_btn().prop("disabled", true);
					frappe.call({
						method: "royce_health_ke.sms.send_to_patient",
						args: { patient: frm.doc.name, message: values.message },
						freeze: true,
						freeze_message: __("Sending..."),
						callback(res) {
							d.hide();
							const m = res.message || {};
							frappe.show_alert(
								{
									message: __("SMS sent ({0} unit(s), KES {1}).", [
										m.sms_units || 1,
										format_number(m.cost || 0, null, 2),
									]),
									indicator: "green",
								},
								7
							);
						},
						always() {
							d.get_primary_btn().prop("disabled", false);
						},
					});
				},
			});

			const update_count = () => {
				const text = d.get_value("message") || "";
				d.fields_dict.count.$wrapper.html(
					`<div class="text-muted small">${__("{0} characters = {1} SMS", [
						text.length,
						sms_units(text),
					])}</div>`
				);
			};
			d.fields_dict.message.$input.on("input", update_count);
			d.fields_dict.message.df.change = update_count;
			update_count();
			d.show();
		},
	});
}
