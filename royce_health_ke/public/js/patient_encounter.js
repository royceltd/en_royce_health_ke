// Copyright (c) 2026, Royce Technologies LTD and contributors
// For license information, please see license.txt

// Clinical decision support (royce_health_ke.cds): after a save, show the
// consultation's pending alerts; the clinician marks each "Acted on" or
// overrides it with a reason. Alerts never block saving or submitting.
const KE_ALERT_COLOURS = { Critical: "red", Warning: "orange", Info: "blue" };

frappe.ui.form.on("Patient Encounter", {
	setup(frm) {
		ke_request_queries(frm);
		ke_diagnosis_setup(frm);
	},
	refresh(frm) {
		if (!frm.is_new()) ke_show_clinical_alerts(frm);
		ke_consultation_refresh(frm);
		ke_may_consult(frm);
		ke_unsent_requests(frm);
		ke_latest_vitals(frm);
		ke_request_type(frm);
		// Admit to Ward (royce_health_ke.inpatient): the admission order with ward,
		// urgency, date, reason and notes; the patient goes to the ward's list
		if (
			!frm.is_new() &&
			!frm.doc.inpatient_record &&
			frappe.model.can_create("Inpatient Record")
		) {
			frm.add_custom_button(__("Admit to Ward"), () => ke_admit_dialog(frm));
		}
		if (frm.doc.patient && frappe.model.can_read("Vital Signs")) {
			frm.add_custom_button(
				__("Vital Signs History"),
				() => ke_vitals_history(frm.doc.patient),
				__("View")
			);
		}
	},
	ke_request_type(frm) {
		ke_request_type(frm);
	},
	patient(frm) {
		ke_may_consult(frm);
	},
	encounter_date(frm) {
		ke_may_consult(frm);
	},
	after_save(frm) {
		ke_show_clinical_alerts(frm, true);
	},
	ke_send_requests(frm) {
		ke_send_requests(frm);
	},
	ke_complete_consultation(frm) {
		ke_complete_consultation(frm);
	},
	before_submit(frm) {
		// Submit (or its shortcut) goes through Complete Consultation and its checks
		frappe.validated = false;
		ke_complete_consultation(frm);
	},
});

// ICD-11 diagnosis (royce_health_ke.diagnosis): one row, the name or the code
// searched, the other filled in. An ICD-11 title picked by name becomes a
// Diagnosis record on the server, so the name column skips link validation.
function ke_diagnosis_setup(frm) {
	// Only on a grid (forms.py makes the diagnosis a table). Marley's pill
	// picker (Table MultiSelect) has no grid: set_query on its rows threw and
	// left the consultation blank (v0.45.1).
	const grid = frm.fields_dict.diagnosis && frm.fields_dict.diagnosis.grid;
	if (!grid) return;
	frm.set_query("diagnosis", "diagnosis", () => ({
		query: "royce_health_ke.diagnosis.diagnosis_query",
	}));
	frm.set_query("ke_icd11_code", "diagnosis", () => ({
		query: "royce_health_ke.diagnosis.icd11_query",
	}));
	grid.update_docfield_property("diagnosis", "ignore_link_validation", 1);
}

function ke_resolve_diagnosis(frm, cdt, cdn, args) {
	const row = locals[cdt][cdn];
	if (row.__ke_resolving) return;
	frappe.xcall("royce_health_ke.diagnosis.resolve", args).then((r) => {
		if (!r || !r.diagnosis) return;
		row.__ke_resolving = true;
		const sets = [];
		if (row.diagnosis !== r.diagnosis)
			sets.push(frappe.model.set_value(cdt, cdn, "diagnosis", r.diagnosis));
		if (r.code_value && row.ke_icd11_code !== r.code_value)
			sets.push(frappe.model.set_value(cdt, cdn, "ke_icd11_code", r.code_value));
		Promise.all(sets).finally(() => (row.__ke_resolving = false));
	});
}

frappe.ui.form.on("Patient Encounter Diagnosis", {
	diagnosis(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (row.diagnosis) ke_resolve_diagnosis(frm, cdt, cdn, { diagnosis: row.diagnosis });
	},
	ke_icd11_code(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (row.ke_icd11_code)
			ke_resolve_diagnosis(frm, cdt, cdn, { code_value: row.ke_icd11_code });
	},
});

