/* global ke_prescription_quantity */
// Copyright (c) 2026, Royce Technologies LTD and contributors
// For license information, please see license.txt

// The Order Drug panel on the consultation's Prescription tab
// (royce_health_ke.prescribing). Left: one drug (or a Drug Package) at a time.
// Right: Pending (this consultation, not sent), Sent, Active, Past, Chronic.
// Save to Draft keeps pending drugs on the consultation; Submit sends them to
// the pharmacy. Everything lands in Marley's Drug Prescription rows.
const KE_RX = "royce_health_ke.prescribing.";
const KE_RX_LISTS = [
	["pending", __("Pending")],
	["sent", __("Sent")],
	["active", __("Active")],
	["past", __("Past")],
	["chronic", __("Chronic")],
];

frappe.ui.form.on("Patient Encounter", {
	refresh(frm) {
		ke_rx_panel(frm);
	},
});

function ke_rx_panel(frm) {
	const field = frm.fields_dict.ke_prescribe_html;
	if (!field) return;
	const $w = field.$wrapper.empty();
	if (frm.is_new()) {
		$w.html(
			`<p class="text-muted">${__("Save the consultation to prescribe from here.")}</p>`
		);
		return;
	}
	const open = frm.doc.docstatus === 0 && frm.perm[0] && frm.perm[0].write;
	$w.html(`<div class="row ke-rx">
		<div class="col-md-5 ke-rx-order" ${open ? "" : 'style="display:none"'}>
			<div class="p-3 mb-3" style="border:1px solid var(--border-color);border-radius:8px">
				<div class="d-flex justify-content-between align-items-center mb-2">
					<b>${__("Order Drug")}</b>
					<span class="ke-rx-stock indicator-pill gray" style="display:none"></span>
				</div>
				<div class="btn-group btn-group-sm mb-3 ke-rx-mode">
					<button class="btn btn-primary" data-mode="single">${__("Single Drug")}</button>
					<button class="btn btn-default" data-mode="package">${__("Drug Package")}</button>
				</div>
				<div class="ke-rx-form"></div>
				<div class="small text-muted ke-rx-qty mb-2"></div>
				<button class="btn btn-sm btn-default ke-rx-add">${__("Add to Pending")}</button>
			</div>
		</div>
		<div class="${open ? "col-md-7" : "col-md-12"}">
			<ul class="nav nav-tabs ke-rx-tabs">${KE_RX_LISTS.map(
				([key, label], i) =>
					`<li class="nav-item"><a class="nav-link ${
						i ? "" : "active"
					}" data-list="${key}" href="#">${label} <span class="badge badge-pill ke-rx-n-${key}"></span></a></li>`
			).join("")}</ul>
			<div class="ke-rx-list p-2" style="min-height:120px"></div>
			<div class="text-right mt-2 ke-rx-actions" ${open ? "" : 'style="display:none"'}>
				<button class="btn btn-sm btn-default ke-rx-draft">${__("Save to Draft")}</button>
				<button class="btn btn-sm btn-primary ke-rx-submit">${__("Submit")}</button>
			</div>
		</div>
	</div>`);
	frm.__ke_rx = { list: "pending", data: { sent: [], active: [], past: [], chronic: [] } };
	if (open) ke_rx_form(frm, $w);
	$w.find(".ke-rx-tabs a").on("click", (e) => {
		e.preventDefault();
		$w.find(".ke-rx-tabs a").removeClass("active");
		$(e.currentTarget).addClass("active");
		frm.__ke_rx.list = $(e.currentTarget).data("list");
		ke_rx_render(frm);
	});
	$w.find(".ke-rx-draft").on("click", () => ke_rx_save_draft(frm));
	$w.find(".ke-rx-submit").on("click", () => ke_rx_submit(frm));
	ke_rx_render(frm);
	frappe.xcall(KE_RX + "history", { encounter: frm.doc.name }).then((data) => {
		frm.__ke_rx.data = data || frm.__ke_rx.data;
		ke_rx_render(frm);
	});
}

function ke_rx_form(frm, $w) {
	const routes = (frappe.meta.get_docfield("Drug Prescription", "ke_route") || {}).options || "";
	const fg = new frappe.ui.FieldGroup({
		body: $w.find(".ke-rx-form"),
		fields: [
			{
				fieldname: "drug_class",
				fieldtype: "Autocomplete",
				label: __("Drug Class"),
				depends_on: "eval:doc.mode!=='package'",
			},
			{
				fieldname: "drug_code",
				fieldtype: "Link",
				options: "Item",
				label: __("Drug Name"),
				depends_on: "eval:doc.mode!=='package'",
				get_query: () => ({
					query: KE_RX + "drug_query",
					filters: { drug_class: fg.get_value("drug_class") || "" },
				}),
				onchange: () => ke_rx_drug(frm, fg),
			},
			{
				fieldname: "package",
				fieldtype: "Link",
				options: "Treatment Plan Template",
				label: __("Drug Package"),
				depends_on: "eval:doc.mode==='package'",
				get_query: () => ({ query: KE_RX + "package_query" }),
			},
			{ fieldname: "mode", fieldtype: "Data", hidden: 1, default: "single" },
			{
				fieldname: "ke_buy_externally",
				fieldtype: "Check",
				label: __("Buy Externally"),
				depends_on: "eval:doc.mode!=='package'",
			},
			{ fieldtype: "Section Break", depends_on: "eval:doc.mode!=='package'" },
			{
				fieldname: "ke_dose",
				fieldtype: "Float",
				label: __("Dose"),
				reqd: 1,
				onchange: () => ke_rx_quantity(fg),
			},
			{ fieldtype: "Column Break" },
			{
				fieldname: "ke_dose_uom",
				fieldtype: "Link",
				options: "UOM",
				label: __("Unit"),
				onchange: () => ke_rx_quantity(fg),
			},
			{ fieldtype: "Section Break", depends_on: "eval:doc.mode!=='package'" },
			{
				fieldname: "dosage_by_interval",
				fieldtype: "Check",
				label: __("Schedule dosage? (every N hours)"),
				onchange: () => ke_rx_quantity(fg),
			},
			{
				fieldname: "dosage",
				fieldtype: "Link",
				options: "Prescription Dosage",
				label: __("Frequency"),
				depends_on: "eval:!doc.dosage_by_interval",
				onchange: () => ke_rx_quantity(fg),
			},
			{
				fieldname: "interval",
				fieldtype: "Int",
				label: __("Every"),
				depends_on: "eval:doc.dosage_by_interval",
				onchange: () => ke_rx_quantity(fg),
			},
			{
				fieldname: "interval_uom",
				fieldtype: "Select",
				options: "Hour\nDay",
				default: "Hour",
				label: __("Interval Unit"),
				depends_on: "eval:doc.dosage_by_interval",
				onchange: () => ke_rx_quantity(fg),
			},
			{ fieldtype: "Section Break", depends_on: "eval:doc.mode!=='package'" },
			{
				fieldname: "duration",
				fieldtype: "Int",
				label: __("Duration"),
				reqd: 1,
				onchange: () => ke_rx_quantity(fg),
			},
			{ fieldtype: "Column Break" },
			{
				fieldname: "duration_unit",
				fieldtype: "Select",
				options: "Day\nWeek\nMonth\nHour",
				default: "Day",
				label: __("Unit"),
				onchange: () => ke_rx_quantity(fg),
			},
			{ fieldtype: "Section Break", depends_on: "eval:doc.mode!=='package'" },
			{ fieldname: "ke_route", fieldtype: "Select", options: routes, label: __("Route") },
			{ fieldname: "ke_chronic", fieldtype: "Check", label: __("Chronic medicine") },
			{ fieldtype: "Column Break" },
			{
				fieldname: "ke_start_date",
				fieldtype: "Date",
				label: __("Start Date"),
				default: frappe.datetime.get_today(),
			},
			{
				fieldname: "ke_start_time",
				fieldtype: "Time",
				label: __("Start Time"),
				default: frappe.datetime.now_time(),
			},
			{ fieldtype: "Section Break", depends_on: "eval:doc.mode!=='package'" },
			{ fieldname: "comment", fieldtype: "Small Text", label: __("Instructions") },
		],
	});
	fg.make();
	frm.__ke_rx.fg = fg;
	frappe.xcall(KE_RX + "drug_classes").then((classes) => {
		fg.get_field("drug_class").set_data(classes || []);
	});
	$w.find(".ke-rx-mode button").on("click", (e) => {
		const mode = $(e.currentTarget).data("mode");
		$w.find(".ke-rx-mode button").removeClass("btn-primary").addClass("btn-default");
		$(e.currentTarget).removeClass("btn-default").addClass("btn-primary");
		fg.set_value("mode", mode);
		fg.refresh_dependency();
		$w.find(".ke-rx-add").text(
			mode === "package" ? __("Add Package to Pending") : __("Add to Pending")
		);
		$w.find(".ke-rx-qty, .ke-rx-stock").toggle(mode !== "package");
	});
	$w.find(".ke-rx-add").on("click", () => ke_rx_add(frm, fg));
}

function ke_rx_drug(frm, fg) {
	const item = fg.get_value("drug_code");
	const $stock = frm.fields_dict.ke_prescribe_html.$wrapper.find(".ke-rx-stock");
	fg.__ke_info = null;
	if (!item) {
		$stock.hide();
		return;
	}
	frappe.xcall(KE_RX + "drug_info", { item_code: item }).then((info) => {
		fg.__ke_info = info;
		if (info.stock === null || info.stock === undefined) {
			$stock.hide();
		} else {
			$stock
				.removeClass("gray green red")
				.addClass(info.stock > 0 ? "green" : "red")
				.text(__("Available: {0} {1}", [format_number(info.stock), info.stock_uom || ""]))
				.show();
		}
		const set = {};
		if (info.dose_uom && !fg.get_value("ke_dose_uom")) set.ke_dose_uom = info.dose_uom;
		if (info.route && !fg.get_value("ke_route")) set.ke_route = info.route;
		if (info.dosage && !fg.get_value("dosage")) set.dosage = info.dosage;
		if (info.duration && !fg.get_value("duration")) {
			set.duration = info.duration;
			set.duration_unit = info.duration_unit || "Day";
		}
		fg.set_values(set).then(() => ke_rx_quantity(fg));
	});
}

// The quantity the pharmacy will dispense, worked out as the doctor types.
function ke_rx_quantity(fg) {
	const $q = fg.wrapper.closest(".ke-rx").find(".ke-rx-qty");
	const v = fg.get_values(true) || {};
	if (!v.drug_code || !v.duration) {
		$q.empty();
		return;
	}
	frappe
		.xcall(KE_RX + "duration", { number: v.duration, unit: v.duration_unit || "Day" })
		.then((period) => {
			fg.__ke_period = period;
			return frappe.xcall("royce_health_ke.dispensing.quantity_for", {
				row: {
					drug_code: v.drug_code,
					medication: fg.__ke_info && fg.__ke_info.medication,
					ke_dose: v.ke_dose,
					ke_dose_uom: v.ke_dose_uom,
					dosage: v.dosage,
					period,
					interval: v.interval,
					interval_uom: v.interval_uom,
					dosage_by_interval: v.dosage_by_interval,
				},
			});
		})
		.then((r) => {
			$q.html(
				r
					? __("To dispense: {0} {1}", [
							r.quantity,
							frappe.utils.escape_html(r.unit || ""),
					  ])
					: ""
			);
		});
}

async function ke_rx_add(frm, fg) {
	const v = fg.get_values(true) || {};
	if (v.mode === "package") {
		if (!v.package) {
			frappe.msgprint(__("Choose a Drug Package."));
			return;
		}
		const rows = await frappe.xcall(KE_RX + "package_drugs", { package: v.package });
		if (!(rows || []).length) {
			frappe.msgprint(__("This package has no drugs."));
			return;
		}
		rows.forEach((r) => ke_rx_add_row(frm, r));
		fg.set_value("package", "");
		frappe.show_alert({
			message: __("{0} drug(s) added to Pending", [rows.length]),
			indicator: "green",
		});
		ke_rx_render(frm);
		return;
	}
	const missing = [];
	if (!v.drug_code) missing.push(__("Drug Name"));
	if (!v.ke_dose) missing.push(__("Dose"));
	if (v.dosage_by_interval ? !v.interval : !v.dosage) missing.push(__("Frequency"));
	if (!v.duration) missing.push(__("Duration"));
	if (!v.ke_route) missing.push(__("Route"));
	if (missing.length) {
		frappe.msgprint(__("Fill in: {0}", [missing.join(", ")]), __("Order Drug"));
		return;
	}
	const period = await frappe.xcall(KE_RX + "duration", {
		number: v.duration,
		unit: v.duration_unit || "Day",
	});
	ke_rx_add_row(frm, {
		drug_code: v.drug_code,
		drug_name: (fg.__ke_info && fg.__ke_info.item_name) || v.drug_code,
		medication: fg.__ke_info && fg.__ke_info.medication,
		ke_dose: v.ke_dose,
		ke_dose_uom: v.ke_dose_uom,
		ke_route: v.ke_route,
		dosage: v.dosage_by_interval ? null : v.dosage,
		dosage_by_interval: v.dosage_by_interval ? 1 : 0,
		interval: v.dosage_by_interval ? v.interval : null,
		interval_uom: v.dosage_by_interval ? v.interval_uom : null,
		period,
		ke_start_date: v.ke_start_date,
		ke_start_time: v.ke_start_time,
		ke_buy_externally: v.ke_buy_externally ? 1 : 0,
		ke_chronic: v.ke_chronic ? 1 : 0,
		comment: v.comment,
	});
	// ready for the next drug: keep the class and the start
	["drug_code", "ke_dose", "ke_dose_uom", "dosage", "interval", "duration", "comment"].forEach(
		(f) => fg.set_value(f, "")
	);
	fg.set_value("ke_buy_externally", 0);
	fg.set_value("ke_chronic", 0);
	ke_rx_render(frm);
}

function ke_rx_add_row(frm, values) {
	const row = frm.add_child("drug_prescription");
	Object.assign(row, values, { ke_draft: 1 });
	if (!row.ke_start_date) row.ke_start_date = frappe.datetime.get_today();
	frm.refresh_field("drug_prescription");
	frm.dirty();
	// the quantity in dispensing units (dispensing.py) as the table does it
	if (typeof ke_prescription_quantity === "function")
		ke_prescription_quantity(frm, row.doctype, row.name);
}

// Prescribe again from Active, Past or Chronic
function ke_rx_again(frm, mr) {
	const fg = frm.__ke_rx.fg;
	if (!fg) return;
	const m = /^(\d+)\s+(\w+)$/.exec(mr.period || "");
	fg.set_values({
		ke_dose: mr.ke_dose,
		ke_dose_uom: mr.ke_dose_uom,
		ke_route: mr.ke_route,
		dosage: mr.dosage,
		duration: m ? cint(m[1]) : "",
		duration_unit: m ? m[2] : "Day",
		ke_chronic: mr.chronic ? 1 : 0,
		comment: mr.comment,
	}).then(() => fg.set_value("drug_code", mr.drug_code));
	frappe.show_alert({ message: __("Check the dose, then Add to Pending"), indicator: "blue" });
}

function ke_rx_pending(frm) {
	return (frm.doc.drug_prescription || []).filter((d) => d.drug_code && !d.medication_request);
}

function ke_rx_render(frm) {
	const $w = frm.fields_dict.ke_prescribe_html && frm.fields_dict.ke_prescribe_html.$wrapper;
	if (!$w || !frm.__ke_rx) return;
	const esc = frappe.utils.escape_html;
	const data = Object.assign({}, frm.__ke_rx.data, { pending: ke_rx_pending(frm) });
	KE_RX_LISTS.forEach(([key]) =>
		$w.find(`.ke-rx-n-${key}`).text((data[key] || []).length || "")
	);
	const list = frm.__ke_rx.list;
	const rows = data[list] || [];
	const $list = $w.find(".ke-rx-list");
	if (!rows.length) {
		const empty = {
			pending: __("No drugs waiting. Add one on the left."),
			sent: __("Nothing sent to the pharmacy from this consultation yet."),
			active: __("No other current prescriptions."),
			past: __("No earlier prescriptions."),
			chronic: __("No chronic medicines recorded."),
		};
		$list.html(`<p class="text-muted text-center mt-4">${empty[list]}</p>`);
		return;
	}
	const pill = (text, colour) =>
		`<span class="indicator-pill ${colour} ml-1" style="font-size:10px">${esc(text)}</span>`;
	let html = "";
	if (list === "pending") {
		html = rows
			.map((d) => {
				const how = [
					d.ke_dose ? `${d.ke_dose} ${d.ke_dose_uom || ""}` : "",
					d.dosage_by_interval
						? __("every {0} {1}", [d.interval, d.interval_uom || ""])
						: d.dosage || "",
					d.period ? __("for {0}", [d.period]) : "",
					d.ke_route || "",
				]
					.filter(Boolean)
					.join(" · ");
				return `<tr><td><b>${esc(d.drug_name || d.drug_code)}</b>
					${d.ke_draft ? pill(__("Draft"), "gray") : pill(__("Sends on save"), "orange")}
					${d.ke_buy_externally ? pill(__("Buy externally"), "blue") : ""}
					${d.ke_chronic ? pill(__("Chronic"), "purple") : ""}
					<div class="small text-muted">${esc(how)}${d.comment ? ". " + esc(d.comment) : ""}</div></td>
					<td class="text-right small">${
						d.ke_quantity ? esc(`${d.ke_quantity} ${d.ke_dispensing_unit || ""}`) : ""
					}</td>
					<td class="text-right"><button class="btn btn-xs btn-default ke-rx-remove" data-row="${esc(
						d.name
					)}">${__("Remove")}</button></td></tr>`;
			})
			.join("");
	} else {
		const colours = {
			Waiting: "orange",
			Dispensed: "green",
			"Partly Dispensed": "yellow",
			"Buy Outside": "blue",
			"Sent Back": "red",
		};
		html = rows
			.map(
				(m) => `<tr><td><b>${esc(m.drug || "")}</b>${
					m.chronic ? pill(__("Chronic"), "purple") : ""
				}
					<div class="small text-muted">${esc(m.instructions || "")}</div>
					<div class="small text-muted">${esc(frappe.datetime.str_to_user(m.order_date))}${
					m.practitioner ? " · " + esc(m.practitioner) : ""
				}</div></td>
					<td class="text-right small">${esc(String(m.quantity || ""))}</td>
					<td class="text-right">${pill(__(m.pharmacy_status), colours[m.pharmacy_status] || "gray")}${
					list !== "sent" && frm.__ke_rx.fg
						? ` <button class="btn btn-xs btn-default ke-rx-again" data-mr="${esc(
								m.name
						  )}">${
								list === "chronic" ? __("Continue") : __("Prescribe Again")
						  }</button>`
						: ""
				}</td></tr>`
			)
			.join("");
	}
	$list.html(`<table class="table table-sm mb-0"><tbody>${html}</tbody></table>`);
	$list.find(".ke-rx-remove").on("click", (e) => {
		const name = $(e.currentTarget).data("row");
		const row = (frm.doc.drug_prescription || []).find((d) => d.name === name);
		if (!row) return;
		frappe.model.clear_doc(row.doctype, row.name);
		frm.refresh_field("drug_prescription");
		frm.dirty();
		ke_rx_render(frm);
	});
	$list.find(".ke-rx-again").on("click", (e) => {
		const name = $(e.currentTarget).data("mr");
		const mr = rows.find((m) => m.name === name);
		if (mr) ke_rx_again(frm, mr);
	});
}

async function ke_rx_save_draft(frm) {
	await frm.save();
	frappe.show_alert({ message: __("Saved. Draft drugs are not sent yet."), indicator: "green" });
}

async function ke_rx_submit(frm) {
	if (!ke_rx_pending(frm).length) {
		frappe.msgprint(__("No drugs to send: add one first."));
		return;
	}
	if (frm.is_dirty()) await frm.save();
	const r = await frappe.xcall(KE_RX + "submit", { encounter: frm.doc.name });
	await frm.reload_doc();
	frappe.show_alert({
		message: __("{0} drug(s) sent to the pharmacy", [(r && r.sent) || 0]),
		indicator: "green",
	});
}
