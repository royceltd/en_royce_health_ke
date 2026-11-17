// Copyright (c) 2026, Royce Technologies LTD and contributors
// For license information, please see license.txt

// Clinical decision support (royce_health_ke.cds): after a save, show the
// consultation's pending alerts; the clinician marks each "Acted on" or
// overrides it with a reason. Alerts never block saving or submitting.
const KE_ALERT_COLOURS = { Critical: "red", Warning: "orange", Info: "blue" };

frappe.ui.form.on("Patient Encounter", {
	refresh(frm) {
		if (!frm.is_new()) ke_show_clinical_alerts(frm);
		ke_consultation_refresh(frm);
		ke_may_consult(frm);
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
});

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
	if (frm.doc.docstatus === 0) {
		frm.add_custom_button(__("Complete Consultation"), () =>
			ke_complete_consultation(frm)
		).addClass("btn-primary");
	}
	frappe.call({
		method: "royce_health_ke.consultation.panel",
		args: { encounter: frm.doc.name },
		callback: (r) => {
			const data = r.message || {};
			results.$wrapper.html(ke_results_html(data.results || []));
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
			const colour = r.awaiting_payment
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
					<div><span class="indicator-pill ${colour}">${esc(r.status || "")}</span> ${seen}</div>
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
			"Complete this consultation? Orders not sent yet are placed, and the consultation can no longer be edited."
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
	if (!info || !info.visit) return;
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
				options: info.unpaid
					? `<p class="text-muted">${__(
							"{0} request(s) or medicine(s) are paid first: the patient goes to the Cashier, then on to the service point once paid.",
							[info.unpaid]
					  )}</p>`
					: "",
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
									? __("Sent to the Cashier first: the {0} requests are not paid. The patient goes on to {0} once paid.", [__(sent.redirected_from)])
									: __("Sent to {0}", [__(sent.station || v.station)]),
							indicator: sent.redirected_from ? "orange" : "green",
						},
						sent.redirected_from ? 10 : 5,
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