// Prescription in dispensing units (royce_health_ke.dispensing): the quantity
// is worked out from the dose, frequency and duration as the doctor types.
function ke_prescription_quantity(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	if (row.medication_request || !(row.medication || row.drug_code)) return;
	frappe
		.xcall("royce_health_ke.dispensing.quantity_for", {
			row: {
				medication: row.medication,
				drug_code: row.drug_code,
				ke_dose: row.ke_dose,
				ke_dose_uom: row.ke_dose_uom,
				dosage: row.dosage,
				period: row.period,
				interval: row.interval,
				interval_uom: row.interval_uom,
				dosage_by_interval: row.dosage_by_interval,
			},
		})
		.then((r) => {
			if (!r) return;
			frappe.model.set_value(cdt, cdn, "ke_quantity", r.quantity);
			if (r.unit) frappe.model.set_value(cdt, cdn, "ke_dispensing_unit", r.unit);
		});
}

frappe.ui.form.on("Drug Prescription", {
	drug_prescription_add(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.ke_start_date)
			frappe.model.set_value(cdt, cdn, "ke_start_date", frm.doc.encounter_date);
	},
	medication: ke_prescription_quantity,
	drug_code: ke_prescription_quantity,
	ke_dose: ke_prescription_quantity,
	ke_dose_uom: ke_prescription_quantity,
	dosage: ke_prescription_quantity,
	period: ke_prescription_quantity,
	interval: ke_prescription_quantity,
	interval_uom: ke_prescription_quantity,
	dosage_by_interval: ke_prescription_quantity,
});

// Request Type picker (royce_health_ke.routing): the request tables offer that
// type's templates only, each with this patient's price; other tables hide.
const KE_REQUEST_FIELDS = [
	["lab_test_prescription", "lab_test_code", "Lab Test"],
	["lab_test_prescription", "observation_template", "Imaging"],
	["procedure_prescription", "procedure", "Procedure"],
	["therapies", "therapy_type", "Therapy"],
];
const KE_REQUEST_SECTIONS = {
	lab_test_prescription: "sb_test_prescription",
	procedure_prescription: "sb_procedures",
	therapies: "rehabilitation_section",
};

function ke_request_queries(frm) {
	KE_REQUEST_FIELDS.forEach(([table, field, kind]) => {
		if (!(frm.fields_dict[table] && frm.fields_dict[table].grid)) return;
		frm.set_query(field, table, () => {
			const category = frm.doc.ke_request_type;
			const own = frm.__ke_request_kind;
			// a type of another kind leaves this column to its own kind's templates
			return {
				query: "royce_health_ke.routing.template_query",
				filters: {
					category: category && own === kind ? category : "",
					kind,
					encounter: frm.is_new() ? "" : frm.doc.name,
				},
			};
		});
	});
}

async function ke_request_type(frm) {
	if (!frm.fields_dict.ke_request_type) return;
	let kind = null;
	if (frm.doc.ke_request_type) {
		kind = await frappe.db.get_value(
			"Request Category",
			frm.doc.ke_request_type,
			"request_kind"
		);
		kind = kind && kind.message && kind.message.request_kind;
	}
	frm.__ke_request_kind = kind;
	const show = {};
	KE_REQUEST_FIELDS.forEach(([table, _field, k]) => {
		show[table] = show[table] || !kind || k === kind;
	});
	Object.entries(KE_REQUEST_SECTIONS).forEach(([table, section]) => {
		if (frm.fields_dict[section]) frm.toggle_display(section, show[table]);
	});
	const lab =
		frm.fields_dict.lab_test_prescription && frm.fields_dict.lab_test_prescription.grid;
	if (lab) {
		lab.update_docfield_property("lab_test_code", "hidden", kind === "Imaging" ? 1 : 0);
		lab.update_docfield_property(
			"observation_template",
			"hidden",
			kind === "Lab Test" ? 1 : 0
		);
		lab.refresh();
	}
}

// Requests added but not sent: they reach the Cashier and the lab only once
// sent (Send Requests) or when the consultation is completed.
function ke_unsent_requests(frm) {
	if (frm.is_new() || frm.doc.docstatus !== 0) return;
	const unsent = ["lab_test_prescription", "procedure_prescription", "therapies"]
		.flatMap((t) => frm.doc[t] || [])
		.filter(
			(r) =>
				!r.service_request &&
				(r.lab_test_code || r.observation_template || r.procedure || r.therapy_type)
		);
	if (unsent.length) {
		frm.dashboard.add_comment(
			__(
				"{0} request(s) not sent yet: click Send Requests on the Requests tab so they reach the Cashier and the lab.",
				[unsent.length]
			),
			"orange",
			true
		);
	}
}

