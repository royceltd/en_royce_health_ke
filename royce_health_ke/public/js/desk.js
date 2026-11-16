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
