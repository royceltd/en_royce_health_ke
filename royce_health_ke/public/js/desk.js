// Copyright (c) 2026, Royce Technologies LTD and contributors
// For license information, please see license.txt

// Success messages close by themselves: a dialog showing only green messages
// with nothing to choose closes after a few seconds, so staff don't stop to
// dismiss it. A warning, an error or a question in it keeps it open.
(() => {
	const SECONDS = 5;
	const original = frappe.msgprint;
	let shown = 0;

	const as_data = (msg) => {
		if ($.isPlainObject(msg)) return msg;
		if (typeof msg === "string" && msg[0] === "{") {
			try {
				return JSON.parse(msg);
			} catch (e) {
				return {};
			}
		}
		return {};
	};
	const is_success = (data) => data.indicator === "green" && !data.primary_action && !data.secondary_action;

	frappe.msgprint = function (msg) {
		// The dialog empties when it closes: empty now means this message starts it.
		const area = frappe.msg_dialog && frappe.msg_dialog.msg_area;
		const fresh = !area || !area.contents().length;
		const dialog = original.apply(this, arguments);
		// A list of messages comes back here one by one, and a toast shows no
		// dialog: only a message put in the dialog counts.
		if (!dialog) return dialog;
		try {
			if (fresh) dialog.__ke_keep = false;
			if (!is_success(as_data(msg))) {
				dialog.__ke_keep = true;
				return dialog;
			}
			const token = ++shown;
			dialog.__ke_close_token = token;
			setTimeout(() => {
				if (dialog.__ke_close_token === token && !dialog.__ke_keep && dialog.display) dialog.hide();
			}, SECONDS * 1000);
		} catch (e) {
			console.error(e);
		}
		return dialog;
	};
})();

// Take Payment (visit Bill and the patient's invoice): the cashier types what
// the patient hands over; the bill is paid (or part of it) and the change shows.
// Change is given only for cash. After paying, the receipt prints.
frappe.provide("royce_health_ke");
royce_health_ke.take_payment = ({ invoice, company, due, currency, on_paid }) => {
	const money = (v) => format_currency(v || 0, currency);
	frappe.xcall("royce_health_ke.cashier.payment_modes", { company }).then((modes) => {
		if (!modes.length) {
			frappe.msgprint(__("Set up a Mode of Payment with an account for {0} first.", [company]));
			return;
		}
		const is_cash = (mode) => (modes.find((m) => m.name === mode) || {}).type === "Cash";
		let d = null; // field change events may fire while the dialog is being made
		d = new frappe.ui.Dialog({
			title: __("Take Payment: {0}", [invoice]),
			fields: [
				{ fieldtype: "HTML", fieldname: "due_html" },
				{
					fieldname: "mode_of_payment",
					fieldtype: "Select",
					label: __("Paid By"),
					options: modes.map((m) => m.name),
					default: modes[0].name,
					reqd: 1,
					change: () => d && update(),
				},
				{
					fieldname: "amount_received",
					fieldtype: "Currency",
					label: __("Amount Received"),
					options: currency,
					default: due,
					reqd: 1,
					change: () => d && update(),
				},
				{
					fieldname: "reference_no",
					fieldtype: "Data",
					label: __("Transaction Code"),
					description: __("The M-Pesa, card or bank code."),
					depends_on: `eval:!${JSON.stringify(modes.filter((m) => m.type === "Cash").map((m) => m.name))}.includes(doc.mode_of_payment)`,
				},
				{ fieldtype: "HTML", fieldname: "change_html" },
			],
			primary_action_label: __("Take Payment"),
			primary_action(v) {
				const cash = is_cash(v.mode_of_payment);
				if (!cash && !v.reference_no) {
					frappe.msgprint(__("Enter the transaction code."));
					return;
				}
				d.disable_primary_action();
				frappe
					.call({
						method: "royce_health_ke.cashier.take_payment",
						args: { invoice, ...v },
						freeze: true,
						freeze_message: __("Taking payment..."),
					})
					.then(({ message: r }) => {
						d.hide();
						paid_message(r);
						on_paid && on_paid(r);
					})
					.always(() => d.enable_primary_action());
			},
		});
		const update = () => {
			const v = d.get_values(true) || {};
			const received = flt(v.amount_received);
			let html = "";
			if (is_cash(v.mode_of_payment) && received > due) {
				html = `<div class="alert alert-success mb-0" style="font-size: 1.25em">${__("Change to give")}: <b>${money(received - due)}</b></div>`;
			} else if (received > due) {
				html = `<div class="alert alert-danger mb-0">${__("More than owed: change is given only for cash.")}</div>`;
			} else if (received > 0 && received < due) {
				html = `<div class="alert alert-warning mb-0">${__("Part payment: {0} stays owed.", [money(due - received)])}</div>`;
			}
			d.fields_dict.change_html.$wrapper.html(html);
		};
		d.fields_dict.due_html.$wrapper.html(
			`<div class="mb-2" style="font-size: 1.25em">${__("To pay")}: <b>${money(due)}</b></div>`,
		);
		d.show();
		update();
	});

	function paid_message(r) {
		const lines = [`${__("Paid")}: <b>${money(r.paid)}</b>`];
		if (r.change > 0) {
			lines.push(`<span style="font-size: 1.4em">${__("Change to give")}: <b>${money(r.change)}</b></span>`);
		}
		if (r.balance > 0) lines.push(`${__("Still owed")}: <b>${money(r.balance)}</b>`);
		const d = frappe.msgprint({
			title: __("Payment taken"),
			message: lines.join("<br>"),
			indicator: "blue",
			primary_action: {
				label: __("Print Receipt"),
				action: () => {
					d.hide();
					const params = new URLSearchParams({
						doctype: "Sales Invoice",
						name: r.invoice,
						format: "Patient Receipt",
						no_letterhead: 1,
						trigger_print: 1,
					});
					window.open(`/printview?${params}`, "_blank");
				},
			},
		});
	}
};
