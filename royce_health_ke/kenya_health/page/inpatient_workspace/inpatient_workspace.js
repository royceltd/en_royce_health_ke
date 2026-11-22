/* global healthcare, royce_health_ke */
// Copyright (c) 2026, Royce Technologies LTD and contributors
// For license information, please see license.txt

// One admission's patient screen: a banner and a horizontal tab bar. The tabs
// come from the Patient Workspace Profile (data); recording at the bedside
// uses Marley's Nursing Dialog (vitals, intake/output, medication round,
// notes, handover, care plan). Server side: royce_health_ke/inpatient.py.

const IW = "royce_health_ke.inpatient.";

frappe.pages["inpatient-workspace"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Inpatient"),
		single_column: true,
	});
	wrapper.iw = new InpatientWorkspace(page);
};

frappe.pages["inpatient-workspace"].on_page_show = function (wrapper) {
	const route = frappe.get_route();
	// inpatient-workspace/<admission>[/<theatre booking>]: with a booking, the
	// theatre's tabs (opened from the Theatre List)
	if (wrapper.iw && route[1]) wrapper.iw.load(route[1], route[2] || null);
};

function iw_esc(v) {
	return frappe.utils.escape_html(v == null ? "" : String(v));
}

function iw_when(v) {
	return v ? iw_esc(frappe.datetime.str_to_user(v)) : "";
}

function iw_money(v) {
	return format_currency(v || 0);
}

function iw_table(headers, rows) {
	if (!rows.length) return `<p class="text-muted">${__("Nothing recorded yet.")}</p>`;
	return `<div class="table-responsive"><table class="table table-sm table-bordered" style="font-size:12px">
		<thead><tr>${headers.map((h) => `<th>${h}</th>`).join("")}</tr></thead>
		<tbody>${rows
			.map((r) => `<tr>${r.map((c) => `<td>${c}</td>`).join("")}</tr>`)
			.join("")}</tbody></table></div>`;
}

class InpatientWorkspace {
	constructor(page) {
		this.page = page;
		page.set_secondary_action(__("Ward"), () =>
			this.booking
				? frappe.set_route("query-report", "Theatre List")
				: frappe.set_route("ward")
		);
		this.$banner = $(`<div class="mb-3"></div>`).appendTo(page.main);
		this.$tabs = $(`<ul class="nav nav-tabs mb-3" style="flex-wrap:wrap"></ul>`).appendTo(
			page.main
		);
		this.$panel = $(`<div></div>`).appendTo(page.main);
		this.$tabs.on("click", "a", (e) => {
			e.preventDefault();
			this.show($(e.currentTarget).data("panel"));
		});
	}

	async load(ip, booking) {
		if (booking !== undefined) this.booking = booking;
		this.ip = ip;
		this.data = await frappe.xcall(IW + "workspace", {
			inpatient_record: ip,
			booking: this.booking,
		});
		this.page.set_title(this.data.patient_name);
		this.page.set_secondary_action(
			this.booking ? __("Theatre List") : this.data.casualty ? __("Casualty") : __("Ward"),
			() =>
				this.booking
					? frappe.set_route("query-report", "Theatre List")
					: frappe.set_route(this.data.casualty ? "casualty" : "ward")
		);
		this.render_banner();
		this.$tabs.html(
			this.data.tabs
				.map(
					(t) =>
						`<li class="nav-item"><a class="nav-link" href="#" data-panel="${iw_esc(
							t.panel
						)}">${iw_esc(__(t.label || t.panel))}</a></li>`
				)
				.join("")
		);
		this.show(
			this.panel_name && this.data.tabs.some((t) => t.panel === this.panel_name)
				? this.panel_name
				: this.data.tabs[0].panel
		);
	}

	render_banner() {
		const d = this.data;
		const chip = (label, value, colour) =>
			value
				? `<div class="mr-4 mb-1"><span class="text-muted small">${label}</span><br><b${
						colour ? ` style="color:var(--${colour}-600)"` : ""
				  }>${iw_esc(value)}</b></div>`
				: "";
		const m = d.money || {};
		this.$banner
			.html(`<div class="p-3" style="border:1px solid var(--border-color);border-radius:8px">
			<div class="d-flex flex-wrap align-items-start">
				${chip(__("Patient"), `${d.patient_name} (${d.patient})`)}
				${chip(__("Age / Sex"), [d.age, d.sex].filter(Boolean).join(" · "))}
				${chip(__("Ward / Bed"), [d.ward, d.bed].filter(Boolean).join(" · ") || __("Waiting for a bed"))}
				${chip(
					__("Admitted"),
					d.admitted
						? `${frappe.datetime.str_to_user(d.admitted)} (${d.days} ${__("day(s)")})`
						: ""
				)}
				${chip(__("Doctor"), d.practitioner_name || d.practitioner)}
				${chip(__("Payer"), d.payer)}
				${chip(__("Allergies"), d.allergies, "red")}
				${chip(__("Status"), __(d.status))}
			</div>
			${
				d.theatre
					? `<div class="small mt-1"><b>${__("Theatre")}:</b> ${iw_esc(
							[
								d.theatre.procedure,
								d.theatre.theatre,
								d.theatre.scheduled_start
									? frappe.datetime.str_to_user(d.theatre.scheduled_start)
									: "",
								d.theatre.surgeon,
								__(d.theatre.status),
							]
								.filter(Boolean)
								.join(" · ")
					  )} <a class="iw-booking">${iw_esc(d.theatre.name)}</a></div>`
					: ""
			}
			${
				d.transfer_to
					? `<div class="alert alert-info mt-2 mb-0">${__(
							"Transfer to {0} asked ({1}). The patient stays here until that ward gives a bed.",
							[iw_esc(d.transfer_to), iw_esc(d.transfer_reason || "")]
					  )}</div>`
					: ""
			}
			${
				d.reason
					? `<div class="small mt-1"><b>${__("Admitted for")}:</b> ${iw_esc(
							d.reason
					  )}</div>`
					: ""
			}
			${
				d.preauth === "Pending"
					? `<div class="alert alert-warning mt-2 mb-0">${__(
							"Waiting for the payer's pre-authorisation (due {0}). Care goes on; the claim is held until the code is recorded.",
							[iw_when(d.preauth_due)]
					  )} <a class="iw-preauth">${__("Record the code")}</a></div>`
					: ""
			}
			${
				m.over
					? `<div class="alert alert-warning mt-2 mb-0">${__(
							"Running bill {0}, paid {1}: {2} not yet paid.",
							[iw_money(m.total), iw_money(m.paid), iw_money(m.short)]
					  )}${
							m.deposit ? " " + __("Deposit asked: {0}.", [iw_money(m.deposit)]) : ""
					  }</div>`
					: ""
			}
		</div>`);
		this.$banner
			.find(".iw-booking")
			.on("click", () => frappe.set_route("Form", "Theatre Booking", d.theatre.name));
		this.$banner.find(".iw-preauth").on("click", () =>
			frappe.prompt(
				{
					fieldname: "code",
					fieldtype: "Data",
					label: __("Pre-authorisation code"),
					reqd: 1,
				},
				(v) =>
					frappe
						.xcall(IW + "record_preauth", {
							inpatient_record: this.ip,
							code: v.code,
						})
						.then(() => this.load(this.ip))
			)
		);
	}

	nursing(action) {
		if (!(window.healthcare && healthcare.nursing && healthcare.nursing.open)) {
			frappe.msgprint(__("The Nursing Dialog is not available."));
			return;
		}
		const dialog = healthcare.nursing.open({
			patient: this.data.patient,
			reference_doctype: "Inpatient Record",
			reference_name: this.ip,
			practitioner: this.data.practitioner,
		});
		if (action) dialog.select_action(action);
		dialog.dialog.onhide = () => this.show(this.panel_name);
	}

	ward_round() {
		frappe.new_doc("Patient Encounter", {
			patient: this.data.patient,
			inpatient_record: this.ip,
			practitioner: this.data.practitioner,
		});
	}