// The latest vital signs at the top of every tab, abnormal readings in red.
function ke_latest_vitals(frm) {
	if (!frm.doc.patient) return;
	frappe
		.xcall("royce_health_ke.consultation.latest_vitals", {
			patient: frm.doc.patient,
			visit: frm.doc.ke_patient_visit || null,
		})
		.then((v) => {
			if (frm.__ke_vitals_section)
				frm.__ke_vitals_section.closest(".form-dashboard-section").remove();
			frm.__ke_vitals_section = null;
			if (!v) return;
			const esc = frappe.utils.escape_html;
			const flags = (v.ke_vitals_flags || "").toLowerCase();
			const item = (label, value, unit, key) =>
				value || value === 0
					? `<div class="mr-4 mb-1"><span class="text-muted small">${label}</span><br><b${
							key && flags.includes(key) ? ' style="color:var(--red-600)"' : ""
					  }>${esc(String(value))}${unit ? " " + unit : ""}</b></div>`
					: "";
			const bp = v.bp || (v.bp_systolic ? `${v.bp_systolic}/${v.bp_diastolic || "?"}` : "");
			const html = `<div class="d-flex flex-wrap align-items-start">
				${item(__("Temp"), v.temperature, "°C", "temp")}
				${item(__("Pulse"), v.pulse, "/min", "pulse")}
				${item(__("Resp"), v.respiratory_rate, "/min", "resp")}
				${item(__("BP"), bp, "mmHg", "bp")}
				${item(__("SpO2"), v.ke_spo2, "%", "spo2")}
				${item(__("Weight"), v.weight, "kg")}
				${item(__("Height"), v.ke_height_cm, "cm")}
				${item(__("BMI"), v.bmi ? flt(v.bmi, 1) : "", "")}
				<div class="ml-auto small text-muted">${esc(frappe.datetime.str_to_user(v.signs_date))} ${esc(
				(v.signs_time || "").slice(0, 5)
			)} ·
					<a href="/desk/vital-signs/${encodeURIComponent(v.name)}">${esc(v.name)}</a> ·
					<a class="ke-vitals-history">${__("History and trends")}</a>
					${
						v.ke_vitals_status === "Abnormal"
							? `<span class="indicator-pill red ml-2">${__("Abnormal")}</span>`
							: ""
					}</div>
			</div>`;
			frm.__ke_vitals_section = frm.dashboard.add_section(html, __("Latest Vital Signs"));
			frm.__ke_vitals_section
				.find(".ke-vitals-history")
				.on("click", () => ke_vitals_history(frm.doc.patient));
			frm.dashboard.show();
		});
}

// Requests the bill can't charge: no price for this patient.
function ke_unpriced_html(info) {
	if (!info || !(info.unpriced || []).length) return "";
	return `<div class="alert alert-warning">${__(
		"No price set for this patient: {0}. The Cashier can't bill these until the administrator sets their price.",
		[info.unpriced.map((n) => frappe.utils.escape_html(n)).join(", ")]
	)}</div>`;
}

// A new consultation for a patient the doctor can't see yet (not checked in,
// or the consultation fee unpaid): say so at once, not only on Save
// (royce_health_ke.flow.consultation_gate refuses the save).
function ke_may_consult(frm) {
	if (!frm.is_new() || !frm.doc.patient) {
		if (frm.__ke_blocked) frm.set_intro("");
		frm.__ke_blocked = false;
		return;
	}
	frappe
		.xcall("royce_health_ke.flow.may_consult", {
			patient: frm.doc.patient,
			encounter_date: frm.doc.encounter_date,
		})
		.then((why) => {
			frm.__ke_blocked = Boolean(why);
			frm.set_intro(why ? frappe.utils.escape_html(why) : "", "red");
		});
}

