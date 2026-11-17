// Copyright (c) 2026, Royce Technologies LTD and contributors
// For license information, please see license.txt

const STATIONS = [
	"Triage",
	"Consultation",
	"Casualty",
	"Laboratory",
	"Radiology",
	"Pharmacy",
	"Procedure Room",
	"Cashier",
	"Admission",
];

frappe.ui.form.on("Patient Visit", {
	setup(frm) {
		frm.set_query("insurance_policy", () => ({
			filters: { patient: frm.doc.patient, insurance_payor: frm.doc.insurance_payor, docstatus: 1 },
		}));
		frm.set_query("insurance_plan", () => ({ filters: { insurance_payor: frm.doc.insurance_payor } }));
		frm.set_query("practitioner", () => ({ filters: { status: "Active" } }));
	},

	refresh(frm) {
		if (!frm.is_new()) render_bill(frm);
		if (frm.is_new() || frm.doc.status !== "Open") return;
		const call = (method, args, message) =>
			frappe.call({ method: `royce_health_ke.visits.${method}`, args, freeze: true }).then(() => {
				if (message) frappe.show_alert({ message, indicator: "green" });
				frm.reload_doc();
			});

		if (frm.doc.queue_status === "Waiting") {
			frm.add_custom_button(__("Seen"), () => call("acknowledge", { visit: frm.doc.name }, __("Seen"))).addClass(
				"btn-primary",
			);
		}
		frm.add_custom_button(__("Send To"), () => send_to_dialog(frm, call));

		const make = (doctype, label, values) =>
			frm.add_custom_button(label, () => frappe.new_doc(doctype, values), __("Record"));
		make("Vital Signs", __("Vital Signs"), {
			patient: frm.doc.patient,
			company: frm.doc.company,
			ke_patient_visit: frm.doc.name,
		});
		make("Patient Encounter", __("Consultation"), {
			patient: frm.doc.patient,
			practitioner: frm.doc.practitioner,
			appointment_type: frm.doc.appointment_type,
			medical_department: frm.doc.department,
			company: frm.doc.company,
			ke_patient_visit: frm.doc.name,
		});
		if (frm.doc.vital_signs) {
			frm.add_custom_button(__("Latest Vital Signs"), () => frappe.set_route("Form", "Vital Signs", frm.doc.vital_signs), __("View"));
		}
		if (frm.doc.encounter) {
			frm.add_custom_button(__("Latest Consultation"), () => frappe.set_route("Form", "Patient Encounter", frm.doc.encounter), __("View"));
		}
		frm.add_custom_button(__("Complete Visit"), () =>
			frappe.confirm(__("Complete this visit? The patient leaves every waiting list."), () =>
				call("complete", { visit: frm.doc.name }, __("Visit completed")),
			),
		__("Status"));
		frm.add_custom_button(__("Cancel Visit"), () =>
			frappe.prompt({ fieldname: "reason", fieldtype: "Small Text", label: __("Reason"), reqd: 1 }, (v) =>
				call("cancel", { visit: frm.doc.name, reason: v.reason }, __("Visit cancelled")),
			),
		__("Status"));

		if (frm.doc.current_station === "Consultation" && frm.doc.practitioner) {
			const where = [frm.doc.practitioner_name || frm.doc.practitioner, frm.doc.consultation_room, frm.doc.appointment_type]
				.filter(Boolean)
				.join(" · ");
			frm.dashboard.add_comment(__("Consultation: {0}", [where]), "blue", true);
			if (frm.doc.queue_status === "Waiting") {
				frm.add_custom_button(
					__("Reassign Doctor"),
					() =>
						frappe.confirm(__("Give this patient to the next doctor on duty? They keep their place in the queue."), () =>
							frappe
								.call({ method: "royce_health_ke.visits.reassign", args: { visit: frm.doc.name }, freeze: true })
								.then(({ message: r }) => {
									if (r) frappe.show_alert({ message: sent_message(r), indicator: "green" }, 8);
									frm.reload_doc();
								}),
						),
					__("Status"),
				);
			}
		}
		frm.add_custom_button(__("Queue Slip"), () => frm.print_doc(), __("View"));
		if (frm.doc.allow_credit) {
			frm.dashboard.add_comment(__("Services before payment approved: {0}", [frm.doc.credit_reason || ""]), "blue", true);
		}
		if (frm.doc.fee_first && !frm.doc.fee_paid && !frm.doc.allow_credit) {
			frm.dashboard.set_headline(
				__("Consultation fee to pay at the Cashier: the patient joins the triage list once it is paid."),
				"orange",
			);
		}
		if (frm.doc.vitals_status === "Abnormal") {
			frm.dashboard.set_headline(__("Abnormal vitals at triage. See the latest vital signs."), "red");
		}
	},

	patient(frm) {
		if (frm.doc.patient && frm.doc.payment_method === "Insurance") fill_policy(frm);
	},
	payment_method(frm) {
		if (frm.doc.patient && frm.doc.payment_method === "Insurance") fill_policy(frm);
	},
	insurance_payor(frm) {
		if (frm.doc.patient && frm.doc.payment_method === "Insurance") fill_policy(frm);
	},
	insurance_policy(frm) {
		if (!frm.doc.insurance_policy) return;
		frappe.db
			.get_value("Patient Insurance Policy", frm.doc.insurance_policy, [
				"insurance_payor",
				"insurance_plan",
				"policy_number",
				"ke_relation",
				"ke_principal_member",
				"ke_principal_member_number",
				"policy_expiry_date",
			])
			.then(({ message: p }) => {
				if (!p) return;
				frm.set_value({
					insurance_payor: p.insurance_payor,
					insurance_plan: p.insurance_plan,
					member_number: p.policy_number,
					policy_expiry: p.policy_expiry_date,
					relation: p.ke_relation || "Principal",
					principal_member: p.ke_principal_member,
					principal_member_number: p.ke_principal_member_number,
				});
			});
	},
});

