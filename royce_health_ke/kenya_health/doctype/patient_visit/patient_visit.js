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
			])
			.then(({ message: p }) => {
				if (!p) return;
				frm.set_value({
					insurance_payor: p.insurance_payor,
					insurance_plan: p.insurance_plan,
					member_number: p.policy_number,
					relation: p.ke_relation || "Principal",
					principal_member: p.ke_principal_member,
					principal_member_number: p.ke_principal_member_number,
				});
			});
	},
});

// The patient's active policy, when there is exactly one.
function fill_policy(frm) {
	if (frm.doc.insurance_policy) return;
	frappe.call("royce_health_ke.visits.patient_policies", { patient: frm.doc.patient }).then(({ message }) => {
		if (message && message.length === 1) frm.set_value("insurance_policy", message[0].name);
		else if (message && message.length > 1)
			frappe.show_alert({ message: __("This patient has {0} active policies: choose one.", [message.length]), indicator: "blue" });
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
						: frm.__ke_patient_now > 0
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
	if (r.station === "Consultation" && r.practitioner) {
		return r.room
			? __("Sent to {0}, {1}", [r.practitioner_name || r.practitioner, r.room])
			: __("Sent to {0}", [r.practitioner_name || r.practitioner]);
	}
	return __("Sent to {0}", [__(r.station)]);
}

const money = (value, currency) => format_currency(value || 0, currency);

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
		let html = "";
		if (b.charges.length) {
			html += `<p class="text-muted small mb-1">${__("Not billed yet")}</p>
				<table class="table table-sm table-bordered mb-3"><thead><tr>
				<th>${__("Item")}</th><th class="text-right">${__("Qty")}</th>
				<th class="text-right">${__("Rate")}</th><th class="text-right">${__("Amount")}</th>
				${b.insurance || b.charges.some((r) => r.insurance) ? `<th class="text-right">${__("Insurance")}</th>` : ""}
				</tr></thead><tbody>
				${b.charges
					.map(
						(r) => `<tr><td>${esc(r.item)}<div class="text-muted small">${esc(__(r.reference_dt || ""))}${
							b.split
								? r.covered
									? ` · ${__("Insurer's bill")}`
									: ` · <span class="text-danger">${__("Not covered: patient pays first")}</span>`
								: ""
						}</div></td>
						<td class="text-right">${r.qty}</td><td class="text-right">${money(r.rate, c)}</td>
						<td class="text-right">${money(r.amount, c)}</td>
						${b.charges.some((x) => x.insurance) ? `<td class="text-right">${money(r.insurance, c)}</td>` : ""}</tr>`,
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
		if (b.can_bill && b.charges.length && (!b.split || b.patient_now > 0)) {
			frm.add_custom_button(__("Create Bill"), () => make_bill(frm), __("Bill"));
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

function make_bill(frm) {
	frappe.call({ method: "royce_health_ke.visit_bill.make_bill", args: { visit: frm.doc.name }, freeze: true }).then(
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