// Consultation tabs (royce_health_ke.consultation): Observation -> Requests ->
// Results -> Diagnosis -> Prescription -> Complete.
function ke_consultation_refresh(frm) {
	const results = frm.fields_dict.ke_results_html;
	const pharmacy = frm.fields_dict.ke_pharmacy_html;
	if (!results) return;
	if (frm.is_new()) {
		results.$wrapper.html(
			`<p class="text-muted">${__("Results show here once requests are sent.")}</p>`
		);
		pharmacy && pharmacy.$wrapper.empty();
		return;
	}
	// One way to complete: the main button is Complete Consultation, not Marley's Submit
	// (IT demo, 18 Nov 2026: a consultation was locked by Submit before the diagnosis).
	if (frm.doc.docstatus === 0 && !frm.is_dirty()) {
		frm.page.set_primary_action(__("Complete Consultation"), () =>
			ke_complete_consultation(frm)
		);
	}
	frappe.call({
		method: "royce_health_ke.consultation.panel",
		args: { encounter: frm.doc.name },
		callback: (r) => {
			const data = r.message || {};
			results.$wrapper.html(ke_results_html(data.results || []));
			results.$wrapper.find(".ke-cancel-request").on("click", (e) => {
				const request = $(e.currentTarget).data("request");
				frappe.prompt(
					{ fieldname: "reason", fieldtype: "Small Text", label: __("Reason"), reqd: 1 },
					(v) =>
						frappe
							.xcall("royce_health_ke.consultation.cancel_request", {
								request,
								reason: v.reason,
							})
							.then((r) => {
								if (r && r.note)
									frappe.msgprint({ message: r.note, indicator: "orange" });
								frm.reload_doc();
							}),
					__("Cancel this request?"),
					__("Cancel Request")
				);
			});
			results.$wrapper.find(".ke-mark-seen").on("click", (e) => {
				const $b = $(e.currentTarget);
				frappe.call({
					method: "royce_health_ke.lab.mark_seen",
					args: { doctype: $b.data("doctype"), name: $b.data("name") },
					callback: () =>
						$b.replaceWith(`<span class="text-muted small">${__("Seen")}</span>`),
				});
			});
			if (pharmacy) pharmacy.$wrapper.html(ke_sent_back_html(data.sent_back || []));
			if ((data.sent_back || []).length) {
				frm.dashboard.add_comment(
					__("Pharmacy sent back {0}: see the Prescription tab.", [
						data.sent_back.map((m) => m.medication).join(", "),
					]),
					"orange",
					true
				);
			}
		},
	});
}