// Reception types the member number; a returning member's details are filled
// in from their policy with the chosen payer (or their only policy). The
// policy itself is found, or created, from the payer and member number on save.
function fill_policy(frm) {
	if (frm.doc.insurance_policy || frm.doc.member_number) return;
	frappe.call("royce_health_ke.visits.patient_policies", { patient: frm.doc.patient }).then(({ message }) => {
		const all = message || [];
		const policies = frm.doc.insurance_payor ? all.filter((p) => p.insurance_payor === frm.doc.insurance_payor) : all;
		if (policies.length === 1) {
			const p = policies[0];
			frm.set_value({
				insurance_payor: p.insurance_payor,
				insurance_plan: p.insurance_plan,
				member_number: p.policy_number,
				policy_expiry: p.policy_expiry_date,
				relation: p.ke_relation || "Principal",
				principal_member: p.ke_principal_member,
				principal_member_number: p.ke_principal_member_number,
			});
		} else if (policies.length > 1) {
			frappe.show_alert({
				message: __("This patient has {0} active policies: choose the payer and type the member number.", [policies.length]),
				indicator: "blue",
			});
		}
	});
}

function send_to_dialog(frm, call) {
	const d = new frappe.ui.Dialog({
		title: __("Send {0} to", [frm.doc.patient_name]),
		fields: [
			{
				fieldname: "station",
				fieldtype: "Select",
				label: __("Station"),
				options: STATIONS.filter((s) => s !== frm.doc.current_station || frm.doc.queue_status !== "Waiting"),
				reqd: 1,
				// Triage sends on to the doctor; uncovered orders of an insured patient go to the cashier first.
				default:
					frm.doc.current_station === "Triage"
						? "Consultation"
						: frm.__ke_patient_now > 0 || frm.__ke_cash_to_bill
							? "Cashier"
							: undefined,
			},
			{
				fieldname: "practitioner",
				fieldtype: "Link",
				options: "Healthcare Practitioner",
				label: __("Practitioner"),
				default: frm.doc.practitioner,
				depends_on: "eval:doc.station == 'Consultation'",
				description: __("Leave blank to assign the next doctor on duty."),
			},
			{ fieldname: "note", fieldtype: "Data", label: __("Note") },
		],
		primary_action_label: __("Send"),
		primary_action(v) {
			d.hide();
			frappe
				.call({ method: "royce_health_ke.visits.send_to", args: { visit: frm.doc.name, ...v }, freeze: true })
				.then(({ message: r }) => {
					frappe.show_alert({ message: sent_message(r || { station: v.station }), indicator: "green" }, 8);
					frm.reload_doc();
				});
		},
	});
	d.show();
}

