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
	const ip = frappe.get_route()[1];
	if (wrapper.iw && ip) wrapper.iw.load(ip);
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
		page.set_secondary_action(__("Ward"), () => frappe.set_route("ward"));
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

	async load(ip) {
		this.ip = ip;
		this.data = await frappe.xcall(IW + "workspace", { inpatient_record: ip });
		this.page.set_title(this.data.patient_name);
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
				${chip(__("Doctor"), d.practitioner)}
				${chip(__("Payer"), d.payer)}
				${chip(__("Allergies"), d.allergies, "red")}
				${chip(__("Status"), __(d.status))}
			</div>
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
		const data = await frappe.xcall(IW + "panel", { inpatient_record: this.ip, panel });
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
			fg.__resolving = true;
			const set = {};
			if (r.diagnosis && fg.get_value("diagnosis") !== r.diagnosis)
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
		]);
		this.$panel.append(`<div class="small">
			<p><b>${__("Outcome")}:</b> ${iw_esc(__(d.outcome || "Not set"))}${
			d.referred_to ? ` · ${__("Referred to")} ${iw_esc(d.referred_to)}` : ""
		}</p>
			${d.note ? `<p>${iw_esc(d.note)}</p>` : ""}
			<p class="text-muted">${__("MOH 717 counts the admission by this outcome.")}</p></div>`);
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
		this.buttons([[__("Medication Round"), () => this.nursing("medication"), true]]);
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