function ke_results_html(rows) {
	const esc = frappe.utils.escape_html;
	if (!rows.length) {
		return `<p class="text-muted">${__(
			"No lab or imaging requests on this visit yet. Add them on the Requests tab and click Send Requests."
		)}</p>`;
	}
	return rows
		.map((r) => {
			const link = r.name
				? `<a href="${frappe.utils.get_form_link(
						r.doctype,
						r.name
				  )}" target="_blank">${esc(r.name)}</a>`
				: "";
			const colour = r.cancelled
				? "gray"
				: r.awaiting_payment
				? "orange"
				: r.rows || r.impression
				? "green"
				: "blue";
			let body = "";
			if (r.rows && r.rows.length) {
				body = `<table class="table table-sm table-bordered mt-2 mb-0" style="font-size:12px">
					<thead><tr><th>${__("Test")}</th><th>${__("Result")}</th><th>${__("Unit")}</th><th>${__(
					"Normal range"
				)}</th></tr></thead><tbody>${r.rows
					.map(
						(x) => `<tr${
							x.flag ? ' style="font-weight:600;color:var(--red-600)"' : ""
						}>
						<td>${esc(x.name || "")}</td><td>${esc(x.value || "")} ${x.flag ? esc(x.flag) : ""}</td>
						<td>${esc(x.uom || "")}</td><td>${esc(x.range || "")}</td></tr>`
					)
					.join("")}</tbody></table>`;
			} else if (r.impression) {
				body = `<div class="mt-2" style="white-space:pre-wrap"><b>${__(
					"Findings"
				)}:</b> ${esc(r.findings || "")}</div><div style="white-space:pre-wrap"><b>${__(
					"Impression"
				)}:</b> ${esc(r.impression)}</div>`;
			}
			const seen =
				r.name && (r.rows || r.impression)
					? r.seen
						? `<span class="text-muted small">${__("Seen")}</span>`
						: `<button class="btn btn-xs btn-default ke-mark-seen" data-doctype="${esc(
								r.doctype
						  )}" data-name="${esc(r.name)}">${__("Mark Seen")}</button>`
					: "";
			return `<div class="mb-3 p-3" style="border:1px solid var(--border-color);border-radius:8px">
				<div class="d-flex justify-content-between align-items-center">
					<div><b>${esc(r.test || "")}</b> <span class="text-muted small ml-2">${link}</span></div>
					<div><span class="indicator-pill ${colour}">${esc(r.status || "")}</span> ${seen}${
				r.cancellable
					? ` <button class="btn btn-xs btn-default ke-cancel-request" data-request="${esc(
							r.request
					  )}">${__("Cancel Request")}</button>`
					: ""
			}</div>
				</div>${body}</div>`;
		})
		.join("");
}

function ke_sent_back_html(rows) {
	if (!rows.length) return "";
	const esc = frappe.utils.escape_html;
	return `<div class="alert alert-warning mb-2"><b>${__("Sent back by the pharmacy")}</b>
		<ul class="mb-0">${rows
			.map((m) => `<li>${esc(m.medication || "")}: ${esc(m.note || "")}</li>`)
			.join("")}</ul>
		<div class="small mt-1">${__(
			"Change the prescription: the pharmacy can't give a different medicine without you."
		)}</div></div>`;
}

async function ke_save_first(frm) {
	if (frm.is_dirty() || frm.is_new()) await frm.save();
}

async function ke_send_requests(frm) {
	await ke_save_first(frm);
	frappe.call({
		method: "royce_health_ke.consultation.send_requests",
		args: { encounter: frm.doc.name },
		freeze: true,
		freeze_message: __("Sending requests..."),
		callback: async (r) => {
			await frm.reload_doc();
			frappe.show_alert({ message: __("Requests sent"), indicator: "green" });
			ke_next_station(frm, r.message, false);
		},
	});
}

async function ke_complete_consultation(frm) {
	await ke_save_first(frm);
	frappe.confirm(
		__(
			"Complete this consultation? It is then locked: no more requests, diagnosis or prescriptions. To wait for results, use Send Requests instead."
		),
		() =>
			frappe.call({
				method: "royce_health_ke.consultation.complete",
				args: { encounter: frm.doc.name },
				freeze: true,
				freeze_message: __("Completing consultation..."),
				callback: async (r) => {
					await frm.reload_doc();
					ke_next_station(frm, r.message, true);
				},
			})
	);
}

// After sending requests or completing: where does the patient go next?
function ke_next_station(frm, info, completed) {
	const unpriced = ke_unpriced_html(info);
	if (!info || !info.visit) {
		if (unpriced)
			frappe.msgprint({ title: __("No price set"), indicator: "orange", message: unpriced });
		return;
	}
	const FINISH = __("Finish visit (patient goes home)");
	const STAY = __("Stay with me (results later)");
	const options = [...info.stations];
	if (completed) options.push(FINISH);
	else options.push(STAY);
	const d = new frappe.ui.Dialog({
		title: __("Where does the patient go next?"),
		fields: [
			{
				fieldtype: "HTML",
				options:
					unpriced +
					(info.unpaid
						? `<p class="text-muted">${__(
								"{0} request(s) or medicine(s) are paid first: the patient goes to the Cashier, then on to the service point once paid.",
								[info.unpaid]
						  )}</p>`
						: ""),
			},
			{
				fieldname: "station",
				fieldtype: "Select",
				label: __("Send to"),
				options: options.join("\n"),
				default: options[0],
				reqd: 1,
			},
			{ fieldname: "note", fieldtype: "Small Text", label: __("Note for the next station") },
		],
		primary_action_label: __("Send"),
		primary_action(v) {
			if (v.station === STAY) return d.hide();
			const finish = v.station === FINISH;
			frappe.call({
				method: finish
					? "royce_health_ke.visits.complete"
					: "royce_health_ke.visits.send_to",
				args: finish
					? { visit: info.visit }
					: { visit: info.visit, station: v.station, note: v.note },
				callback: (r) => {
					d.hide();
					const sent = (r && r.message) || {};
					frappe.show_alert(
						{
							message: finish
								? __("Visit completed")
								: sent.redirected_from
								? __(
										"Sent to the Cashier first: the {0} requests are not paid. The patient goes on to {0} once paid.",
										[__(sent.redirected_from)]
								  )
								: __("Sent to {0}", [__(sent.station || v.station)]),
							indicator: sent.redirected_from ? "orange" : "green",
						},
						sent.redirected_from ? 10 : 5
					);
				},
			});
		},
	});
	d.show();
}

function ke_show_clinical_alerts(frm, popup) {
	frappe.call({
		method: "royce_health_ke.cds.pending_alerts",
		args: { encounter: frm.doc.name },
		callback: (r) => {
			const alerts = r.message || [];
			frm.dashboard.clear_headline();
			if (!alerts.length) return;
			const critical = alerts.filter((a) => a.severity === "Critical").length;
			frm.dashboard.set_headline_alert(
				`${__("{0} clinical alert(s) to review", [alerts.length])}${
					critical ? " (" + __("{0} critical", [critical]) + ")" : ""
				} <a class="ke-review-alerts" style="margin-left:8px">${__("Review")}</a>`,
				critical ? "red" : "orange"
			);
			$(frm.wrapper)
				.find(".ke-review-alerts")
				.on("click", () => ke_alerts_dialog(frm, alerts));
			if (popup) ke_alerts_dialog(frm, alerts);
		},
	});
}

function ke_alerts_dialog(frm, alerts) {
	const d = new frappe.ui.Dialog({ title: __("Clinical Alerts"), size: "large" });
	const render = () => {
		const html = alerts
			.map(
				(a) => `<div class="ke-alert mb-3 p-3" data-name="${
					a.name
				}" style="border:1px solid var(--border-color);border-radius:8px">
				<div class="mb-2"><span class="indicator-pill ${KE_ALERT_COLOURS[a.severity] || "gray"}">${__(
					a.severity
				)}</span>
				<span class="text-muted small ml-2">${__(a.kind)}</span></div>
				<div style="white-space:pre-wrap">${frappe.utils.escape_html(a.message)}</div>
				<div class="mt-2">
					<button class="btn btn-xs btn-primary ke-acted">${__("Acted On")}</button>
					<button class="btn btn-xs btn-default ke-override ml-2">${__("Override")}</button>
				</div></div>`
			)
			.join("");
		d.$body.html(html || `<p class="text-muted">${__("All alerts reviewed.")}</p>`);
		d.$body.find(".ke-acted").on("click", (e) => answer(e, "Acted On"));
		d.$body.find(".ke-override").on("click", (e) => {
			frappe.prompt(
				{
					fieldname: "reason",
					fieldtype: "Small Text",
					label: __("Reason for overriding"),
					reqd: 1,
				},
				(v) => answer(e, "Overridden", v.reason),
				__("Override Alert")
			);
		});
	};
	const answer = (e, response, reason) => {
		const name = $(e.target).closest(".ke-alert").data("name");
		frappe.call({
			method: "royce_health_ke.cds.respond",
			args: { log: name, response, reason },
			callback: () => {
				alerts = alerts.filter((a) => a.name !== name);
				render();
				ke_show_clinical_alerts(frm);
				if (!alerts.length) d.hide();
			},
		});
	};
	render();
	d.show();
}

// Every vital signs reading of the patient, with a trend line per sign
// (royce_health_ke.consultation.vitals_history).
const KE_TRENDS = [
	["temperature", __("Temp"), "°C"],
	["pulse", __("Pulse"), "/min"],
	["respiratory_rate", __("Resp"), "/min"],
	["bp_systolic", __("Systolic BP"), "mmHg"],
	["ke_spo2", __("SpO2"), "%"],
	["weight", __("Weight"), "kg"],
];

function ke_sparkline(values) {
	const points = values.map((v, i) => [i, v]).filter(([, v]) => v || v === 0);
	if (points.length < 2) return "";
	const w = 160,
		h = 36,
		pad = 3;
	const ys = points.map(([, v]) => v);
	const lo = Math.min(...ys),
		hi = Math.max(...ys);
	const n = values.length - 1 || 1;
	const xy = points.map(([i, v]) => [
		pad + (i / n) * (w - 2 * pad),
		h - pad - (hi === lo ? 0.5 : (v - lo) / (hi - lo)) * (h - 2 * pad),
	]);
	const last = xy[xy.length - 1];
	return `<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" role="img">
		<polyline fill="none" stroke="var(--blue-500)" stroke-width="1.5" points="${xy
			.map((p) => p.join(","))
			.join(" ")}"/>
		<circle cx="${last[0]}" cy="${last[1]}" r="2.5" fill="var(--blue-600)"/></svg>`;
}

function ke_vitals_history(patient) {
	frappe.xcall("royce_health_ke.consultation.vitals_history", { patient }).then((rows) => {
		const esc = frappe.utils.escape_html;
		rows = rows || [];
		const trends = KE_TRENDS.map(([field, label, unit]) => {
			const values = rows.map((r) => (r[field] ? flt(r[field]) : null));
			const known = values.filter((v) => v !== null);
			if (!known.length) return "";
			return `<div class="mr-4 mb-3"><div class="small text-muted">${label}</div>
				<div><b>${esc(String(known[known.length - 1]))}</b> ${unit}
				<span class="small text-muted">(${__("{0} readings", [known.length])})</span></div>
				${ke_sparkline(values)}</div>`;
		}).join("");
		const table = rows
			.slice()
			.reverse()
			.map((v) => {
				const bp =
					v.bp || (v.bp_systolic ? `${v.bp_systolic}/${v.bp_diastolic || "?"}` : "");
				const cell = (x) => `<td>${x || x === 0 ? esc(String(x)) : ""}</td>`;
				return `<tr${
					v.ke_vitals_status === "Abnormal" ? ' style="color:var(--red-600)"' : ""
				}>
					<td><a href="/desk/vital-signs/${encodeURIComponent(v.name)}">${esc(
					frappe.datetime.str_to_user(v.signs_date)
				)} ${esc((v.signs_time || "").slice(0, 5))}</a></td>
					${cell(v.temperature)}${cell(v.pulse)}${cell(v.respiratory_rate)}${cell(bp)}${cell(
					v.ke_spo2
				)}${cell(v.weight)}${cell(v.ke_height_cm)}${cell(v.bmi ? flt(v.bmi, 1) : "")}
					<td class="small">${esc(v.ke_vitals_flags || "")}</td></tr>`;
			})
			.join("");
		const d = new frappe.ui.Dialog({ title: __("Vital Signs History"), size: "extra-large" });
		d.$body.html(
			rows.length
				? `<div class="d-flex flex-wrap">${trends}</div>
				<div class="table-responsive"><table class="table table-sm table-bordered" style="font-size:12px">
				<thead><tr><th>${__("Taken")}</th><th>${__("Temp")}</th><th>${__("Pulse")}</th><th>${__(
						"Resp"
				  )}</th><th>${__("BP")}</th><th>SpO2</th><th>${__("Weight")}</th><th>${__(
						"Height"
				  )}</th><th>BMI</th><th>${__("Flags")}</th></tr></thead>
				<tbody>${table}</tbody></table></div>`
				: `<p class="text-muted">${__("No vital signs recorded for this patient.")}</p>`
		);
		d.show();
	});
}

async function ke_admit_dialog(frm) {
	const wards = (await frappe.xcall("royce_health_ke.inpatient.ward_list")) || [];
	if (!wards.length) {
		frappe.msgprint(
			__("No ward has beds yet. Set up the wards and beds (Healthcare Service Units) first.")
		);
		return;
	}
	const d = new frappe.ui.Dialog({
		title: __("Admit to Ward"),
		fields: [
			{
				fieldname: "ward",
				fieldtype: "Select",
				label: __("Ward"),
				options: wards.join("\n"),
				reqd: 1,
			},
			{
				fieldname: "urgency",
				fieldtype: "Select",
				label: __("Urgency"),
				options: "Routine\nUrgent\nEmergency",
				default: "Routine",
				reqd: 1,
			},
			{
				fieldname: "admission_date",
				fieldtype: "Date",
				label: __("Admission Date"),
				default: frappe.datetime.get_today(),
				reqd: 1,
			},
			{ fieldname: "expected_days", fieldtype: "Int", label: __("Expected Stay (days)") },
			{ fieldtype: "Column Break" },
			{
				fieldname: "reason",
				fieldtype: "Small Text",
				label: __("Admission Reason"),
				reqd: 1,
			},
			{
				fieldname: "notes",
				fieldtype: "Small Text",
				label: __("Admission Notes (for the ward)"),
			},
		],
		primary_action_label: __("Admit"),
		primary_action(v) {
			frappe
				.xcall("royce_health_ke.inpatient.request_admission", {
					encounter: frm.doc.name,
					...v,
				})
				.then((ip) => {
					d.hide();
					frappe.msgprint({
						title: __("Admission requested"),
						indicator: "green",
						message: __(
							"{0} is on the {1} admission list ({2}). The ward gives the bed. Complete the consultation when you are done.",
							[
								frappe.utils.escape_html(frm.doc.patient_name),
								frappe.utils.escape_html(v.ward),
								ip,
							]
						),
					});
					frm.reload_doc();
				});
		},
	});
	d.show();
}
