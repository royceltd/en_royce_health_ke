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
	Promise.all([
		frappe.xcall("royce_health_ke.cashier.payment_modes", { company }),
		frappe.xcall("royce_health_ke.cashier.payment_context", { invoice }),
	]).then(([modes, ctx]) => {
		if (!modes.length) {
			frappe.msgprint(__("Set up a Mode of Payment with an account for {0} first.", [company]));
			return;
		}
		const credit = flt(ctx.credit);
		const is_cash = (mode) => (modes.find((m) => m.name === mode) || {}).type === "Cash";
		// what is left to pay after the patient's credit, when used
		const owed = (v) => Math.max(flt(due) - (credit && v.use_credit ? credit : 0), 0);
		let d = null; // field change events may fire while the dialog is being made
		d = new frappe.ui.Dialog({
			title: __("Take Payment: {0}", [invoice]),
			fields: [
				{ fieldtype: "HTML", fieldname: "due_html" },
				{
					fieldname: "use_credit",
					fieldtype: "Check",
					label: __("Use the patient's credit of {0}", [money(credit)]),
					default: credit ? 1 : 0,
					hidden: credit ? 0 : 1,
					change: () => {
						if (!d) return;
						d.set_value("amount_received", owed(d.get_values(true) || {}));
						update();
					},
				},
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
					default: owed({ use_credit: credit ? 1 : 0 }),
					change: () => d && update(),
				},
				{
					fieldname: "reference_no",
					fieldtype: "Data",
					label: __("Transaction Code"),
					description: __("The M-Pesa, card or bank code."),
					depends_on: `eval:!${JSON.stringify(
						modes.filter((m) => m.type === "Cash").map((m) => m.name)
					)}.includes(doc.mode_of_payment)`,
				},
				{ fieldtype: "HTML", fieldname: "change_html" },
			],
			primary_action_label: __("Take Payment"),
			primary_action(v) {
				const cash = is_cash(v.mode_of_payment);
				if (flt(v.amount_received) > 0 && !cash && !v.reference_no) {
					frappe.msgprint(__("Enter the transaction code."));
					return;
				}
				if (!flt(v.amount_received) && owed(v) > 0) {
					frappe.msgprint(__("Enter the amount received."));
					return;
				}
				d.disable_primary_action();
				frappe
					.call({
						method: "royce_health_ke.cashier.take_payment",
						args: { invoice, ...v, use_credit: v.use_credit ? 1 : 0 },
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
		if (ctx.mpesa_prompt) {
			d.set_secondary_action_label(__("Send M-Pesa Prompt"));
			d.set_secondary_action(() => mpesa_prompt(d.get_values(true) || {}));
		}
		const update = () => {
			const v = d.get_values(true) || {};
			const received = flt(v.amount_received);
			const left = owed(v);
			let html = "";
			if (credit && v.use_credit) {
				html += `<div class="text-muted mb-2">${__("Credit used: {0}. Left to pay: {1}", [
					money(Math.min(credit, flt(due))),
					`<b>${money(left)}</b>`,
				])}</div>`;
			}
			if (is_cash(v.mode_of_payment) && received > left) {
				html += `<div class="alert alert-success mb-0" style="font-size: 1.25em">${__("Change to give")}: <b>${money(
					received - left
				)}</b></div>`;
			} else if (received > left) {
				html += `<div class="alert alert-info mb-0">${__(
					"More than owed: {0} stays on the patient's account as credit for the next bill.",
					[money(received - left)]
				)}</div>`;
			} else if (received > 0 && received < left) {
				html += `<div class="alert alert-warning mb-0">${__(
					"Part payment: {0} stays owed, and the lab, radiology and pharmacy wait until it is paid.",
					[money(left - received)]
				)}</div>`;
			}
			d.fields_dict.change_html.$wrapper.html(html);
		};
		d.fields_dict.due_html.$wrapper.html(
			`<div class="mb-2" style="font-size: 1.25em">${__("To pay")}: <b>${money(due)}</b></div>`
		);
		d.show();
		update();

		// STK push (royce_payments): the patient approves on their phone; the
		// payment is recorded against the bill when M-Pesa confirms it.
		function mpesa_prompt(v) {
			frappe.prompt(
				[
					{
						fieldname: "phone",
						fieldtype: "Data",
						label: __("Patient's M-Pesa number"),
						default: ctx.mobile,
						reqd: 1,
					},
					{
						fieldname: "amount",
						fieldtype: "Currency",
						label: __("Amount"),
						options: currency,
						default: owed(v),
						reqd: 1,
					},
				],
				(p) => {
					d.hide();
					frappe
						.xcall("royce_health_ke.cashier.mpesa_prompt", {
							invoice,
							phone: p.phone,
							amount: p.amount,
							use_credit: v.use_credit ? 1 : 0,
						})
						.then((r) => wait_for_mpesa(r));
				},
				__("Send M-Pesa Prompt"),
				__("Send")
			);
		}

		function wait_for_mpesa(r) {
			const w = frappe.msgprint({
				title: __("Waiting for M-Pesa"),
				message: __("{0} The patient enters their M-Pesa PIN on their phone.", [
					frappe.utils.escape_html(r.message || ""),
				]),
				indicator: "blue",
			});
			let tries = 0;
			const timer = setInterval(() => {
				tries += 1;
				frappe
					.xcall("royce_payments.daraja.stk.get_status", { name: r.name })
					.then((s) => {
						if (["Paid", "Received"].includes(s.status)) {
							clearInterval(timer);
							w.hide();
							frappe.msgprint({
								title: __("Payment taken"),
								message: __("M-Pesa {0} received.", [frappe.utils.escape_html(s.mpesa_receipt || "")]),
								indicator: "green",
							});
							on_paid && on_paid({ invoice: r.invoice });
						} else if (["Failed", "Cancelled", "Needs Review"].includes(s.status) || tries > 40) {
							clearInterval(timer);
							w.hide();
							frappe.msgprint({
								title: __("M-Pesa payment not completed"),
								message: frappe.utils.escape_html(
									s.result_desc || __("No answer from the phone yet. Check again later on the bill.")
								),
								indicator: "orange",
							});
							on_paid && on_paid({ invoice: r.invoice });
						}
					})
					.catch(() => tries > 40 && clearInterval(timer));
			}, 3000);
		}
	});

	function paid_message(r) {
		const lines = [`${__("Paid")}: <b>${money(r.paid)}</b>`];
		if (r.change > 0) {
			lines.push(`<span style="font-size: 1.4em">${__("Change to give")}: <b>${money(r.change)}</b></span>`);
		}
		if (r.credit_used > 0) lines.push(`${__("Paid from credit")}: <b>${money(r.credit_used)}</b>`);
		if (r.credit_added > 0) {
			lines.push(`${__("Kept as the patient's credit")}: <b>${money(r.credit_added)}</b>`);
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

// Idle screen lock (royce_health_ke.security, Kenya Health Settings > Idle
// Screen Lock): after N minutes without activity the desk is covered and
// blurred until the user types their password. Nothing is reloaded, so unsaved
// work stays on the page. Activity in any tab of this browser counts; one
// unlock frees every tab. Five wrong passwords log the user out.
(() => {
	const ACTIVE = "ke_last_activity";
	const UNLOCKED = "ke_unlocked_at";
	const store = {
		get: (k) => {
			try {
				return Number(localStorage.getItem(k)) || 0;
			} catch (e) {
				return 0;
			}
		},
		set: (k, v) => {
			try {
				localStorage.setItem(k, String(v));
			} catch (e) {
				// private window: this tab alone
			}
		},
	};
	let last = Date.now();
	let overlay = null;
	let failures = 0;

	const minutes = () => cint((frappe.boot || {}).ke_idle_lock_minutes);
	const active = () => Math.max(last, store.get(ACTIVE));

	let stamped = 0;
	function activity() {
		if (overlay) return;
		last = Date.now();
		if (last - stamped > 5000) {
			stamped = last;
			store.set(ACTIVE, last);
		}
	}

	function lock() {
		if (overlay || !frappe.session || frappe.session.user === "Guest") return;
		const name = frappe.utils.escape_html(frappe.session.user_fullname || frappe.session.user);
		overlay = $(`
			<div class="ke-idle-lock" style="position:fixed;inset:0;z-index:2147483000;display:flex;
				align-items:center;justify-content:center;background:rgba(0,0,0,0.35);
				backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px);">
				<form style="background:var(--card-bg, #fff);color:var(--text-color, #1f272e);
					border-radius:12px;padding:24px;width:min(360px,calc(100vw - 32px));
					box-shadow:0 10px 40px rgba(0,0,0,0.25);">
					<div style="font-size:1.1em;font-weight:600;margin-bottom:4px">${__("Screen locked")}</div>
					<div class="text-muted small" style="margin-bottom:16px">${__(
						"{0}, type your password to carry on. Your unsaved work is still here.",
						[name],
					)}</div>
					<input type="password" class="form-control" autocomplete="current-password"
						placeholder="${__("Password")}" required>
					<div class="ke-idle-error text-danger small" style="min-height:1.4em;margin-top:6px"></div>
					<div style="display:flex;justify-content:space-between;align-items:center;margin-top:8px">
						<a href="#" class="ke-idle-logout small">${__("Log out")}</a>
						<button type="submit" class="btn btn-primary btn-sm">${__("Unlock")}</button>
					</div>
				</form>
			</div>`).appendTo(document.body);
		const input = overlay.find("input");
		setTimeout(() => input.trigger("focus"), 50);
		overlay.find(".ke-idle-logout").on("click", (e) => {
			e.preventDefault();
			frappe.app.logout();
		});
		overlay.find("form").on("submit", (e) => {
			e.preventDefault();
			const error = overlay.find(".ke-idle-error").text("");
			frappe
				.call({
					method: "royce_health_ke.security.unlock",
					args: { password: input.val() },
					type: "POST",
					error_handlers: { 429: () => error.text(__("Too many tries. Wait a minute.")) },
				})
				.then(({ message }) => {
					if (message) {
						store.set(UNLOCKED, Date.now());
						unlock();
						return;
					}
					failures += 1;
					input.val("").trigger("focus");
					if (failures >= 5) {
						frappe.app.logout();
						return;
					}
					error.text(__("Wrong password ({0} of 5).", [failures]));
				})
				.fail((xhr) => {
					// the session ended on the server: log in again
					if (xhr && (xhr.status === 401 || xhr.status === 403)) {
						window.location.href =
							"/login?redirect-to=" + encodeURIComponent(window.location.pathname);
					}
				});
		});
	}

	function unlock() {
		if (!overlay) return;
		overlay.remove();
		overlay = null;
		failures = 0;
		activity();
	}

	function check() {
		const limit = minutes();
		if (!limit) return;
		if (!overlay && Date.now() - active() >= limit * 60 * 1000) lock();
	}

	["mousemove", "mousedown", "keydown", "scroll", "touchstart", "wheel"].forEach((event) =>
		window.addEventListener(event, activity, { passive: true, capture: true }),
	);
	window.addEventListener("storage", (e) => {
		if (e.key === UNLOCKED && overlay) unlock();
	});
	setInterval(check, 15000);
})();
