// Copyright (c) 2026, Royce Technologies LTD and contributors
// For license information, please see license.txt

// Registration details the hospital requires (Kenya Health Settings); the
// contact number and county depend on age and nationality, so the server
// checks those (royce_health_ke.identity.missing_registration_details).
const KE_REQUIRED = ["dob", "ke_id_type", "ke_nationality", "ke_residence"];

frappe.ui.form.on("Patient", {
	setup(frm) {
		// residences of the chosen county first; a new one starts in it
		frm.set_query("ke_residence", () => ({
			filters: Object.assign(
				{ disabled: 0 },
				frm.doc.ke_county ? { county: ["in", [frm.doc.ke_county, ""]] } : {}
			),
		}));
		frm.fields_dict.ke_residence.get_route_options_for_new_doc = () => ({
			county: frm.doc.ke_county || "",
			sub_county: frm.doc.ke_sub_county || "",
		});
	},
	onload_post_render(frm) {
		ke_offer_sub_counties(frm);
	},
	ke_county(frm) {
		ke_offer_sub_counties(frm).then((names) => {
			// a sub-county of another county no longer fits
			if (frm.doc.ke_sub_county && names.length && !names.includes(frm.doc.ke_sub_county)) {
				frm.set_value("ke_sub_county", "");
			}
		});
	},
	// the residence fills the county and sub-county only when they are empty
	ke_residence(frm) {
		if (!frm.doc.ke_residence) return;
		frappe
			.xcall("royce_health_ke.identity.residence_place", { residence: frm.doc.ke_residence })
			.then((place) => {
				if (!place) return;
				if (!frm.doc.ke_county && place.county) frm.set_value("ke_county", place.county);
				if (
					!frm.doc.ke_sub_county &&
					place.sub_county &&
					(frm.doc.ke_county || place.county) === place.county
				) {
					frm.set_value("ke_sub_county", place.sub_county);
				}
			});
	},
	dob(frm) {
		ke_contact_required(frm);
	},
	ke_nationality(frm) {
		ke_contact_required(frm);
	},
	refresh(frm) {
		if (frappe.boot.ke_require_registration && frm.is_new()) {
			for (const f of KE_REQUIRED) frm.toggle_reqd(f, true);
		}
		ke_contact_required(frm);
		if (frm.is_new()) return;
		// Today's open visit: close it from the patient's record (visit_close.py)
		frappe.db
			.get_list("Patient Visit", {
				filters: { patient: frm.doc.name, status: "Open" },
				fields: ["name"],
				order_by: "creation desc",
				limit: 1,
			})
			.then((rows) => {
				if (!rows.length || !frappe.model.can_write("Patient Visit")) return;
				frm.add_custom_button(__("Close Visit"), () =>
					royce_health_ke.close_visit(rows[0].name, () => frm.reload_doc())
				);
			});
		if (frappe.model.can_create("Patient Visit")) {
			frm.add_custom_button(
				__("Check In (New Visit)"),
				() => frappe.new_doc("Patient Visit", { patient: frm.doc.name }),
				__("Create")
			);
		}
		// The patient file: the whole record, clinicians only (printing.patient_file)
		if (
			frappe.user.has_role([
				"Physician",
				"Nursing User",
				"Healthcare Administrator",
				"System Manager",
			])
		) {
			frm.add_custom_button(
				__("Patient File"),
				() =>
					window.open(
						`/printview?doctype=Patient&name=${encodeURIComponent(
							frm.doc.name
						)}&format=Patient%20File`,
						"_blank"
					),
				__("View")
			);
		}
		if (frappe.model.can_read("Patient Record Access")) {
			frm.add_custom_button(
				__("Who Opened This Record"),
				() => frappe.set_route("List", "Patient Record Access", { patient: frm.doc.name }),
				__("View")
			);
		}
		// Under 5 (the WHO standards' range): plot every measurement on the WHO curves.
		if (frm.doc.dob && moment().diff(moment(frm.doc.dob), "days") <= 1856) {
			frm.add_custom_button(__("Growth Chart"), () => growth_chart_dialog(frm), __("View"));
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
		[__("Please call us")]:
			__("Dear {0}, {1} would like to speak with you.", [name, at]) + call,
		[__("Results ready")]:
			__("Dear {0}, your results are ready at {1}. Please see your clinician.", [name, at]) +
			call,
		[__("Missed appointment")]:
			__(
				"Dear {0}, we missed you at your appointment at {1}. Please contact us to book another.",
				[name, at]
			) + call,
		[__("Medicine ready")]:
			__("Dear {0}, your medicine is ready for collection at {1}.", [name, at]) + call,
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
				frappe.msgprint(
					__("This patient has no mobile number. Add one to the record first.")
				);
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
					{
						fieldtype: "Data",
						fieldname: "to",
						label: __("To"),
						read_only: 1,
						default: info.mobile,
					},
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
						description: __(
							"Don't include results or diagnoses: phones are not private."
						),
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

// Growth chart: WHO curves (-3, -2, median, +2, +3 SD) by month, birth to 5
// years, with the child's measurements on top (royce_health_ke.growth.chart).
const GROWTH_COLOURS = {
	"-3": "#c0392b",
	"-2": "#e67e22",
	0: "#27ae60",
	2: "#e67e22",
	3: "#c0392b",
};

function growth_chart_dialog(frm) {
	const charts = { [__("Weight-for-age")]: "wfa", [__("Length/height-for-age")]: "lhfa" };
	const d = new frappe.ui.Dialog({
		title: __("Growth Chart"),
		size: "extra-large",
		fields: [
			{
				fieldname: "chart_type",
				fieldtype: "Select",
				label: __("Chart"),
				options: Object.keys(charts).join("\n"),
				default: __("Weight-for-age"),
				change: () => load(),
			},
			{ fieldname: "chart", fieldtype: "HTML" },
		],
	});
	const load = () =>
		frappe.call({
			method: "royce_health_ke.growth.chart",
			args: {
				patient: frm.doc.name,
				indicator: charts[d.get_value("chart_type")] || "wfa",
			},
			callback: (r) => r.message && d.fields_dict.chart.$wrapper.html(growth_svg(r.message)),
		});
	d.show();
	load();
}

function growth_svg(data) {
	const W = 860,
		H = 440,
		left = 50,
		right = 20,
		top = 20,
		bottom = 40;
	const all = data.curves.flatMap((c) => c.values).concat(data.measurements.map((m) => m.value));
	const lo = Math.floor(Math.min(...all)),
		hi = Math.ceil(Math.max(...all));
	const x = (months) => left + (months / 60) * (W - left - right);
	const y = (v) => top + (1 - (v - lo) / (hi - lo)) * (H - top - bottom);
	const path = (pts) =>
		pts.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(" ");
	let svg = `<svg viewBox="0 0 ${W} ${H}" style="width:100%;height:auto;font-size:11px">`;
	for (let m = 0; m <= 60; m += 6) {
		svg += `<line x1="${x(m)}" x2="${x(m)}" y1="${top}" y2="${H - bottom}" stroke="#eee"/>`;
		svg += `<text x="${x(m)}" y="${
			H - bottom + 15
		}" text-anchor="middle" fill="#666">${m}</text>`;
	}
	const step = Math.max(1, Math.round((hi - lo) / 10));
	for (let v = lo; v <= hi; v += step) {
		svg += `<line x1="${left}" x2="${W - right}" y1="${y(v)}" y2="${y(v)}" stroke="#eee"/>`;
		svg += `<text x="${left - 6}" y="${y(v) + 4}" text-anchor="end" fill="#666">${v}</text>`;
	}
	for (const c of data.curves) {
		const pts = c.values.map((v, m) => [x(m), y(v)]);
		svg += `<path d="${path(pts)}" fill="none" stroke="${GROWTH_COLOURS[c.z]}" stroke-width="${
			c.z === 0 ? 2 : 1.3
		}"/>`;
		const last = pts[pts.length - 1];
		svg += `<text x="${last[0] - 2}" y="${last[1] - 3}" text-anchor="end" fill="${
			GROWTH_COLOURS[c.z]
		}">${c.z === 0 ? __("Median") : (c.z > 0 ? "+" : "") + c.z}</text>`;
	}
	const pts = data.measurements.map((m) => [x(m.months), y(m.value)]);
	if (pts.length > 1)
		svg += `<path d="${path(pts)}" fill="none" stroke="#2c3e50" stroke-width="1.5"/>`;
	for (const m of data.measurements) {
		const tip = `${frappe.datetime.str_to_user(m.date)}: ${m.value}${
			m.z !== null ? " (z " + m.z + ")" : ""
		}`;
		svg += `<circle cx="${x(m.months)}" cy="${y(
			m.value
		)}" r="4" fill="#2c3e50"><title>${frappe.utils.escape_html(tip)}</title></circle>`;
	}
	svg += `<text x="${(left + W - right) / 2}" y="${H - 5}" text-anchor="middle" fill="#444">${__(
		"Age (months)"
	)}</text>`;
	svg += "</svg>";
	const rows = data.measurements
		.map(
			(m) =>
				`<tr><td>${frappe.datetime.str_to_user(m.date)}</td><td>${m.months}</td><td>${
					m.value
				}</td><td>${m.z ?? ""}</td></tr>`
		)
		.join("");
	const table = data.measurements.length
		? `<table class="table table-sm mt-3"><thead><tr><th>${__("Date")}</th><th>${__(
				"Age (months)"
		  )}</th><th>${__("Value")}</th><th>${__(
				"Z-score"
		  )}</th></tr></thead><tbody>${rows}</tbody></table>`
		: `<p class="text-muted mt-3">${__(
				"No measurements recorded yet. Record weight and height in Vital Signs."
		  )}</p>`;
	return `<h5>${frappe.utils.escape_html(data.title)}: ${frappe.utils.escape_html(
		data.patient_name
	)}</h5>${svg}<p class="text-muted small">${__(
		"WHO Child Growth Standards. Green: median; orange: -2 / +2 SD; red: -3 / +3 SD."
	)}</p>${table}`;
}

// The contact number the server requires (identity.missing_registration_details),
// marked with an asterisk: an adult's own mobile; for a child under 18, the
// next of kin's phone (IT demo, 18 Nov 2026). County too for Kenyans.
function ke_contact_required(frm) {
	// new registrations only: an older record missing them is only warned about (as on the server)
	if (!frappe.boot.ke_require_registration || !frm.is_new()) return;
	const age = frm.doc.dob ? moment().diff(moment(frm.doc.dob), "years") : null;
	const child = age !== null && age < 18;
	frm.toggle_reqd("mobile", !child);
	if (frm.fields_dict.ke_nok_phone) frm.toggle_reqd("ke_nok_phone", child && !frm.doc.mobile);
	if (frm.fields_dict.ke_county)
		frm.toggle_reqd("ke_county", frm.doc.ke_nationality === "Kenya");
}

// The chosen county's sub-counties, offered as suggestions in the Sub-County
// field (a text field: a name not on the list can still be typed).
const ke_sub_county_cache = {};
function ke_offer_sub_counties(frm) {
	const county = frm.doc.ke_county;
	const names = !county
		? Promise.resolve([])
		: ke_sub_county_cache[county]
		? Promise.resolve(ke_sub_county_cache[county])
		: frappe
				.xcall("royce_health_ke.identity.sub_counties", { county })
				.then((list) => (ke_sub_county_cache[county] = list || []));
	return names.then((list) => {
		const field = frm.fields_dict.ke_sub_county;
		const input = field && field.$input && field.$input.get(0);
		if (!input) return list;
		if (!field.ke_awesomplete) {
			field.ke_awesomplete = new Awesomplete(input, {
				minChars: 0,
				maxItems: 30,
				autoFirst: true,
			});
			$(input).on("focus", () => {
				field.ke_awesomplete.evaluate();
				if (field.ke_awesomplete._list.length) field.ke_awesomplete.open();
			});
			input.addEventListener("awesomplete-selectcomplete", () => $(input).trigger("change"));
		}
		field.ke_awesomplete.list = list;
		return list;
	});
}