	async show(panel) {
		this.panel_name = panel;
		this.$tabs.find("a").removeClass("active");
		this.$tabs.find(`a[data-panel="${panel}"]`).addClass("active");
		this.$panel.html(`<p class="text-muted">${__("Loading...")}</p>`);
		const data = await frappe.xcall(IW + "panel", {
			inpatient_record: this.ip,
			panel,
			booking: this.booking,
		});
		const render = this["render_" + panel.toLowerCase().replace(/ /g, "_")];
		this.$panel.html("");
		if (render) render.call(this, data || {});
	}

	buttons(list) {
		const $bar = $(`<div class="mb-3"></div>`).appendTo(this.$panel);
		list.forEach(([label, fn, primary]) =>
			$(
				`<button class="btn btn-sm ${
					primary ? "btn-primary" : "btn-default"
				} mr-2 mb-1">${label}</button>`
			)
				.on("click", fn)
				.appendTo($bar)
		);
	}

	render_patient_file(d) {
		this.buttons(
			[
				[
					__("Open Patient File"),
					() =>
						window.open(
							`/printview?doctype=Patient&name=${encodeURIComponent(
								d.patient
							)}&format=Patient%20File`,
							"_blank"
						),
					true,
				],
				[__("Patient Report (choose sections)"), () => this.patient_report(d.patient)],
				[
					__("Admission Record"),
					() => frappe.set_route("Form", "Inpatient Record", this.ip),
				],
				d.encounter
					? [
							__("Admitting Consultation"),
							() => frappe.set_route("Form", "Patient Encounter", d.encounter),
					  ]
					: null,
			].filter(Boolean)
		);
		this.$panel.append(`<div class="small">
			${d.reason ? `<p><b>${__("Admission reason")}:</b> ${iw_esc(d.reason)}</p>` : ""}
			${d.instruction ? `<p><b>${__("Admission notes")}:</b> ${iw_esc(d.instruction)}</p>` : ""}</div>`);
	}

	// A form card on the tab, with its records in a table under it (Bethesda,
	// 20 Nov 2026: "for every entry, its form and the records in a table").
	entry_card(title, fields, save_label, on_save) {
		const $card =
			$(`<div class="p-3 mb-3" style="border:1px solid var(--border-color);border-radius:8px">
			<div class="mb-2"><b>${iw_esc(title)}</b></div><div class="iw-form"></div>
			<div class="text-right"><button class="btn btn-sm btn-default iw-reset mr-2">${__(
				"Reset"
			)}</button><button class="btn btn-sm btn-success iw-save">${iw_esc(
				save_label || __("Save")
			)}</button></div></div>`).appendTo(this.$panel);
		const fg = new frappe.ui.FieldGroup({ body: $card.find(".iw-form"), fields });
		fg.make();
		$card
			.find(".iw-reset")
			.on("click", () =>
				fg.fields_list.forEach((f) => f.df.fieldname && f.set_value(f.df.default || ""))
			);
		$card.find(".iw-save").on("click", async () => {
			const values = fg.get_values();
			if (!values) return;
			// an empty number box reads as 0: send only what was entered
			Object.values(fg.fields_dict).forEach((f) => {
				if (
					["Int", "Float", "Currency", "Percent"].includes(f.df.fieldtype) &&
					f.$input &&
					!String(f.$input.val() || "").trim()
				)
					delete values[f.df.fieldname];
			});
			$card.find(".iw-save").prop("disabled", true);
			try {
				await on_save(values, fg);
				frappe.show_alert({ message: __("Saved"), indicator: "green" });
				this.show(this.panel_name);
			} finally {
				$card.find(".iw-save").prop("disabled", false);
			}
		});
		return fg;
	}

	is_doctor() {
		return frappe.user.has_role(["Physician", "Healthcare Administrator", "System Manager"]);
	}

	render_vitals(d) {
		if (frappe.model.can_create("Vital Signs")) {
			this.entry_card(
				__("Record Vital Signs"),
				[
					{
						fieldname: "taken_at",
						fieldtype: "Datetime",
						label: __("Date and Time"),
						default: frappe.datetime.now_datetime(),
						reqd: 1,
					},
					{ fieldname: "temperature", fieldtype: "Data", label: __("Temperature (°C)") },
					{ fieldname: "pulse", fieldtype: "Data", label: __("Pulse (/min)") },
					{ fieldtype: "Column Break" },
					{
						fieldname: "bp_systolic",
						fieldtype: "Data",
						label: __("BP Systolic (mmHg)"),
					},
					{
						fieldname: "bp_diastolic",
						fieldtype: "Data",
						label: __("BP Diastolic (mmHg)"),
					},
					{
						fieldname: "respiratory_rate",
						fieldtype: "Data",
						label: __("Resp. Rate (/min)"),
					},
					{ fieldtype: "Column Break" },
					{ fieldname: "ke_spo2", fieldtype: "Data", label: __("SpO2 (%)") },
					{ fieldname: "weight", fieldtype: "Float", label: __("Weight (kg)") },
					{ fieldname: "ke_height_cm", fieldtype: "Float", label: __("Height (cm)") },
					{ fieldtype: "Section Break" },
					{
						fieldname: "vital_signs_note",
						fieldtype: "Small Text",
						label: __("Comments"),
					},
				],
				__("Save"),
				(v) => {
					const { taken_at, ...values } = v;
					return frappe.xcall(IW + "record_vitals", {
						inpatient_record: this.ip,
						values,
						taken_at,
					});
				}
			);
		}
		const rows = (d.rows || [])
			.slice()
			.reverse()
			.map((v) => [
				`${iw_when(v.signs_date)} ${iw_esc((v.signs_time || "").slice(0, 5))}`,
				iw_esc(v.weight || ""),
				iw_esc(v.ke_height_cm || ""),
				iw_esc(v.bmi ? flt(v.bmi, 1) : ""),
				iw_esc(v.bp || (v.bp_systolic ? `${v.bp_systolic}/${v.bp_diastolic || "?"}` : "")),
				iw_esc(v.pulse || ""),
				iw_esc(v.respiratory_rate || ""),
				iw_esc(v.temperature || ""),
				iw_esc(v.ke_spo2 || ""),
				iw_esc(v.vital_signs_note || ""),
				`<span style="color:var(--red-600)">${iw_esc(v.ke_vitals_flags || "")}</span>`,
			]);
		this.$panel.append(
			iw_table(
				[
					__("Date Recorded"),
					__("Weight"),
					__("Height"),
					__("BMI"),
					__("BP (mmHg)"),
					__("Pulse"),
					__("Resp. Rate"),
					__("Temp (°C)"),
					"SpO2 (%)",
					__("Comments"),
					__("Flags"),
				],
				rows
			)
		);
	}

	render_requests(d) {
		if (this.is_doctor()) {
			const fg = this.entry_card(
				__("New Request"),
				[
					{
						fieldname: "category",
						fieldtype: "Link",
						options: "Request Category",
						label: __("Request Type"),
						reqd: 1,
						onchange: () => fg.set_value("template", ""),
					},
					{ fieldtype: "Column Break" },
					{
						fieldname: "template",
						fieldtype: "Dynamic Link",
						options: "template_dt",
						get_options: () => fg.get_value("template_dt"),
						label: __("Service"),
						reqd: 1,
						get_query: () => ({
							query: "royce_health_ke.routing.template_query",
							filters: {
								category: fg.get_value("category") || "",
								kind: this.__request_kind || "",
								encounter: "",
							},
						}),
					},
					{ fieldname: "template_dt", fieldtype: "Data", hidden: 1 },
					{ fieldtype: "Column Break" },
					{
						fieldname: "urgency",
						fieldtype: "Select",
						label: __("Urgency"),
						options: "Routine\nUrgent\nSTAT",
						default: "Routine",
					},
					{ fieldtype: "Section Break" },
					{ fieldname: "note", fieldtype: "Small Text", label: __("Notes") },
				],
				__("Send Request"),
				(v) =>
					frappe.xcall(IW + "add_request", {
						inpatient_record: this.ip,
						category: v.category,
						template: v.template,
						urgency: v.urgency,
						note: v.note,
					})
			);
			const doctypes = {
				"Lab Test": "Lab Test Template",
				Imaging: "Observation Template",
				Procedure: "Clinical Procedure Template",
				Therapy: "Therapy Type",
			};
			fg.fields_dict.category.df.onchange = async () => {
				const cat = fg.get_value("category");
				const kind = cat
					? (await frappe.db.get_value("Request Category", cat, "request_kind")).message
							.request_kind
					: "";
				this.__request_kind = kind;
				fg.set_value("template_dt", doctypes[kind] || "");
				fg.set_value("template", "");
			};
		}
		const rows = (d.requests || []).map((r) => [
			`<a href="/desk/service-request/${encodeURIComponent(r.name)}">${iw_esc(
				r.template_dn
			)}</a>`,
			iw_esc(r.ke_service_point || ""),
			iw_esc(r.status_label),
			`${iw_when(r.order_date)} ${iw_esc((r.order_time || "").slice(0, 5))}`,
			iw_esc(r.practitioner_name || ""),
		]);
		this.$panel.append(
			iw_table([__("Request"), __("Goes to"), __("Status"), __("Ordered"), __("By")], rows)
		);
	}

