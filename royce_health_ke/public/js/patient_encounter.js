// Copyright (c) 2026, Royce Technologies LTD and contributors
// For license information, please see license.txt

// Clinical decision support (royce_health_ke.cds): after a save, show the
// consultation's pending alerts; the clinician marks each "Acted on" or
// overrides it with a reason. Alerts never block saving or submitting.
const KE_ALERT_COLOURS = { Critical: "red", Warning: "orange", Info: "blue" };

frappe.ui.form.on("Patient Encounter", {
	refresh(frm) {
		if (!frm.is_new()) ke_show_clinical_alerts(frm);
	},
	after_save(frm) {
		ke_show_clinical_alerts(frm, true);
	},
});

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
