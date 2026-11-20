/* global royce_health_ke */
// Copyright (c) 2026, Royce Technologies LTD and contributors
// For license information, please see license.txt

// The drug screen (royce_health_ke.prescribing), to Bethesda's design of
// 20 Nov 2026: "Add Prescription" on the left, "Current Prescription" on the
// right (Pending, Sent, Active, Past, Chronic), the Medication Mapping note,
// Save Prescription. Used on the consultation's Prescription tab and on the
// ward's Drug Administration tab: new royce_health_ke.DrugOrder({...}).
frappe.provide("royce_health_ke");

royce_health_ke.DrugOrder = class DrugOrder {
	constructor({ wrapper, get_encounter, ward = false, on_sent = null, on_change = null }) {
		this.$w = $(wrapper);
		this.get_encounter = get_encounter; // () => Promise<encounter name>
		this.ward = ward; // the Inpatient Record on the ward, else false
		this.on_sent = on_sent;
		this.on_change = on_change; // after a drug is added or removed (the consultation was saved)
		this.list = "pending";
		this.data = { pending: [], sent: [], active: [], past: [], chronic: [] };
		this.method = "royce_health_ke.prescribing.";
		this.make();
		this.load();
	}

	call(name, args) {
		return frappe.xcall(this.method + name, args);
	}

	make() {
		const lists = [
			["pending", __("Pending")],
			["sent", this.ward ? __("Sent today") : __("Sent")],
			["active", __("Active Prescriptions")],
			["past", __("Past")],
			["chronic", __("Chronic")],
		];
		this.$w.html(`<div class="row ke-do">
			<div class="col-lg-5 mb-3 ke-do-left">
				<div class="p-3 h-100" style="border:1px solid var(--border-color);border-radius:8px">
					<div class="d-flex justify-content-between align-items-center mb-2">
						<b>${__("Add Prescription")}</b>
						<span class="ke-do-stock indicator-pill gray" style="display:none"></span>
					</div>
					<div class="btn-group btn-group-sm mb-2 ke-do-mode">
						<button class="btn btn-primary" data-mode="single">${__("Single Drug")}</button>
						<button class="btn btn-default" data-mode="package">${__("Drug Package")}</button>
					</div>
					<div class="ke-do-form"></div>
					<div class="text-right">
						<button class="btn btn-sm btn-default ke-do-reset">${__("Reset")}</button>
						<button class="btn btn-sm btn-success ke-do-add">+ ${__("Add Prescription")}</button>
					</div>
				</div>
			</div>
			<div class="col-lg-7 mb-3">
				<div class="p-3 h-100" style="border:1px solid var(--border-color);border-radius:8px">
					<div class="d-flex justify-content-between align-items-center mb-2">
						<b>${__("Current Prescription")}</b>
						<select class="form-control form-control-sm ke-do-list" style="width:auto">
							${lists.map(([k, l]) => `<option value="${k}">${l}</option>`).join("")}
						</select>
					</div>
					<div class="ke-do-table" style="overflow-x:auto"></div>
					<div class="ke-do-mapping"></div>
					<div class="text-right mt-2 ke-do-actions">
						<span class="small text-muted mr-2">${__(
							"Drugs added are kept as a draft until you Save Prescription."
						)}</span>
						<button class="btn btn-sm btn-success ke-do-save">${__("Save Prescription")}</button>
					</div>
				</div>
			</div>
		</div>`);
		this.$w.find(".ke-do-list").on("change", (e) => {
			this.list = $(e.currentTarget).val();
			this.render();
		});
		this.$w.find(".ke-do-save").on("click", () => this.save());
		this.$w.find(".ke-do-add").on("click", () => this.add());
		this.$w.find(".ke-do-reset").on("click", () => this.reset());
		this.$w
			.find(".ke-do-mode button")
			.on("click", (e) => this.set_mode($(e.currentTarget).data("mode")));
		this.make_form();
	}

	make_form() {
		const routes =
			(frappe.meta.get_docfield("Drug Prescription", "ke_route") || {}).options || "";
		const single = "eval:doc.mode!=='package'";
		const fg = (this.fg = new frappe.ui.FieldGroup({
			body: this.$w.find(".ke-do-form"),
			fields: [
				{ fieldname: "mode", fieldtype: "Data", hidden: 1, default: "single" },
				{
					fieldname: "package",
					fieldtype: "Link",
					options: "Treatment Plan Template",
					label: __("Drug Package"),
					depends_on: "eval:doc.mode==='package'",
					get_query: () => ({ query: this.method + "package_query" }),
				},
				{
					fieldname: "drug_class",
					fieldtype: "Autocomplete",
					label: __("Drug Class"),
					depends_on: single,
				},
				{
					fieldname: "drug_code",
					fieldtype: "Link",
					options: "Item",
					label: __("Drug Name"),
					reqd: 1,
					depends_on: single,
					get_query: () => ({
						query: this.method + "drug_query",
						filters: { drug_class: fg.get_value("drug_class") || "" },
					}),
					onchange: () => this.drug_changed(),
				},
				{
					fieldname: "ke_buy_externally",
					fieldtype: "Check",
					label: __("Buy Externally"),
					depends_on: single,
				},
				{ fieldtype: "Section Break", depends_on: single },
				{
					fieldname: "ke_dose",
					fieldtype: "Float",
					label: __("Dose"),
					reqd: 1,
					description: __("e.g. 500 mg or 5 ml"),
					onchange: () => this.preview(),
				},
				{
					fieldname: "ke_dose_uom",
					fieldtype: "Link",
					options: "UOM",
					label: __("Dose Unit"),
					onchange: () => this.preview(),
				},
				{
					fieldname: "duration",
					fieldtype: "Int",
					label: __("Duration"),
					reqd: 1,
					onchange: () => this.preview(),
				},
				{
					fieldname: "ke_start_date",
					fieldtype: "Date",
					label: __("Start Date"),
					reqd: 1,
					default: frappe.datetime.get_today(),
				},
				{ fieldtype: "Column Break" },
				{
					fieldname: "dosage",
					fieldtype: "Link",
					options: "Prescription Dosage",
					label: __("Frequency"),
					depends_on: "eval:!doc.dosage_by_interval",
					onchange: () => this.preview(),
				},
				{
					fieldname: "dosage_by_interval",
					fieldtype: "Check",
					label: __("Schedule dosage (every N hours)"),
					onchange: () => this.preview(),
				},
				{
					fieldname: "interval",
					fieldtype: "Int",
					label: __("Every (hours)"),
					depends_on: "eval:doc.dosage_by_interval",
					onchange: () => this.preview(),
				},
				{
					fieldname: "duration_unit",
					fieldtype: "Select",
					options: "Day\nWeek\nMonth\nHour",
					default: "Day",
					label: __("Duration Unit"),
					onchange: () => this.preview(),
				},
				{
					fieldname: "ke_route",
					fieldtype: "Select",
					options: routes,
					label: __("Route"),
					reqd: 1,
				},
				{
					fieldname: "ke_start_time",
					fieldtype: "Time",
					label: __("Start Time"),
					reqd: 1,
					default: frappe.datetime.now_time(),
				},
				{ fieldtype: "Section Break", depends_on: single },
				{
					fieldname: "comment",
					fieldtype: "Small Text",
					label: __("Instructions"),
					description: __("e.g. Take after meals"),
				},
				{
					fieldname: "ke_quantity",
					fieldtype: "Int",
					label: __("Quantity"),
					reqd: 1,
					description: __("Worked out from the dose; change it if needed."),
				},
				{
					fieldname: "unit",
					fieldtype: "Data",
					label: __("Dispensing Unit"),
					read_only: 1,
				},
				{
					fieldname: "ke_chronic",
					fieldtype: "Check",
					label: __("Chronic medicine"),
					hidden: this.ward ? 1 : 0,
				},
			],
		}));
		fg.make();
		this.call("drug_classes").then((c) => fg.get_field("drug_class").set_data(c || []));
	}

	set_mode(mode) {
		this.$w.find(".ke-do-mode button").removeClass("btn-primary").addClass("btn-default");
		this.$w
			.find(`.ke-do-mode button[data-mode="${mode}"]`)
			.removeClass("btn-default")
			.addClass("btn-primary");
		this.fg.set_value("mode", mode);
		this.fg.refresh_dependency();
		this.$w.find(".ke-do-stock").toggle(mode !== "package" && !!this.info);
	}

	reset() {
		const keep = { drug_class: this.fg.get_value("drug_class") };
		this.fg.fields_list.forEach((f) => {
			if (f.df.fieldname && !["mode", "drug_class"].includes(f.df.fieldname))
				f.set_value(f.df.default || "");
		});
		this.fg.set_values(keep);
		this.info = null;
		this.$w.find(".ke-do-stock").hide();
	}

	drug_changed() {
		const item = this.fg.get_value("drug_code");
		const $stock = this.$w.find(".ke-do-stock");
		this.info = null;
		if (!item) return $stock.hide();
		this.call("drug_info", { item_code: item }).then((info) => {
			this.info = info;
			if (info.stock === null || info.stock === undefined) $stock.hide();
			else
				$stock
					.removeClass("gray green red")
					.addClass(info.stock > 0 ? "green" : "red")
					.text(
						__("Available: {0} {1}", [format_number(info.stock), info.stock_uom || ""])
					)
					.show();
			const set = { unit: info.stock_uom || "" };
			if (info.dose_uom && !this.fg.get_value("ke_dose_uom"))
				set.ke_dose_uom = info.dose_uom;
			if (info.route && !this.fg.get_value("ke_route")) set.ke_route = info.route;
			if (info.dosage && !this.fg.get_value("dosage")) set.dosage = info.dosage;
			if (info.duration && !this.fg.get_value("duration")) {
				set.duration = info.duration;
				set.duration_unit = info.duration_unit || "Day";
			}
			this.fg.set_values(set).then(() => this.preview());
		});
	}

	async row() {
		const v = this.fg.get_values(true) || {};
		const period = v.duration
			? await this.call("duration", { number: v.duration, unit: v.duration_unit || "Day" })
			: null;
		return {
			drug_code: v.drug_code,
			medication: this.info && this.info.medication,
			ke_dose: v.ke_dose,
			ke_dose_uom: v.ke_dose_uom,
			dosage: v.dosage_by_interval ? null : v.dosage,
			dosage_by_interval: v.dosage_by_interval ? 1 : 0,
			interval: v.dosage_by_interval ? v.interval : null,
			interval_uom: v.dosage_by_interval ? "Hour" : null,
			period,
			ke_route: v.ke_route,
			ke_start_date: v.ke_start_date,
			ke_start_time: v.ke_start_time,
			comment: v.comment,
			ke_quantity: v.ke_quantity,
			ke_buy_externally: v.ke_buy_externally ? 1 : 0,
			ke_chronic: v.ke_chronic ? 1 : 0,
		};
	}

	// The quantity in dispensing units and the mapping note, as the doctor types
	async preview() {
		const v = this.fg.get_values(true) || {};
		if (!v.drug_code || !v.duration || !(v.dosage || (v.dosage_by_interval && v.interval)))
			return;
		const row = await this.row();
		row.ke_quantity = null;
		const r = await this.call("preview", { row });
		if (!r) return;
		this.fg.set_value("ke_quantity", r.quantity);
		if (r.unit) this.fg.set_value("unit", r.unit);
		this.show_mapping(r.text);
	}

	show_mapping(text) {
		this.$w
			.find(".ke-do-mapping")
			.html(
				text
					? `<div class="alert alert-success small mt-2 mb-0"><b>${__(
							"Medication Mapping"
					  )}</b><br>${frappe.utils.escape_html(text)}</div>`
					: ""
			);
	}

	async encounter() {
		if (!this.name) this.name = await this.get_encounter();
		return this.name;
	}

	async load() {
		if (this.ward) {
			// the ward: today's open ward-round prescription, if any; one is made on the first drug
			this.data = await this.call("ward_lists", { inpatient_record: this.ward });
			this.name = this.data.encounter || null;
		} else {
			const name = await this.encounter();
			this.data = await this.call("current", { encounter: name });
		}
		const open = this.ward ? this.data.can_prescribe : this.data.open;
		this.$w.find(".ke-do-left, .ke-do-actions").toggle(Boolean(open));
		this.render();
	}

	async add() {
		const v = this.fg.get_values(true) || {};
		let rows;
		if (v.mode === "package") {
			if (!v.package) return frappe.msgprint(__("Choose a Drug Package."));
			rows = await this.call("package_drugs", { package: v.package });
			if (!(rows || []).length) return frappe.msgprint(__("This package has no drugs."));
		} else {
			const missing = [];
			if (!v.drug_code) missing.push(__("Drug Name"));
			if (!v.ke_dose) missing.push(__("Dose"));
			if (v.dosage_by_interval ? !v.interval : !v.dosage) missing.push(__("Frequency"));
			if (!v.duration) missing.push(__("Duration"));
			if (!v.ke_route) missing.push(__("Route"));
			if (!v.ke_start_date || !v.ke_start_time) missing.push(__("Start"));
			if (!v.ke_quantity) missing.push(__("Quantity"));
			if (missing.length)
				return frappe.msgprint(
					__("Fill in: {0}", [missing.join(", ")]),
					__("Add Prescription")
				);
			rows = [await this.row()];
		}
		const name = await this.encounter();
		const r = await this.call("add_drug", { encounter: name, row: rows });
		this.data.pending = r.pending;
		this.show_mapping(r.mapping && r.mapping.text);
		this.reset();
		this.fg.set_value("package", "");
		this.list = "pending";
		this.$w.find(".ke-do-list").val("pending");
		this.render();
		frappe.show_alert({ message: __("Added to the draft prescription"), indicator: "green" });
		if (this.on_change) this.on_change({ mapping: r.mapping && r.mapping.text });
	}

	async save() {
		if (!(this.data.pending || []).length)
			return frappe.msgprint(__("No drugs to send: add one first."));
		const name = await this.encounter();
		const r = await this.call("save_prescription", { encounter: name });
		frappe.show_alert({
			message: __("{0} drug(s) sent to the pharmacy", [(r && r.sent) || 0]),
			indicator: "green",
		});
		if (r && r.completed) this.name = null; // the ward round is done; the next drug starts a new one
		this.show_mapping("");
		if (this.on_sent) this.on_sent(r);
		this.load();
	}

	again(m) {
		const p = /^(\d+)\s+(\w+)$/.exec(m.period || "");
		this.set_mode("single");
		this.fg
			.set_values({
				ke_dose: m.ke_dose,
				ke_dose_uom: m.ke_dose_uom,
				ke_route: m.ke_route,
				dosage: m.dosage,
				duration: p ? cint(p[1]) : "",
				duration_unit: p ? p[2] : "Day",
				ke_chronic: m.chronic ? 1 : 0,
				comment: m.comment,
			})
			.then(() => this.fg.set_value("drug_code", m.drug_code));
		frappe.show_alert({
			message: __("Check the dose, then Add Prescription"),
			indicator: "blue",
		});
	}

	view(r) {
		const esc = frappe.utils.escape_html;
		const lines = [
			[__("Drug"), r.drug],
			[__("Dose"), r.dose || (r.ke_dose ? `${r.ke_dose} ${r.ke_dose_uom || ""}` : "")],
			[__("Frequency"), r.frequency || r.instructions],
			[__("Duration"), r.duration || r.period],
			[__("Route"), r.route || r.ke_route],
			[__("Start"), r.start],
			[__("Quantity"), r.quantity ? `${r.quantity} ${r.unit || ""}` : ""],
			[__("Instructions"), r.instructions || r.comment],
			[__("Pharmacy"), r.pharmacy_status],
			[__("Prescribed by"), r.practitioner],
		].filter(([, v]) => v);
		frappe.msgprint({
			title: esc(r.drug || ""),
			message: `<table class="table table-sm mb-0">${lines
				.map(
					([k, v]) =>
						`<tr><td class="text-muted">${k}</td><td>${esc(String(v))}</td></tr>`
				)
				.join("")}</table>`,
		});
	}

	render() {
		const esc = frappe.utils.escape_html;
		const rows = this.data[this.list] || [];
		const $t = this.$w.find(".ke-do-table");
		const counts = (k) => (this.data[k] || []).length;
		this.$w.find(".ke-do-list option").each((_i, o) => {
			const base = $(o)
				.text()
				.replace(/ \(\d+\)$/, "");
			$(o).text(counts(o.value) ? `${base} (${counts(o.value)})` : base);
		});
		if (!rows.length) {
			$t.html(
				`<p class="text-muted text-center my-4">${
					this.list === "pending"
						? __("No drugs waiting. Add one on the left.")
						: __("None.")
				}</p>`
			);
			return;
		}
		const pill = (text, colour) =>
			`<span class="indicator-pill ${colour} ml-1" style="font-size:10px">${esc(
				text
			)}</span>`;
		const colours = {
			Waiting: "orange",
			Dispensed: "green",
			"Partly Dispensed": "yellow",
			"Buy Outside": "blue",
			"Sent Back": "red",
		};
		const pending = this.list === "pending";
		const body = rows
			.map((r, i) => {
				const flags = pending
					? (r.buy_externally ? pill(__("Buy externally"), "blue") : "") +
					  (r.chronic ? pill(__("Chronic"), "purple") : "")
					: pill(__(r.pharmacy_status || ""), colours[r.pharmacy_status] || "gray") +
					  (r.chronic ? pill(__("Chronic"), "purple") : "");
				const dose = pending
					? r.dose
					: r.ke_dose
					? `${r.ke_dose} ${r.ke_dose_uom || ""}`
					: "";
				const freq = pending ? r.frequency : r.dosage || "";
				const dur = pending ? r.duration : r.period || "";
				const route = pending ? r.route : r.ke_route || "";
				const qty = pending ? `${r.quantity || ""} ${r.unit || ""}` : r.quantity || "";
				const actions = [
					`<button class="btn btn-xs btn-link ke-do-view" data-i="${i}" title="${__(
						"View"
					)}">${frappe.utils.icon("view", "sm")}</button>`,
					pending
						? `<button class="btn btn-xs btn-link text-danger ke-do-del" data-row="${esc(
								r.name
						  )}" title="${__("Remove")}">${frappe.utils.icon(
								"delete",
								"sm"
						  )}</button>`
						: ["active", "past", "chronic"].includes(this.list) &&
						  !this.$w.find(".ke-do-left").is(":hidden")
						? `<button class="btn btn-xs btn-default ke-do-again" data-i="${i}">${
								this.list === "chronic" ? __("Continue") : __("Prescribe Again")
						  }</button>`
						: "",
				].join("");
				return `<tr><td>${i + 1}</td><td><b>${esc(r.drug || "")}</b>${flags}</td>
					<td>${esc(dose || "")}</td><td>${esc(freq || "")}</td><td>${esc(dur || "")}</td>
					<td>${esc(route || "")}</td><td>${esc(String(qty).trim())}</td>
					<td class="text-nowrap">${actions}</td></tr>`;
			})
			.join("");
		$t.html(`<table class="table table-sm mb-0"><thead><tr>
			<th>#</th><th>${__("Drug Name")}</th><th>${__("Dose")}</th><th>${__("Frequency")}</th>
			<th>${__("Duration")}</th><th>${__("Route")}</th><th>${__("Quantity")}</th><th>${__(
			"Actions"
		)}</th>
			</tr></thead><tbody>${body}</tbody></table>`);
		$t.find(".ke-do-view").on("click", (e) => this.view(rows[$(e.currentTarget).data("i")]));
		$t.find(".ke-do-again").on("click", (e) => this.again(rows[$(e.currentTarget).data("i")]));
		$t.find(".ke-do-del").on("click", async (e) => {
			const name = await this.encounter();
			const r = await this.call("remove_drug", {
				encounter: name,
				row: $(e.currentTarget).data("row"),
			});
			this.data.pending = r.pending;
			this.render();
			if (this.on_change) this.on_change({});
		});
	}
};