	render_results(d) {
		const labs = (d.labs || [])
			.map(
				(t) => `<div class="mb-3"><b>${iw_esc(
					t.test
				)}</b> <a class="small ml-2" href="/desk/lab-test/${encodeURIComponent(
					t.name
				)}">${iw_esc(t.name)}</a> ${
					t.validated
						? ""
						: `<span class="indicator-pill blue">${__("At the lab")}</span>`
				}
				${
					(t.rows || []).length
						? iw_table(
								[__("Test"), __("Result"), __("Unit"), __("Range")],
								t.rows.map((r) => [
									iw_esc(r.name),
									`<b${r.flag ? ' style="color:var(--red-600)"' : ""}>${iw_esc(
										r.result || ""
									)} ${iw_esc(r.flag || "")}</b>`,
									iw_esc(r.unit || ""),
									iw_esc(r.range || ""),
								])
						  )
						: ""
				}</div>`
			)
			.join("");
		const imaging = (d.imaging || [])
			.map(
				(o) =>
					`<div class="mb-3"><b>${iw_esc(
						o.observation_template
					)}</b> <span class="indicator-pill gray">${iw_esc(
						__(o.ke_exam_status)
					)}</span>${
						o.images
							? ` <a href="${iw_esc(
									o.images
							  )}" target="_blank" rel="noopener noreferrer" class="small ml-2">${__(
									"View Images"
							  )}</a>`
							: ""
					}${
						o.ke_impression
							? `<div class="small"><b>${__("Impression")}:</b> ${iw_esc(
									o.ke_impression
							  )}</div>`
							: ""
					}</div>`
			)
			.join("");
		this.$panel.html(
			labs || imaging
				? labs + imaging
				: `<p class="text-muted">${__("No results during this admission yet.")}</p>`
		);
	}

	render_diagnosis(d) {
		if (this.is_doctor()) {
			const fg = this.entry_card(
				__("Add Diagnosis"),
				[
					{
						fieldname: "diagnosis",
						fieldtype: "Link",
						options: "Diagnosis",
						label: __("Diagnosis"),
						ignore_link_validation: 1,
						get_query: () => ({ query: "royce_health_ke.diagnosis.diagnosis_query" }),
						onchange: () =>
							this.resolve_diagnosis(fg, { diagnosis: fg.get_value("diagnosis") }),
					},
					{ fieldtype: "Column Break" },
					{
						fieldname: "code_value",
						fieldtype: "Link",
						options: "Code Value",
						label: __("ICD-11 Code"),
						description: __(
							"Needed: filled from the diagnosis when it has one, else choose it."
						),
						get_query: () => ({ query: "royce_health_ke.diagnosis.icd11_query" }),
						onchange: () =>
							this.resolve_diagnosis(fg, { code_value: fg.get_value("code_value") }),
					},
				],
				__("Add Diagnosis"),
				(v) => {
					if (!v.diagnosis && !v.code_value)
						frappe.throw(__("Choose the diagnosis or its ICD-11 code."));
					return frappe.xcall(IW + "add_diagnosis", {
						inpatient_record: this.ip,
						diagnosis: v.diagnosis,
						code_value: v.code_value,
					});
				}
			);
		}
		const rows = (d.diagnoses || []).map((x) => [
			iw_esc(x.diagnosis),
			x.code ? `ICD-11 ${iw_esc(x.code)}` : "",
			iw_when(x.date),
			iw_esc(x.by || ""),
		]);
		this.$panel.append(iw_table([__("Diagnosis"), __("Code"), __("Date"), __("By")], rows));
	}

	// name <-> ICD-11 code, as on the consultation (royce_health_ke.diagnosis)
	resolve_diagnosis(fg, args) {
		if (fg.__resolving || !(args.diagnosis || args.code_value)) return;
		frappe.xcall("royce_health_ke.diagnosis.resolve", args).then((r) => {
			if (!r) return;
			// a hospital diagnosis without a code: the code chosen is added to it,
			// the name stays (inpatient.add_diagnosis)
			if (args.diagnosis) fg.__uncoded = r.code_value ? null : r.diagnosis;
			const keep =
				args.code_value && fg.__uncoded && fg.__uncoded === fg.get_value("diagnosis");
			fg.__resolving = true;
			const set = {};
			if (!keep && r.diagnosis && fg.get_value("diagnosis") !== r.diagnosis)
				set.diagnosis = r.diagnosis;
			if (r.code_value && fg.get_value("code_value") !== r.code_value)
				set.code_value = r.code_value;
			fg.set_values(set).finally(() => (fg.__resolving = false));
		});
	}

	// Doctor's notes, instructions and nursing notes: one design, kept apart
	// (Bethesda, 20 Nov 2026). Current (the form) and Past (the notes).
	notes_screen(d, { note_type, title, info, can_write, extra = [], empty }) {
		const $root = this.$panel;
		const views = [
			["current", __("Current")],
			["past", __("Past")],
			...extra.map(([label]) => [label, label]),
		];
		const $row = $(`<div class="row">
			<div class="col-md-2 mb-3"><div class="list-group">${views
				.map(
					([k, l]) =>
						`<a href="#" class="list-group-item list-group-item-action py-2" data-view="${iw_esc(
							k
						)}">${iw_esc(l)}</a>`
				)
				.join("")}</div></div>
			<div class="col-md-10 iw-notes-body"></div></div>`).appendTo($root);
		const show = (key) => {
			const action = extra.find(([label]) => label === key);
			if (action) return action[1]();
			$row.find("[data-view]").removeClass("active");
			$row.find(`[data-view="${key}"]`).addClass("active");
			this.$panel = $row.find(".iw-notes-body").empty();
			try {
				if (key === "current" && can_write) this.note_form(note_type, title, info);
				else this.render_nursing_notes({ notes: d.notes }, true, empty);
			} finally {
				this.$panel = $root;
			}
		};
		$row.find("[data-view]").on("click", (e) => {
			e.preventDefault();
			show($(e.currentTarget).data("view"));
		});
		show(can_write ? "current" : "past");
	}

	note_form(note_type, title, info) {
		const templates = [
			__("Patient Assessment"),
			__("Medication Given"),
			__("Vital Signs Recorded"),
			__("Patient Education"),
			__("Care Provided"),
			__("Other Note"),
		];
		this.$panel.append(
			`<div class="alert alert-success small mb-3"><b>${iw_esc(title)}</b><br>${iw_esc(
				info
			)}</div>`
		);
		const fg = this.entry_card(
			title,
			[
				{ fieldname: "note", fieldtype: "Text Editor", label: __(title), reqd: 1 },
				{
					fieldname: "posting_date",
					fieldtype: "Datetime",
					label: __("Date"),
					reqd: 1,
					default: frappe.datetime.now_datetime(),
				},
				{ fieldtype: "Column Break" },
				{
					fieldname: "patient_status",
					fieldtype: "Select",
					label: __("Patient Status"),
					options: "\nStable\nImproving\nUnchanged\nDeteriorating\nCritical",
				},
				{
					fieldname: "notes_by",
					fieldtype: "Data",
					label: __("Notes By"),
					read_only: 1,
					default: frappe.session.user_fullname,
				},
				{ fieldtype: "Section Break", label: __("Quick Note Templates") },
				{ fieldname: "templates", fieldtype: "HTML" },
			],
			__("Save"),
			(v) =>
				frappe.xcall(IW + "record_note", {
					inpatient_record: this.ip,
					note_type,
					note: v.note,
					patient_status: v.patient_status,
					posting_date: v.posting_date,
				})
		);
		fg.fields_dict.templates.$wrapper.html(
			templates
				.map(
					(t) =>
						`<button class="btn btn-xs btn-default mr-2 mb-2 iw-template">${iw_esc(
							t
						)}</button>`
				)
				.join("")
		);
		fg.fields_dict.templates.$wrapper.find(".iw-template").on("click", (e) => {
			const heading = $(e.currentTarget).text();
			fg.set_value(
				"note",
				`${fg.get_value("note") || ""}<p><b>${iw_esc(heading)}:</b> </p>`
			);
		});
	}

	render_doctor_notes(d) {
		this.notes_screen(d, {
			note_type: d.note_type,
			title: __("Doctor's Notes"),
			info: __("The ward round: the patient's progress, findings and plan."),
			can_write: this.is_doctor(),
			empty: __("No doctor's notes yet."),
		});
	}

	render_doctor_instructions(d) {
		this.notes_screen(d, {
			note_type: d.note_type,
			title: __("Doctor's Instructions"),
			info: __("Instructions for the nurses: what to do, watch and report."),
			can_write: this.is_doctor(),
			empty: __("No instructions yet."),
		});
	}

	render_note_list(notes, empty) {
		this.render_nursing_notes({ notes }, true, empty);
	}

	render_tb_screening(d) {
		this.render_charts(d.charts || []);
	}

	render_consent(d) {
		this.buttons([
			[
				__("New Consent"),
				() => frappe.new_doc("Surgical Consent", { patient: this.data.patient }),
				true,
			],
		]);
		this.$panel.append(
			iw_table(
				[__("Consent"), __("Procedure"), __("Date"), __("Given by"), __("Status")],
				(d.consents || []).map((c) => [
					`<a href="/desk/surgical-consent/${encodeURIComponent(c.name)}">${iw_esc(
						c.name
					)}</a>`,
					iw_esc(c.procedure_template || ""),
					iw_when(c.consent_datetime),
					iw_esc([c.consent_by, c.consenter_name].filter(Boolean).join(": ")),
					c.docstatus === 1 ? __("Signed") : __("Draft"),
				])
			)
		);
	}

	render_disposition(d) {
		this.buttons([
			[
				__("Set Disposition"),
				() =>
					frappe.prompt(
						[
							{
								fieldname: "outcome",
								fieldtype: "Select",
								label: __("Outcome"),
								options: (d.outcomes || []).join("\n"),
								default: d.outcome || "Discharged",
								reqd: 1,
							},
							{
								fieldname: "referred_to",
								fieldtype: "Data",
								label: __("Referred To (facility)"),
								default: d.referred_to,
								depends_on: "eval:doc.outcome=='Referred Out'",
							},
							{
								fieldname: "note",
								fieldtype: "Small Text",
								label: __("Note"),
								default: d.note,
							},
						],
						(v) =>
							frappe
								.xcall(IW + "set_disposition", { inpatient_record: this.ip, ...v })
								.then(() => this.show("Disposition")),
						__("Disposition"),
						__("Save")
					),
				true,
			],
			[__("Plan Discharge"), () => this.plan_discharge()],
			this.data.transfer_to
				? [__("Cancel Transfer"), () => this.cancel_transfer()]
				: [
						this.data.casualty ? __("Admit to Ward") : __("Transfer to Ward"),
						() => this.transfer(),
				  ],
		]);
		this.$panel.append(`<div class="small">
			<p><b>${__("Outcome")}:</b> ${iw_esc(__(d.outcome || "Not set"))}${
			d.referred_to ? ` · ${__("Referred to")} ${iw_esc(d.referred_to)}` : ""
		}</p>
			${d.note ? `<p>${iw_esc(d.note)}</p>` : ""}
			<p class="text-muted">${__("MOH 717 counts the admission by this outcome.")}</p></div>`);
	}

	// Transfer to another ward (Bethesda, 20 Nov 2026): asked here, received by
	// the other ward from its Incoming Transfers (it gives the bed).
	async transfer() {
		const wards = ((await frappe.xcall(IW + "ward_list")) || []).filter(
			(w) => w !== this.data.ward
		);
		if (!wards.length) {
			frappe.msgprint(__("There is no other ward."));
			return;
		}
		frappe.prompt(
			[
				{
					fieldname: "ward",
					fieldtype: "Select",
					label: __("To Ward"),
					options: wards.join("\n"),
					default: wards[0],
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
				{ fieldname: "reason", fieldtype: "Small Text", label: __("Reason"), reqd: 1 },
			],
			(v) =>
				frappe
					.xcall(IW + "request_transfer", { inpatient_record: this.ip, ...v })
					.then(() => {
						frappe.show_alert({
							message: __("Sent to {0}: it appears there under Incoming Transfers", [
								v.ward,
							]),
							indicator: "green",
						});
						this.load(this.ip);
					}),
			__("Transfer to another ward"),
			__("Send")
		);
	}

	cancel_transfer() {
		frappe.confirm(__("Cancel the transfer to {0}?", [iw_esc(this.data.transfer_to)]), () =>
			frappe
				.xcall(IW + "cancel_transfer", { inpatient_record: this.ip })
				.then(() => this.load(this.ip))
		);
	}

	patient_report(patient) {
		const sections = [
			["history", __("Medical history")],
			["admissions", __("Admissions")],
			["vitals", __("Vital signs")],
			["consultations", __("Consultations, diagnoses and medicines")],
			["requests", __("Requests")],
			["labs", __("Lab results")],
			["imaging", __("Imaging reports")],
		];
		frappe.prompt(
			sections.map(([fieldname, label]) => ({
				fieldname,
				label,
				fieldtype: "Check",
				default: 1,
			})),
			(v) => {
				const chosen = sections.filter(([f]) => v[f]).map(([f]) => f);
				window.open(
					`/printview?doctype=Patient&name=${encodeURIComponent(
						patient
					)}&format=Patient%20File&sections=${encodeURIComponent(chosen.join(","))}`,
					"_blank"
				);
			},
			__("Patient Report: what to include"),
			__("Open")
		);
	}

	render_nursing_notes(d, list_only, empty) {
		if (!list_only)
			return this.notes_screen(d, {
				note_type: "Nursing Note",
				title: __("Nursing Notes"),
				info: __(
					"Record patient observations, care provided, patient response and any other relevant nursing information."
				),
				can_write: true,
				extra: [
					[__("Nursing Care"), () => this.show("Nursing Care")],
					[__("Shift Handover"), () => this.nursing("handover")],
					[__("Nursing Tasks"), () => this.nursing("nursing_tasks")],
				],
				empty: __("No nursing notes yet. Record the admission assessment first."),
			});
		const notes = (d.notes || [])
			.map((n) => {
				const fdar = ["fdar_focus", "fdar_data", "fdar_action", "fdar_response"]
					.filter((f) => n[f])
					.map(
						(f) =>
							`<div><b>${iw_esc(
								__(f.replace("fdar_", "").replace(/^./, (c) => c.toUpperCase()))
							)}:</b> ${iw_esc(n[f])}</div>`
					)
					.join("");
				return `<div class="mb-2 p-2" style="border-left:3px solid var(--border-color)">
					<div class="small text-muted">${iw_esc(frappe.datetime.str_to_user(n.creation))} · ${iw_esc(
					n.shift || ""
				)} · ${iw_esc(n.by)} · ${iw_esc(n.clinical_note_type || "")}${
					n.ke_patient_status
						? ` · <span class="indicator-pill ${
								{ Critical: "red", Deteriorating: "orange", Improving: "green" }[
									n.ke_patient_status
								] || "gray"
						  }">${iw_esc(__(n.ke_patient_status))}</span>`
						: ""
				}</div>
					<div style="white-space:pre-wrap">${
						frappe.utils.html2text
							? iw_esc(frappe.utils.html2text(n.note || ""))
							: iw_esc(n.note || "")
					}</div>${fdar}</div>`;
			})
			.join("");
		this.$panel.append(
			notes ||
				`<p class="text-muted">${
					empty || __("No nursing notes yet. Record the admission assessment first.")
				}</p>`
		);
	}

	render_nursing_care(d) {
		this.buttons([
			[__("Intake / Output"), () => this.nursing("intake_output")],
			[__("Care Plan"), () => this.nursing("care_plan")],
			[__("Consumables"), () => this.nursing("consumables")],
		]);
		if (d.fluid) {
			const f = d.fluid;
			this.$panel.append(`<div class="mb-3"><b>${__("Fluid balance, last 24 hours")}:</b>
				${__("in")} ${iw_esc(f.intake || 0)} ml · ${__("out")} ${iw_esc(f.output || 0)} ml ·
				<b${(f.balance || 0) < 0 ? ' style="color:var(--red-600)"' : ""}>${__("balance")} ${iw_esc(
				f.balance || 0
			)} ml</b></div>`);
		}
		this.render_charts(d.charts || []);
	}

	// Nursing charts (Bethesda, 20 Nov 2026): the charts listed on the left;
	// the chosen chart's form, with its entries in a table under it.
	render_charts(charts) {
		if (!charts.length) {
			this.$panel.append(
				`<p class="text-muted">${__(
					"No charts set up. Add them in Nursing Chart Template."
				)}</p>`
			);
			return;
		}
		if (charts.length === 1) return this.chart_view(charts[0]);
		const $root = this.$panel;
		const $row = $(`<div class="row">
			<div class="col-md-3 mb-3"><div class="list-group">${charts
				.map(
					(c, i) =>
						`<a href="#" class="list-group-item list-group-item-action py-2" data-i="${i}">${iw_esc(
							c.name
						)}${
							c.due
								? `<div class="small text-muted">${__("Next due")}: ${iw_when(
										c.due
								  )}</div>`
								: ""
						}${
							c.status
								? `<div class="small text-muted">${iw_esc(c.status)}</div>`
								: ""
						}</a>`
				)
				.join("")}</div></div>
			<div class="col-md-9 iw-chart-body"></div></div>`).appendTo($root);
		const show = (i) => {
			this.__chart = charts[i].name;
			$row.find("[data-i]").removeClass("active");
			$row.find(`[data-i="${i}"]`).addClass("active");
			this.$panel = $row.find(".iw-chart-body").empty();
			try {
				this.chart_view(charts[i]);
			} finally {
				this.$panel = $root;
			}
		};
		$row.find("[data-i]").on("click", (e) => {
			e.preventDefault();
			show($(e.currentTarget).data("i"));
		});
		const last = charts.findIndex((c) => c.name === this.__chart);
		show(last >= 0 ? last : 0);
	}

	chart_fields(c) {
		return c.columns.map((col) => {
			const fieldname = "c_" + col.label.replace(/[^a-z0-9]/gi, "_").toLowerCase();
			col.fieldname = fieldname;
			const label = col.label + (col.unit ? ` (${col.unit})` : "");
			if (col.kind === "Number")
				return { fieldname, label, fieldtype: "Float", reqd: col.reqd };
			if (col.kind === "Yes or No")
				return {
					fieldname,
					label,
					fieldtype: "Select",
					options: "\nYes\nNo",
					reqd: col.reqd,
				};
			if (col.kind === "Choice" || col.kind === "Score")
				return {
					fieldname,
					label,
					fieldtype: "Select",
					options: "\n" + (col.options || ""),
					reqd: col.reqd,
				};
			return { fieldname, label, fieldtype: "Data", reqd: col.reqd };
		});
	}

	chart_view(c) {
		if (c.kind === "partograph") return this.partograph_view();
		const totals = Object.entries(c.totals || {})
			.map(([k, v]) => `${iw_esc(k)}: <b>${iw_esc(v)}</b>`)
			.join(" · ");
		this.$panel.append(`<div class="mb-2"><h5 class="mb-1">${iw_esc(c.name)}</h5>
			${c.description ? `<div class="small text-muted">${iw_esc(c.description)}</div>` : ""}
			${
				c.second_check
					? `<div class="small text-muted">${__(
							"Counter-checked by a second nurse"
					  )}</div>`
					: ""
			}
			${totals ? `<div class="small">${__("Last 24 hours")}: ${totals}</div>` : ""}</div>`);
		if (frappe.model.can_create("Nursing Chart Entry")) {
			const fields = this.chart_fields(c);
			// two columns, as on the paper chart
			const half = Math.ceil(fields.length / 2);
			const layout = [
				{
					fieldname: "recorded_at",
					fieldtype: "Datetime",
					label: __("Observation Date and Time"),
					default: frappe.datetime.now_datetime(),
					reqd: 1,
				},
				{ fieldtype: "Section Break" },
				...fields.slice(0, half),
				{ fieldtype: "Column Break" },
				...fields.slice(half),
				{ fieldtype: "Section Break" },
				...(c.second_check
					? [
							{
								fieldname: "second_check_by",
								fieldtype: "Link",
								options: "User",
								label: __("Counter Checked By"),
								description: __(
									"A second nurse, not you, checks the patient and the blood unit."
								),
								reqd: 1,
							},
							{ fieldtype: "Column Break" },
					  ]
					: []),
				{ fieldname: "note", fieldtype: "Small Text", label: __("Remarks") },
			];
			this.entry_card(__("New Entry"), layout, __("Save"), (v) => {
				const values = {};
				c.columns.forEach((col) => {
					const value = v[col.fieldname];
					if (value !== undefined && value !== null && value !== "")
						values[col.label] = value;
				});
				return frappe.xcall("royce_health_ke.charts.record", {
					inpatient_record: this.ip,
					template: c.name,
					values,
					note: v.note,
					second_check_by: v.second_check_by,
					recorded_at: v.recorded_at,
				});
			});
		}
		const rows = (c.entries || []).map((e) => [
			`${iw_esc(frappe.datetime.str_to_user(e.recorded_at))}<div class="text-muted">${iw_esc(
				e.shift || ""
			)}</div>`,
			...c.columns.map((col) => {
				const v = (e.readings || {})[col.label];
				return v
					? `<span${
							v.flag ? ' style="color:var(--red-600);font-weight:600"' : ""
					  }>${iw_esc(v.value)} ${iw_esc(v.unit || "")}</span>`
					: "";
			}),
			...(c.score_label ? [`<b>${iw_esc(e.score == null ? "" : e.score)}</b>`] : []),
			iw_esc(e.note || ""),
			iw_esc(e.by) +
				(e.second_check_by
					? `<div class="text-muted">${__("Checked")}: ${iw_esc(
							e.second_check_by
					  )}</div>`
					: ""),
		]);
		this.$panel.append(
			iw_table(
				[
					__("Time"),
					...c.columns.map((x) => iw_esc(x.label)),
					...(c.score_label ? [iw_esc(c.score_label)] : []),
					__("Remarks"),
					__("By"),
				],
				rows
			)
		);
	}

	// Theatre Doctor Notes (Bethesda, 20 Nov 2026): procedure notes, any
	// complications, date and time, by whom; kept on the booking's continuation
	// notes (added, never changed). Server side: theatre.doctor_notes / add_note.
	render_theatre_doctor_notes(d) {
		if (d.no_booking) {
			this.$panel.append(
				`<p class="text-muted">${__("Open the patient from the Theatre List.")}</p>`
			);
			return;
		}
		if (d.can_write)
			this.entry_card(
				__("Theatre Doctor Note"),
				[
					{
						fieldname: "noted_at",
						fieldtype: "Datetime",
						label: __("Date and Time"),
						default: frappe.datetime.now_datetime(),
						reqd: 1,
					},
					{ fieldtype: "Column Break" },
					{
						fieldname: "practitioner",
						fieldtype: "Link",
						options: "Healthcare Practitioner",
						label: __("By (Doctor)"),
						default: d.practitioner,
						reqd: 1,
					},
					{ fieldtype: "Column Break" },
					{
						fieldname: "stage",
						fieldtype: "Select",
						label: __("Stage"),
						options: "In theatre\nRecovery\nBack to ward",
						default: "In theatre",
					},
					{ fieldtype: "Section Break" },
					{
						fieldname: "note",
						fieldtype: "Small Text",
						label: __("Procedure Notes"),
						reqd: 1,
					},
					{ fieldtype: "Column Break" },
					{
						fieldname: "complications",
						fieldtype: "Small Text",
						label: __("Complications"),
						description: __("Leave empty if none."),
					},
				],
				__("Save Note"),
				(v) =>
					frappe.xcall("royce_health_ke.theatre.add_note", {
						booking: d.booking,
						note: v.note,
						stage: v.stage,
						noted_at: v.noted_at,
						complications: v.complications,
						practitioner: v.practitioner,
					})
			);
		this.$panel.append(
			iw_table(
				[
					__("Date and Time"),
					__("Stage"),
					__("Procedure Notes"),
					__("Complications"),
					__("By"),
				],
				(d.notes || []).map((n) => [
					iw_esc(frappe.datetime.str_to_user(n.noted_at)),
					iw_esc(__(n.stage || "")),
					iw_esc(n.note).replace(/\n/g, "<br>"),
					n.complications
						? `<span style="color:var(--red-600)">${iw_esc(n.complications).replace(
								/\n/g,
								"<br>"
						  )}</span>`
						: `<span class="text-muted">${__("None")}</span>`,
					`${iw_esc(n.doctor)}${
						n.by && n.by !== n.doctor
							? `<div class="text-muted">${__("Entered by")}: ${iw_esc(n.by)}</div>`
							: ""
					}`,
				])
			)
		);
	}

	// Partograph (Bethesda's 7-section form, 20 Nov 2026): one form that saves
	// a labour observation each time, and the delivery and the baby once, on
	// the admission's Delivery Record. Server side: royce_health_ke/partograph.py.
	async partograph_view() {
		const $panel = this.$panel;
		const $loading = $(
			`<p class="text-muted">${__("Loading the partograph...")}</p>`
		).appendTo($panel);
		const root = this.$panel;
		try {
			const d = await frappe.xcall("royce_health_ke.partograph.get", {
				inpatient_record: this.ip,
			});
			$loading.remove();
			this.$panel = $panel;
			this.partograph_render(d);
		} catch (e) {
			// never a blank panel (Bethesda, 21 Nov 2026: "the partograph hangs")
			console.error(e); // eslint-disable-line no-console
			$loading.remove();
			$panel.append(
				`<div class="alert alert-danger">${__(
					"The partograph could not open. Reload the page with Ctrl+Shift+R and try again; if it still fails, send the administrator this message:"
				)}<br><code>${iw_esc((e && (e.message || e.exc_type)) || String(e))}</code></div>`
			);
		} finally {
			this.$panel = root;
		}
	}

	partograph_render(d) {
		const v = d.values || {};
		const yn = "\nYes\nNo";
		const opt = (f) => "\n" + ((d.options || {})[f] || "").replace(/^\n+/, "");
		const keep = (df) => (v[df.fieldname] != null ? { ...df, default: v[df.fieldname] } : df);
		const F = (fieldname, label, fieldtype, extra) => ({
			fieldname,
			label,
			fieldtype: fieldtype || "Data",
			...(extra || {}),
		});
		const S = (f, label) => F(f, label, "Select", { options: opt(f) });
		// [section label, fields, kept between saves]
		const sections = [
			[
				__("Patient Information"),
				[
					F("gravida", __("Gravida"), "Int"),
					F("parity", __("Para")),
					F("previous_cs", __("Previous C-Section"), "Select", { options: yn }),
					F("membranes_ruptured_hours", __("Ruptured Membranes (hours ago)"), "Float", {
						description: v.membranes_ruptured_datetime
							? __("Recorded: ruptured at {0}", [
									frappe.datetime.str_to_user(v.membranes_ruptured_datetime),
							  ])
							: "",
					}),
				],
				true,
			],
			[
				__("Blood Group / Rh Factor"),
				[
					F("blood_group", __("Blood Group"), "Select", { options: "\nA\nB\nAB\nO" }),
					F("rhesus", __("Rhesus"), "Select", { options: "\nPositive\nNegative" }),
					F("haemoglobin", __("Hb (g/dL)"), "Float"),
					F("hb_flag", __("Hb Flag"), "Data", { read_only: 1 }),
				],
				true,
			],
			[
				__("Labour Progression"),
				[
					F("cervical_dilatation_cm", __("Cervical Dilation (cm)"), "Float"),
					S("descent", __("Descent of Head (fifths palpable)")),
					F("fetal_heart_rate", __("Fetal Heart Rate (bpm)"), "Int"),
					F("contractions_per_10min", __("Contractions per 10 min"), "Int"),
					F("contraction_duration_sec", __("Contraction Duration (seconds)"), "Int"),
					S("contraction_intensity", __("Intensity")),
					S("liquor", __("Amniotic Fluid")),
					S("moulding", __("Moulding")),
					F("oxytocin_rate", __("Oxytocin (drops/min)"), "Int"),
					F("drugs_and_fluids", __("Drugs and Fluids Given"), "Small Text"),
				],
				false,
			],
			[
				__("Vital Signs"),
				[
					F("bp_systolic", __("BP Systolic"), "Int"),
					F("bp_diastolic", __("BP Diastolic"), "Int"),
					F("temperature", __("Temp (°C)"), "Float"),
					F("maternal_pulse", __("Pulse Rate"), "Int"),
					S("urine_protein", __("Urine Protein")),
					S("urine_acetone", __("Urine Acetone")),
				],
				false,
			],
			[
				__("Delivery Details"),
				[
					F("induction", __("Induction of Labour"), "Select", { options: yn }),
					F("first_stage_hours", __("First Stage Duration (hours)"), "Float"),
					F("second_stage_minutes", __("Second Stage Duration (minutes)"), "Int"),
					F("third_stage_minutes", __("Third Stage Duration (minutes)"), "Int"),
					F("fourth_stage_hours", __("Fourth Stage Duration (hours)"), "Float"),
					F("vaginal_exams", __("Number of Vaginal Examinations"), "Int"),
					F("vaginal_exam_outcome", __("Vaginal Examinations Outcome")),
					S("mode_of_delivery", __("Mode of Delivery")),
					S("maternal_condition", __("Mother Status")),
					F("amtsl", __("AMTSL"), "Select", { options: yn }),
					S("uterotonic", __("Uterotonic")),
					F("blood_loss_ml", __("Blood Loss (ml)"), "Int"),
					F("placenta_complete", __("Placenta Complete"), "Select", { options: yn }),
					S("perineum", __("Episiotomy / Tear")),
					F("perineum_repaired", __("Repair"), "Select", { options: yn }),
					F("mother_pulse", __("Pulse"), "Int"),
					F("mother_temperature", __("Temperature (°C)"), "Float"),
					F("mother_resp_rate", __("Respiration Rate"), "Int"),
					F("complication", __("Delivery Complication"), "Select", {
						options:
							"\nAPH\nPPH\nEclampsia\nRuptured uterus\nObstructed labour\nSepsis",
					}),
					F("other_complications", __("Other Complications"), "Small Text"),
				],
				true,
			],
			[
				__("Baby Information"),
				[
					S("outcome", __("Birth Outcome (alive)")),
					S("sex", __("Sex")),
					F("apgar_1", __("APGAR Score (1 minute)"), "Int"),
					F("apgar_5", __("APGAR Score (5 minutes)"), "Int"),
					F("apgar_10", __("APGAR Score (10 minutes)"), "Int"),
					F("birth_weight_g", __("Birth Weight (grams)"), "Int"),
					F("length_cm", __("Birth Length (cm)"), "Float"),
					F("head_circumference_cm", __("Head Circumference (cm)"), "Float"),
					F("deformity", __("Deformity (describe)")),
					F("teo", __("TEO (tetracycline) Given at Birth"), "Select", { options: yn }),
					F("chlorhexidine", __("Chlorhexidine Applied"), "Select", { options: yn }),
					F("vitamin_k", __("Vitamin K Given"), "Select", { options: yn }),
					S("infant_prophylaxis", __("Infant Prophylaxis")),
					F("asphyxia", __("Baby with Asphyxia"), "Select", { options: yn }),
					F("resuscitated", __("Baby Successfully Resuscitated"), "Select", {
						options: yn,
					}),
					S("cause_of_death", __("Cause of Neonatal Death")),
					F("drugs_given", __("Drugs Given"), "Small Text"),
				],
				true,
			],
			[
				__("Additional Notes"),
				[
					F("delivery_datetime", __("Date & Time of Delivery"), "Datetime"),
					F("birth_notification_number", __("Birth Notification Number")),
					F("delivered_by", __("Delivered By"), "Link", {
						options: "Healthcare Practitioner",
					}),
				],
				true,
			],
		];

		const done = d.docstatus === 1;
		const buttons = [];
		if (d.delivery && !done)
			buttons.push([__("Complete Delivery"), () => this.partograph_complete(), true]);
		if (d.delivery) {
			buttons.push([
				__("Open Delivery Record"),
				() => frappe.set_route("Form", "Delivery Record", d.delivery),
			]);
			buttons.push([
				__("Labour Care Guide"),
				() =>
					window.open(
						`/printview?doctype=Delivery%20Record&name=${encodeURIComponent(
							d.delivery
						)}&format=${encodeURIComponent(
							"Labour Care Guide"
						)}&no_letterhead=1&trigger_print=1`,
						"_blank"
					),
			]);
		}
		this.$panel.append(`<div class="mb-2"><h5 class="mb-1">${__("Partograph")}</h5>
			<div class="small text-muted">${
				done
					? __("Delivery completed: {0}", [iw_esc(d.delivery)])
					: d.delivery
					? __(
							"In labour. Each save adds an observation; delivery and baby details are kept and can be corrected until the delivery is completed."
					  )
					: __("Not started. The first save opens the labour record.")
			}</div></div>`);
		if (buttons.length) this.buttons(buttons);

		if (!done && frappe.model.can_create("Delivery Record")) {
			const layout = [
				{
					fieldname: "observation_time",
					fieldtype: "Datetime",
					label: __("Observation Time"),
					default: frappe.datetime.now_datetime(),
					reqd: 1,
				},
			];
			sections.forEach(([label, fields, kept]) => {
				layout.push({ fieldtype: "Section Break", label });
				const per = Math.ceil(fields.length / 3);
				fields.forEach((df, i) => {
					if (i && i % per === 0) layout.push({ fieldtype: "Column Break" });
					layout.push(kept ? keep(df) : df);
				});
			});
			this.entry_card(__("Partograph"), layout, __("Save"), (vals, fg) => {
				delete vals.hb_flag;
				return frappe.xcall("royce_health_ke.partograph.record", {
					inpatient_record: this.ip,
					values: vals,
				});
			});
		}

		const o = d.observations || [];
		const cell = (r, f) => iw_esc(r[f] == null ? "" : r[f]);
		this.$panel.append(`<div class="mb-1"><b>${__("Labour observations")}</b></div>`);
		this.$panel.append(
			iw_table(
				[
					__("Time"),
					__("Cervix (cm)"),
					__("Descent"),
					__("FHR"),
					__("Contractions /10 min"),
					__("Liquor"),
					__("Moulding"),
					__("BP"),
					__("Pulse"),
					__("Temp"),
					__("Urine P / A"),
					__("Oxytocin"),
					__("Drugs and fluids"),
					__("Alert"),
					__("By"),
				],
				o.map((r) => [
					iw_esc(frappe.datetime.str_to_user(r.time)),
					cell(r, "cervical_dilatation_cm"),
					cell(r, "descent"),
					cell(r, "fetal_heart_rate"),
					`${cell(r, "contractions_per_10min")} ${cell(r, "contraction_intensity")}`,
					cell(r, "liquor"),
					cell(r, "moulding"),
					r.bp_systolic ? `${cell(r, "bp_systolic")}/${cell(r, "bp_diastolic")}` : "",
					cell(r, "maternal_pulse"),
					cell(r, "temperature"),
					[r.urine_protein, r.urine_acetone].filter(Boolean).map(iw_esc).join(" / "),
					cell(r, "oxytocin_rate"),
					cell(r, "drugs_and_fluids"),
					r.alert
						? `<span style="color:var(--red-600);font-weight:600">${iw_esc(
								r.alert
						  )}</span>`
						: "",
					iw_esc(r.by),
				])
			)
		);
	}

	partograph_complete() {
		frappe.confirm(
			__(
				"Complete the delivery? The record is then final, the pregnancy is marked delivered and each live baby gets a patient record."
			),
			async () => {
				const name = await frappe.xcall("royce_health_ke.partograph.complete", {
					inpatient_record: this.ip,
				});
				frappe.show_alert({
					message: __("Delivery {0} completed", [name]),
					indicator: "green",
				});
				this.show(this.panel_name);
			}
		);
	}

	// Drug Administration (Bethesda, 20 Nov 2026): Prescription (the drug
	// screen, royce_health_ke.DrugOrder), Dispensing and Administration Log.
	render_drug_administration(d) {
		const $root = this.$panel;
		const views = [
			["prescription", __("Prescription")],
			["dispensing", __("Dispensing")],
			["log", __("Administration Log")],
		];
		const $row = $(`<div class="row">
			<div class="col-md-2 mb-3"><div class="list-group">${views
				.map(
					([k, l]) =>
						`<a href="#" class="list-group-item list-group-item-action py-2" data-view="${k}">${l}</a>`
				)
				.join("")}</div></div>
			<div class="col-md-10 iw-drug-body"></div></div>`).appendTo($root);
		const show = (key) => {
			this.__drug_view = key;
			$row.find("[data-view]").removeClass("active");
			$row.find(`[data-view="${key}"]`).addClass("active");
			this.$panel = $row.find(".iw-drug-body").empty();
			try {
				this["drug_" + key](d);
			} finally {
				this.$panel = $root;
			}
		};
		$row.find("[data-view]").on("click", (e) => {
			e.preventDefault();
			show($(e.currentTarget).data("view"));
		});
		show(this.__drug_view || "prescription");
	}

	drug_prescription() {
		if (!(window.royce_health_ke && royce_health_ke.DrugOrder)) return;
		new royce_health_ke.DrugOrder({
			wrapper: $("<div></div>").appendTo(this.$panel),
			ward: this.ip,
			get_encounter: () =>
				frappe.xcall("royce_health_ke.prescribing.ward_encounter", {
					inpatient_record: this.ip,
				}),
		});
	}

	drug_dispensing(d) {
		this.$panel.append(
			`<p class="small text-muted">${
				d.charge === "On administration"
					? __(
							"Drugs are charged when given. A dose can be given once the pharmacy has sent it to the bed."
					  )
					: __(
							"Drugs are charged when the pharmacy sends them. A dose can be given once it has been sent."
					  )
			}</p>`
		);
		const status = (counts) =>
			Object.entries(counts || {})
				.map(([k, v]) => {
					const label =
						{
							Pending: __("waiting for pharmacy"),
							Transferred: __("at the bedside"),
							Completed: __("given"),
							Stopped: __("stopped"),
						}[k] || k;
					const colour =
						{
							Pending: "orange",
							Transferred: "blue",
							Completed: "green",
							Stopped: "gray",
						}[k] || "gray";
					return `<span class="indicator-pill ${colour} mr-1">${v} ${iw_esc(
						label
					)}</span>`;
				})
				.join("");
		const can_stop = frappe.user.has_role([
			"Physician",
			"Healthcare Administrator",
			"System Manager",
		]);
		const rows = (d.active || []).map((a) => [
			`<b>${iw_esc(a.drug_name || a.drug)}</b><div class="text-muted">${iw_esc(
				a.instructions || ""
			)}</div>`,
			iw_esc(a.dose),
			a.next ? iw_esc(frappe.datetime.str_to_user(a.next)) : "",
			status(a.counts),
			can_stop && (a.counts.Pending || a.counts.Transferred)
				? `<button class="btn btn-xs btn-default iw-stop" data-order="${iw_esc(
						a.order
				  )}" data-drug="${iw_esc(a.drug)}">${__("Stop")}</button>`
				: "",
		]);
		this.$panel.append(`<h6>${__("Active prescriptions")}</h6>`);
		this.$panel.append(
			iw_table([__("Drug"), __("Per dose"), __("Next dose"), __("Doses"), ""], rows)
		);
		this.$panel.find(".iw-stop").on("click", (e) => {
			const $b = $(e.currentTarget);
			frappe.prompt(
				{
					fieldname: "reason",
					fieldtype: "Small Text",
					label: __("Why stop it?"),
					reqd: 1,
				},
				(v) =>
					frappe
						.xcall(IW + "stop_drug", {
							order: $b.data("order"),
							drug: $b.data("drug"),
							reason: v.reason,
						})
						.then(() => this.show("Drug Administration"))
			);
		});
	}

	drug_log(d) {
		this.buttons([[__("Medication Round"), () => this.nursing("medication"), false]]);
		if (frappe.model.can_write("Medication Administration")) this.give_dose_card();
		const doses = (d.doses || []).map((x) => [
			iw_esc(frappe.datetime.str_to_user(x.scheduled_time)),
			iw_esc(x.drug_name || ""),
			iw_esc(x.dosage || ""),
			iw_esc(__(x.status)),
			x.administered_time ? iw_esc(frappe.datetime.str_to_user(x.administered_time)) : "",
			iw_esc(x.by || ""),
			iw_esc(x.reason || ""),
		]);
		this.$panel.append(`<h6 class="mt-3">${__("Treatment sheet")}</h6>`);
		this.$panel.append(
			iw_table(
				[
					__("Due"),
					__("Drug"),
					__("Dose"),
					__("Status"),
					__("Given at"),
					__("By"),
					__("Comment"),
				],
				doses
			)
		);
	}

	// Give Dose (v0.58): a form over the treatment sheet, as on the other tabs.
	// The dose list is the round's (due now, held, refused, recently missed).
	give_dose_card() {
		const fg = this.entry_card(
			__("Give Dose"),
			[
				{
					fieldname: "administration",
					fieldtype: "Select",
					label: __("Dose"),
					reqd: 1,
					options: [""],
				},
				{ fieldtype: "Column Break" },
				{
					fieldname: "status",
					fieldtype: "Select",
					label: __("Status"),
					options: "Given\nHeld\nRefused\nNot Available",
					default: "Given",
					reqd: 1,
				},
				{ fieldtype: "Column Break" },
				{
					fieldname: "route",
					fieldtype: "Select",
					label: __("Route"),
					options:
						"\nOral\nIV\nIM\nSC\nSublingual\nTopical\nInhalation\nRectal\nNasogastric\nOther",
				},
				{ fieldtype: "Section Break" },
				{
					fieldname: "second_check_by",
					fieldtype: "Link",
					options: "User",
					label: __("Second Check By"),
				},
				{ fieldtype: "Column Break" },
				{
					fieldname: "reason",
					fieldtype: "Small Text",
					label: __("Comment"),
					description: __("Needed when the dose is not given."),
				},
			],
			__("Record Dose"),
			(v) =>
				frappe.xcall(IW + "give_dose", {
					inpatient_record: this.ip,
					administration: v.administration,
					status: v.status,
					route: v.route,
					reason: v.reason,
					second_check_by: v.second_check_by,
				})
		);
		frappe.xcall(IW + "due_doses", { inpatient_record: this.ip }).then((doses) => {
			const f = fg.fields_dict.administration;
			const when = (t) => frappe.datetime.str_to_user(t);
			f.df.options = [{ label: "", value: "" }].concat(
				(doses || []).map((x) => ({
					value: x.name,
					label: `${when(x.scheduled_time)} · ${x.drug_name} ${x.dosage || ""} ${
						x.dosage_form || ""
					}${x.status === "Scheduled" ? "" : " (" + __(x.status) + ")"}`,
				}))
			);
			f.df.description = (doses || []).length
				? ""
				: __(
						"No doses due. A dose shows here once the pharmacy has sent the drug to the bed."
				  );
			f.refresh();
			f.df.onchange = () => {
				const x = (doses || []).find((y) => y.name === fg.get_value("administration"));
				if (x && x.route) fg.set_value("route", x.route);
			};
		});
	}

	render_billing(d) {
		this.$panel.append(`<div class="d-flex flex-wrap mb-3">
			${[
				[__("Running bill"), d.total],
				[__("Billed"), d.billed],
				[__("Not yet billed"), d.unbilled],
				[__("Paid"), d.paid],
				[__("Owed on bills"), d.outstanding],
			]
				.map(
					([l, v]) =>
						`<div class="mr-4"><span class="text-muted small">${l}</span><br><b>${iw_money(
							v
						)}</b></div>`
				)
				.join("")}</div>`);
		this.$panel.append(`<h6>${__("Not yet billed")}</h6>`);
		this.$panel.append(
			iw_table(
				[__("Item"), __("Qty"), __("Rate"), __("Amount")],
				(d.lines || []).map((l) => [
					iw_esc(l.what),
					iw_esc(l.qty),
					iw_money(l.rate),
					iw_money(l.amount),
				])
			)
		);
		this.$panel.append(`<h6 class="mt-3">${__("Bills")}</h6>`);
		this.$panel.append(
			iw_table(
				[__("Invoice"), __("Date"), __("Total"), __("Owed")],
				(d.invoices || []).map((i) => [
					`<a href="/desk/sales-invoice/${encodeURIComponent(i.name)}">${iw_esc(
						i.name
					)}</a>`,
					iw_when(i.posting_date),
					iw_money(i.grand_total),
					iw_money(i.outstanding_amount),
				])
			)
		);
	}

	render_discharge(d) {
		const list = [];
		if (d.status === "Admitted")
			list.push([__("Plan Discharge"), () => this.plan_discharge(), true]);
		if (d.summary) {
			list.push([
				__("Open Discharge Summary"),
				() => frappe.set_route("Form", "Discharge Summary", d.summary.name),
				!list.length,
			]);
			list.push([
				__("Print Discharge Summary"),
				() =>
					window.open(
						`/printview?doctype=Discharge%20Summary&name=${encodeURIComponent(
							d.summary.name
						)}&format=Patient%20Discharge%20Summary`,
						"_blank"
					),
			]);
		} else {
			list.push([
				__("Write Discharge Summary"),
				() =>
					frappe.model.open_mapped_doc({
						method: "healthcare.healthcare.doctype.inpatient_record.inpatient_record.make_discharge_summary",
						source_name: this.ip,
					}),
			]);
		}
		list.push([
			__("Discharge (admission record)"),
			() => frappe.set_route("Form", "Inpatient Record", this.ip),
		]);
		this.buttons(list);
		this.$panel.append(`<div class="small">
			<p><b>${__("Status")}:</b> ${iw_esc(__(d.status))}</p>
			${
				d.discharge_ordered_date
					? `<p><b>${__("Discharge planned for")}:</b> ${iw_when(
							d.discharge_ordered_date
					  )}</p>`
					: ""
			}
			${
				d.discharge_instructions
					? `<p><b>${__("Instructions")}:</b> ${iw_esc(d.discharge_instructions)}</p>`
					: ""
			}
			${d.followup_date ? `<p><b>${__("Follow-up")}:</b> ${iw_when(d.followup_date)}</p>` : ""}
			<p class="text-muted">${__(
				"Discharging checks that nursing tasks are done, the bill is invoiced and requests are closed (Marley). Return or sell leftover bedside drugs from the admission record."
			)}</p></div>`);
	}

	plan_discharge() {
		frappe.prompt(
			[
				{
					fieldname: "discharge_ordered_date",
					fieldtype: "Date",
					label: __("Discharge Date"),
					default: frappe.datetime.get_today(),
					reqd: 1,
				},
				{ fieldname: "followup_date", fieldtype: "Date", label: __("Follow-up Date") },
				{
					fieldname: "discharge_instructions",
					fieldtype: "Small Text",
					label: __("Instructions for the patient"),
				},
			],
			(v) =>
				frappe
					.xcall(
						"healthcare.healthcare.doctype.inpatient_record.inpatient_record.schedule_discharge",
						{
							discharge_order: JSON.stringify({
								patient: this.data.patient,
								discharge_practitioner: this.data.practitioner,
								...v,
							}),
						}
					)
					.then(() => this.load(this.ip)),
			__("Plan Discharge"),
			__("Save")
		);
	}
}