// "Sent to Dr Amina Otieno, OPD Room 1"
function sent_message(r) {
	if (r.redirected_from) {
		return __("Sent to the Cashier first: the {0} requests are not paid. The patient goes on to {0} once paid.", [
			__(r.redirected_from),
		]);
	}
	if (r.station === "Consultation" && r.practitioner) {
		return r.room
			? __("Sent to {0}, {1}", [r.practitioner_name || r.practitioner, r.room])
			: __("Sent to {0}", [r.practitioner_name || r.practitioner]);
	}
	return __("Sent to {0}", [__(r.station)]);
}

const money = (value, currency) => format_currency(value || 0, currency);
// What a charge is, in the words the cashier uses.
const CHARGE_KINDS = {
	"Patient Visit": __("Consultation fee"),
	"Patient Appointment": __("Consultation fee"),
	"Patient Encounter": __("Consultation"),
	"Service Request": __("Request"),
	"Medication Request": __("Drug"),
	"Lab Test": __("Lab test"),
	Observation: __("Imaging exam"),
	"Clinical Procedure": __("Procedure"),
	"Inpatient Occupancy": __("Bed"),
};
const charge_kind = (dt) => CHARGE_KINDS[dt] || __(dt || "");

// The running bill: unbilled charges at the prices the invoice will use, the
// visit's invoices, and what is left to pay. Create Bill hands the cashier a
// draft invoice of the unbilled charges.
function render_bill(frm) {
	const wrapper = frm.get_field("bill_html").$wrapper;
	wrapper.html(`<div class="text-muted small">${__("Loading the bill...")}</div>`);
	frappe.call("royce_health_ke.visit_bill.visit_bill", { visit: frm.doc.name }).then(({ message: b }) => {
		if (!b) return;
		if (b.error) {
			wrapper.html(`<div class="text-muted">${frappe.utils.escape_html(b.error)}</div>`);
			return;
		}
		const c = b.currency;
		const esc = frappe.utils.escape_html;
		frm.__ke_patient_now = b.patient_now;
		// a cash patient with requests to bill is sent to the Cashier
		frm.__ke_cash_to_bill = frm.doc.payment_method === "Cash" && b.charges.some((r) => !r.on_draft);
		// lines already on a draft bill are shown with that bill, not here
		const pending = b.charges.filter((r) => !r.on_draft);
		let html = "";
		if (pending.length) {
			html += `<p class="text-muted small mb-1">${__("Not billed yet")}</p>
				<table class="table table-sm table-bordered mb-3"><thead><tr>
				<th>${__("Item")}</th><th class="text-right">${__("Qty")}</th>
				<th class="text-right">${__("Rate")}</th><th class="text-right">${__("Amount")}</th>
				${b.insurance || pending.some((r) => r.insurance) ? `<th class="text-right">${__("Insurance")}</th>` : ""}
				</tr></thead><tbody>
				${pending
					.map(
						(r) => `<tr><td>${esc(r.item)}<div class="text-muted small">${esc(charge_kind(r.reference_dt))}${
							b.split
								? r.covered
									? ` · ${__("Insurer's bill")}`
									: ` · <span class="text-danger">${__("Not covered: patient pays first")}</span>`
								: ""
						}</div></td>
						<td class="text-right">${r.qty}</td><td class="text-right">${money(r.rate, c)}</td>
						<td class="text-right">${money(r.amount, c)}</td>
						${pending.some((x) => x.insurance) ? `<td class="text-right">${money(r.insurance, c)}</td>` : ""}</tr>`,
					)
					.join("")}
				<tr><td colspan="3" class="text-right"><b>${__("Total to bill (with tax)")}</b></td>
				<td class="text-right"><b>${money(b.unbilled_total, c)}</b></td></tr>
				</tbody></table>`;
		}
		if (b.invoices.length) {
			html += `<p class="text-muted small mb-1">${__("Invoices")}</p>
				<table class="table table-sm table-bordered mb-3"><thead><tr>
				<th>${__("Invoice")}</th><th>${__("Status")}</th>
				<th class="text-right">${__("Total")}</th>${b.insurance ? `<th class="text-right">${__("Insurance")}</th>` : ""}
				<th class="text-right">${__("Balance")}</th></tr></thead><tbody>
				${b.invoices
					.map(
						(i) => `<tr><td><a href="/app/sales-invoice/${encodeURIComponent(i.name)}">${esc(i.name)}</a></td>
						<td>${esc(__(i.docstatus ? i.status : "Draft"))}</td>
						<td class="text-right">${money(i.grand_total, c)}</td>
						${b.insurance ? `<td class="text-right">${money(i.total_insurance_coverage_amount, c)}</td>` : ""}
						<td class="text-right">${i.docstatus ? money(i.outstanding_amount, c) : ""}</td></tr>`,
					)
					.join("")}
				</tbody></table>`;
		}
		if ((b.approvals || []).length) {
			const colours = { Pending: "orange", Approved: "green", Rejected: "red" };
			html += `<p class="text-muted small mb-1">${__("Approvals")}</p>
				<table class="table table-sm table-bordered mb-3"><tbody>
				${b.approvals
					.map(
						(a) => `<tr><td><a href="/app/bill-approval-request/${encodeURIComponent(a.name)}">${esc(a.name)}</a></td>
						<td>${esc(__(a.request_type))}${a.discount_percentage ? " " + esc(a.discount_percentage) + "%" : a.amount ? " " + money(a.amount, c) : ""}</td>
						<td>${esc(a.reason || "")}</td>
						<td><span class="indicator-pill ${colours[a.status]} no-indicator-dot">${esc(__(a.status))}</span></td></tr>`,
					)
					.join("")}
				</tbody></table>`;
		}
		if (!html) {
			html = `<div class="text-muted">${__("No charges yet.")}</div>`;
		} else {
			html += `<div class="d-flex flex-wrap" style="gap: 24px">
				<div>${__("Billed")}: <b>${money(b.billed, c)}</b></div>
				${b.insurance ? `<div>${__("Insurance")}: <b>${money(b.insurance, c)}</b></div>` : ""}
				<div>${__("Paid")}: <b>${money(b.paid, c)}</b></div>
				<div>${__("To pay")}: <b class="${b.to_pay > 0 ? "text-danger" : ""}">${money(b.to_pay, c)}</b></div>
				${b.patient_now ? `<div>${__("Patient pays now")}: <b class="text-danger">${money(b.patient_now, c)}</b></div>` : ""}
			</div>`;
		}
		wrapper.html(html);
		if (b.status !== (frm.doc.bill_status || "")) {
			frm.doc.bill_status = b.status; // saved on the server already
			frm.refresh_field("bill_status");
		}

		if (frm.doc.status !== "Open") return;
		if (b.can_bill && pending.length && (!b.split || b.patient_now > 0)) {
			const billable = b.split ? pending.filter((r) => !r.covered) : pending;
			frm.add_custom_button(__("Create Bill"), () => bill_dialog(frm, billable, c), __("Bill"));
		}
		const payable = b.invoices.filter((i) => !i.is_return && i.docstatus < 2 && patient_due(i) > 0.005);
		if (b.can_bill && payable.length && !frappe.boot.ke_payment_blocked) {
			frm.add_custom_button(__("Take Payment"), () => take_payment(frm, payable, c), __("Bill"));
		}
		if (b.can_request) {
			const drafts = b.invoices.filter((i) => !i.docstatus && !i.is_return).map((i) => i.name);
			const owing = b.invoices.filter((i) => i.docstatus === 1 && i.outstanding_amount > 0).map((i) => i.name);
			if (drafts.length) {
				frm.add_custom_button(__("Request Discount"), () => request_approval(frm, "Discount", drafts), __("Bill"));
			}
			if (owing.length) {
				frm.add_custom_button(__("Request Waiver"), () => request_approval(frm, "Waiver", owing), __("Bill"));
			}
			if (!frm.doc.allow_credit && !b.can_approve_credit) {
				frm.add_custom_button(__("Request Pay Later"), () => request_approval(frm, "Pay Later", []), __("Bill"));
			}
		}
		if (b.can_approve_credit && !frm.doc.allow_credit) {
			frm.add_custom_button(
				__("Allow Services Before Payment"),
				() =>
					frappe.prompt(
						{ fieldname: "reason", fieldtype: "Small Text", label: __("Reason"), reqd: 1 },
						(v) =>
							frappe
								.call({
									method: "royce_health_ke.visit_bill.approve_credit",
									args: { visit: frm.doc.name, reason: v.reason },
									freeze: true,
								})
								.then(() => frm.reload_doc()),
						__("Serve this visit before payment"),
					),
				__("Bill"),
			);
		}
	});
}

