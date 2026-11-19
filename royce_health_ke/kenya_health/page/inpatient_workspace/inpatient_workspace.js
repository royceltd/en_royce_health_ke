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
		this.$banner
			.find(".iw-preauth")
			.on("click", () =>
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

	render_vitals(d) {
		this.buttons([[__("Record Vital Signs"), () => this.nursing("vitals"), true]]);
		const rows = (d.rows || [])
			.slice()
			.reverse()
			.map((v) => [
				`${iw_when(v.signs_date)} ${iw_esc((v.signs_time || "").slice(0, 5))}`,
				iw_esc(v.temperature || ""),
				iw_esc(v.pulse || ""),
				iw_esc(v.respiratory_rate || ""),
				iw_esc(v.bp || (v.bp_systolic ? `${v.bp_systolic}/${v.bp_diastolic || "?"}` : "")),
				iw_esc(v.ke_spo2 || ""),
				iw_esc(v.weight || ""),
				`<span style="color:var(--red-600)">${iw_esc(v.ke_vitals_flags || "")}</span>`,
			]);
		this.$panel.append(
			iw_table(
				[
					__("Taken"),
					__("Temp"),
					__("Pulse"),
					__("Resp"),
					__("BP"),
					"SpO2",
					__("Weight"),
					__("Flags"),
				],
				rows
			)
		);
	}

	render_requests(d) {
		this.buttons([
			[__("Ward Round: new requests or medicines"), () => this.ward_round(), true],
		]);
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
		this.buttons([[__("Ward Round: update the diagnosis"), () => this.ward_round(), true]]);
		const rows = (d.diagnoses || []).map((x) => [
			iw_esc(x.diagnosis),
			x.code ? `ICD-11 ${iw_esc(x.code)}` : "",
			iw_when(x.date),
			iw_esc(x.by || ""),
		]);
		this.$panel.append(iw_table([__("Diagnosis"), __("Code"), __("Date"), __("By")], rows));
	}

	render_nursing_notes(d) {
		this.buttons([
			[__("Add Nursing Note"), () => this.nursing("notes"), true],
			[__("Shift Handover"), () => this.nursing("handover")],
			[__("Nursing Tasks"), () => this.nursing("nursing_tasks")],
		]);
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
				)} · ${iw_esc(n.by)} · ${iw_esc(n.clinical_note_type || "")}</div>
					<div style="white-space:pre-wrap">${
						frappe.utils.html2text
							? iw_esc(frappe.utils.html2text(n.note || ""))
							: iw_esc(n.note || "")
					}</div>${fdar}</div>`;
			})
			.join("");
		this.$panel.append(
			notes ||
				`<p class="text-muted">${__(
					"No nursing notes yet. Record the admission assessment first."
				)}</p>`
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
		(d.charts || []).forEach((c) => {
			const $c = $(
				`<div class="mb-4 p-3" style="border:1px solid var(--border-color);border-radius:8px"></div>`
			).appendTo(this.$panel);
			const totals = Object.entries(c.totals || {})
				.map(([k, v]) => `${iw_esc(k)}: <b>${iw_esc(v)}</b>`)
				.join(" · ");
			$c.append(`<div class="d-flex justify-content-between align-items-center mb-2">
				<div><b>${iw_esc(c.name)}</b> ${
				c.second_check
					? `<span class="indicator-pill orange">${__("Second nurse checks")}</span>`
					: ""
			}
				${c.due ? `<span class="small text-muted ml-2">${__("Next due")}: ${iw_when(c.due)}</span>` : ""}
				${totals ? `<div class="small">${__("Last 24 hours")}: ${totals}</div>` : ""}</div>
				<button class="btn btn-xs btn-primary">${__("Add Entry")}</button></div>`);
			$c.find("button").on("click", () => this.chart_entry(c));
			const rows = (c.entries || []).map((e) => [
				`${iw_esc(
					frappe.datetime.str_to_user(e.recorded_at)
				)}<div class="text-muted">${iw_esc(e.shift || "")}</div>`,
				...c.columns.map((col) => {
					const v = (e.readings || {})[col.label];
					return v
						? `<span${
								v.flag ? ' style="color:var(--red-600);font-weight:600"' : ""
						  }>${iw_esc(v.value)} ${iw_esc(v.unit || "")}</span>`
						: "";
				}),
				iw_esc(e.note || ""),
				iw_esc(e.by) +
					(e.second_check_by
						? `<div class="text-muted">${__("Checked")}: ${iw_esc(
								e.second_check_by
						  )}</div>`
						: ""),
			]);
			$c.append(
				iw_table(
					[__("Time"), ...c.columns.map((x) => iw_esc(x.label)), __("Note"), __("By")],
					rows
				)
			);
		});
		if (!(d.charts || []).length)
			this.$panel.append(
				`<p class="text-muted">${__(
					"No charts set up. Add them in Nursing Chart Template."
				)}</p>`
			);
	}

	chart_entry(c) {
		const fields = c.columns.map((col) => {
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
			if (col.kind === "Choice")
				return {
					fieldname,
					label,
					fieldtype: "Select",
					options: "\n" + (col.options || ""),
					reqd: col.reqd,
				};
			return { fieldname, label, fieldtype: "Data", reqd: col.reqd };
		});
		fields.push({
			fieldname: "recorded_at",
			fieldtype: "Datetime",
			label: __("Time"),
			default: frappe.datetime.now_datetime(),
		});
		if (c.second_check)
			fields.push({
				fieldname: "second_check_by",
				fieldtype: "Link",
				options: "User",
				label: __("Checked by (second nurse)"),
				reqd: 1,
			});
		fields.push({ fieldname: "note", fieldtype: "Small Text", label: __("Note") });
		const d = new frappe.ui.Dialog({
			title: c.name,
			fields,
			primary_action_label: __("Save"),
			primary_action: (v) => {
				const values = {};
				c.columns.forEach((col) => {
					const value = v[col.fieldname];
					if (value !== undefined && value !== null && value !== "")
						values[col.label] = value;
				});
				frappe
					.xcall("royce_health_ke.charts.record", {
						inpatient_record: this.ip,
						template: c.name,
						values,
						note: v.note,
						second_check_by: v.second_check_by,
						recorded_at: v.recorded_at,
					})
					.then(() => {
						d.hide();
						frappe.show_alert({ message: __("Recorded"), indicator: "green" });
						this.show("Nursing Care");
					});
			},
		});
		d.show();
	}

	render_drug_administration(d) {
		this.buttons([
			[__("Medication Round"), () => this.nursing("medication"), true],
			[__("Prescribe on the Ward Round"), () => this.ward_round()],
		]);
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