// Take Payment on one of the visit's bills (the only one, or the one chosen).
// What the patient still owes on a bill (a draft: its total less the insurer's share).
const patient_due = (i) =>
	i.docstatus === 1 ? i.outstanding_amount : i.grand_total - (i.total_insurance_coverage_amount || 0);

function take_payment(frm, payable, currency) {
	const due = patient_due;
	const pay = (i) =>
		royce_health_ke.take_payment({
			invoice: i.name,
			company: frm.doc.company,
			due: due(i),
			currency,
			on_paid: () => frm.reload_doc(),
		});
	if (payable.length === 1) return pay(payable[0]);
	frappe.prompt(
		{
			fieldname: "invoice",
			fieldtype: "Select",
			label: __("Bill"),
			options: payable.map((i) => ({ value: i.name, label: `${i.name}: ${money(due(i), currency)}` })),
			default: payable[0].name,
			reqd: 1,
		},
		(v) => pay(payable.find((i) => i.name === v.invoice)),
		__("Which bill?"),
		__("Next"),
	);
}

function request_approval(frm, type, invoices) {
	const fields = [];
	if (type !== "Pay Later") {
		fields.push({
			fieldname: "sales_invoice",
			fieldtype: "Select",
			label: __("Bill"),
			options: invoices.join("\n"),
			default: invoices[0],
			reqd: 1,
		});
	}
	if (type === "Discount") {
		fields.push(
			{ fieldname: "discount_percentage", fieldtype: "Percent", label: __("Discount %") },
			{ fieldname: "amount", fieldtype: "Currency", label: __("Or an amount off") },
		);
	}
	if (type === "Waiver") {
		fields.push({
			fieldname: "amount",
			fieldtype: "Currency",
			label: __("Amount to waive"),
			description: __("Blank: the whole balance."),
		});
	}
	fields.push({ fieldname: "reason", fieldtype: "Small Text", label: __("Reason"), reqd: 1 });
	frappe.prompt(
		fields,
		(v) =>
			frappe
				.call({
					method: "royce_health_ke.approvals.request",
					args: { visit: frm.doc.name, request_type: type, ...v },
					freeze: true,
				})
				.then(({ message }) => {
					frappe.show_alert({ message: __("{0} sent to a manager for approval.", [message]), indicator: "green" });
					frm.reload_doc();
				}),
		__("Request {0}", [__(type)]),
		__("Send for Approval"),
	);
}

// The billing desk: the charges not billed yet, all ticked; untick what the
// patient isn't paying for now. Unticked charges stay to bill later, and an
// unpaid request stays off its service point's worklist.
function bill_dialog(frm, charges, currency) {
	if (!charges.length) return make_bill(frm);
	const esc = frappe.utils.escape_html;
	const d = new frappe.ui.Dialog({
		title: __("Bill {0}", [frm.doc.patient_name]),
		size: "large",
		fields: [{ fieldname: "lines", fieldtype: "HTML" }],
		primary_action_label: __("Create Invoice"),
		primary_action() {
			const ticked = [];
			d.$wrapper.find(".ke-bill-line:checked").each((i, el) => {
				const r = charges[$(el).data("idx")];
				ticked.push([r.reference_dt, r.reference_dn]);
			});
			if (!ticked.length) {
				frappe.msgprint(__("Tick at least one charge to bill."));
				return;
			}
			d.hide();
			make_bill(frm, ticked.length === charges.length ? null : ticked);
		},
	});
	d.fields_dict.lines.$wrapper.html(`
		<table class="table table-sm table-bordered">
			<thead><tr>
				<th style="width:32px"><input type="checkbox" class="ke-bill-all" checked></th>
				<th>${__("Requested")}</th><th class="text-right">${__("Qty")}</th>
				<th class="text-right">${__("Amount")}</th>
			</tr></thead>
			<tbody>${charges
				.map(
					(r, i) => `<tr>
					<td><input type="checkbox" class="ke-bill-line" data-idx="${i}" checked></td>
					<td>${esc(r.item)}<div class="text-muted small">${esc(charge_kind(r.reference_dt))}</div></td>
					<td class="text-right">${r.qty}</td>
					<td class="text-right">${money(r.amount, currency)}</td></tr>`,
				)
				.join("")}
			<tr><td></td><td colspan="2" class="text-right"><b>${__("Total to bill")}</b></td>
				<td class="text-right"><b class="ke-bill-total"></b></td></tr>
			</tbody>
		</table>
		<div class="text-muted small">${__(
			"Untick what the patient is not paying for now: it stays on the visit to bill later, and the service point sees a request only once it is paid. Taxes are added on the invoice.",
		)}</div>`);
	const total = () => {
		let sum = 0;
		d.$wrapper.find(".ke-bill-line:checked").each((i, el) => (sum += flt(charges[$(el).data("idx")].amount)));
		d.$wrapper.find(".ke-bill-total").text(format_currency(sum, currency));
		const lines = d.$wrapper.find(".ke-bill-line");
		d.$wrapper.find(".ke-bill-all").prop("checked", lines.length === lines.filter(":checked").length);
	};
	d.$wrapper.on("change", ".ke-bill-line", total);
	d.$wrapper.on("change", ".ke-bill-all", (e) => {
		d.$wrapper.find(".ke-bill-line").prop("checked", $(e.currentTarget).prop("checked"));
		total();
	});
	total();
	d.show();
}

function make_bill(frm, lines) {
	frappe.call({
		method: "royce_health_ke.visit_bill.make_bill",
		// every charge ticked: send no list, and the server bills them all
		args: lines ? { visit: frm.doc.name, lines } : { visit: frm.doc.name },
		freeze: true,
	}).then(
		({ message }) => {
			if (!message) return;
			if (message.existing) {
				frappe.show_alert({ message: __("This visit already has a draft bill for the patient."), indicator: "blue" });
				frappe.set_route("Form", "Sales Invoice", message.existing);
				return;
			}
			const doc = frappe.model.sync(message)[0];
			frappe.set_route("Form", doc.doctype, doc.name);
		},
	);
}
