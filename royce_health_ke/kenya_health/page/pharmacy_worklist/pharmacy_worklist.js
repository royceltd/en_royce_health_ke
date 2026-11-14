// Copyright (c) 2026, Royce Technologies LTD and contributors
// For license information, please see license.txt

// The pharmacy's worklist: prescriptions and counter sales to dispense, one
// row per visit. Server side: royce_health_ke/pharmacy.py.

const PH = "royce_health_ke.pharmacy.";

frappe.pages["pharmacy-worklist"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Pharmacy Worklist"),
		single_column: true,
	});
	wrapper.pharmacy = new PharmacyWorklist(page);
};

frappe.pages["pharmacy-worklist"].on_page_show = function (wrapper) {
	wrapper.pharmacy && wrapper.pharmacy.refresh();
};

const PH_TABS = {
	waiting: __("Waiting"),
	dispensed: __("Dispensed"),
	other: __("Buy Outside / Sent Back"),
	all: __("All"),
};
const PH_STAGE = {
	Waiting: ["orange", __("Waiting")],
	Dispensed: ["green", __("Dispensed")],
	"Buy Outside": ["gray", __("Buy outside")],
	"Sent Back": ["purple", __("Sent back to doctor")],
};

function ph_esc(v) {
	return frappe.utils.escape_html(v == null ? "" : String(v));
}

function ph_pill(text, colour) {
	return `<span class="indicator-pill ${colour} no-indicator-dot" style="white-space:nowrap">${ph_esc(
		text,
	)}</span>`;
}

function ph_num(v) {
	return v == null ? "" : String(Math.round(v * 100) / 100);
}

class PharmacyWorklist {
	constructor(page) {
		this.page = page;
		this.tab = "waiting";
		page.set_primary_action(__("Counter Sale"), () => this.counter_sale(), "add");
		page.set_secondary_action(__("Refresh"), () => this.refresh(), "refresh");
		this.warehouse = page.add_field({
			fieldtype: "Link",
			fieldname: "warehouse",
			label: __("Pharmacy store"),
			options: "Warehouse",
			get_query: () => ({ filters: { is_group: 0 } }),
		});
		this.from = page.add_field({
			fieldtype: "Date",
			fieldname: "from_date",
			label: __("From"),
			default: frappe.datetime.add_days(frappe.datetime.get_today(), -2),
			change: () => this.refresh(),
		});
		this.to = page.add_field({
			fieldtype: "Date",
			fieldname: "to_date",
			label: __("To"),
			default: frappe.datetime.get_today(),
			change: () => this.refresh(),
		});
		this.search = page.add_field({
			fieldtype: "Data",
			fieldname: "search",
			label: __("Search patient or visit"),
			change: () => this.refresh(),
		});
		this.$body = $(`<div>
			<ul class="nav nav-tabs ph-tabs" style="margin-bottom:12px"></ul>
			<div class="ph-table"></div></div>`).appendTo(page.main);
		this.render_tabs({});
		setInterval(() => {
			if (frappe.get_route_str() === "pharmacy-worklist" && !document.hidden) this.refresh();
		}, 60000);
	}

	render_tabs(counts) {
		const $tabs = this.$body.find(".ph-tabs").empty();
		Object.entries(PH_TABS).forEach(([key, label]) => {
			const n = counts[key];
			const badge = n ? ` <span class="badge badge-pill" style="background:var(--bg-light-gray)">${n}</span>` : "";
			$(`<li class="nav-item"><a class="nav-link ${key === this.tab ? "active" : ""}" href="#">${ph_esc(
				label,
			)}${badge}</a></li>`)
				.appendTo($tabs)
				.on("click", (e) => {
					e.preventDefault();
					this.tab = key;
					this.refresh();
				});
		});
	}

	refresh() {
		frappe
			.call(PH + "worklist", {
				tab: this.tab,
				from_date: this.from.get_value(),
				to_date: this.to.get_value(),
				search: this.search.get_value(),
			})
			.then((r) => {
				const m = r.message;
				if (!this.warehouse.get_value() && m.warehouse) this.warehouse.set_value(m.warehouse);
				this.render_tabs(m.tab_counts);
				this.render(m.rows);
			});
	}

	render(rows) {
		const $t = this.$body.find(".ph-table").empty();
		if (!rows.length) {
			$t.html(`<div class="text-muted text-center" style="padding:40px">${__(
				"Nothing here for these dates.",
			)}</div>`);
			return;
		}
		const progress = (c) =>
			Object.entries(c)
				.filter(([, n]) => n)
				.map(([s, n]) => ph_pill(`${n} ${PH_STAGE[s][1]}`, PH_STAGE[s][0]))
				.join(" ");
		const body = rows
			.map(
				(g, i) => `<tr data-idx="${i}" style="cursor:pointer">
				<td>${ph_esc(g.visit || "")}${g.counter_sale ? "<div>" + ph_pill(__("Counter sale"), "blue") + "</div>" : ""}</td>
				<td><b>${ph_esc(g.patient_name)}</b><div class="text-muted small">${ph_esc(g.patient || "")}</div></td>
				<td>${ph_esc([g.age, g.sex].filter(Boolean).join(", "))}</td>
				<td>${ph_esc(g.prescriber || "")}</td>
				<td title="${ph_esc(g.ordered_at)}">${ph_esc(frappe.datetime.prettyDate(g.ordered_at))}</td>
				<td><span class="badge badge-pill" style="background:var(--bg-blue);color:var(--text-on-blue)">${
					g.count
				}</span> <span class="small text-muted">${ph_esc(g.drugs.join(", "))}</span></td>
				<td>${ph_pill(g.payment_method, g.payment_method === "Cash" ? "gray" : "blue")}${
					g.unpaid ? " " + ph_pill(__("{0} not paid", [g.unpaid]), "red") : ""
				}</td>
				<td>${progress(g.counts)}</td>
			</tr>`,
			)
			.join("");
		$t.html(`<div class="table-responsive"><table class="table table-hover table-bordered" style="background:var(--card-bg)">
			<thead><tr><th>${__("Visit")}</th><th>${__("Patient")}</th><th>${__("Age, sex")}</th>
			<th>${__("Prescriber")}</th><th>${__("Ordered")}</th><th>${__("Drugs")}</th><th>${__("Payment")}</th>
			<th>${__("Progress")}</th></tr></thead><tbody>${body}</tbody></table></div>`);
		$t.find("tbody tr").on("click", (e) => this.open(rows[$(e.currentTarget).data("idx")].key));
	}

	args(key) {
		return {
			key,
			from_date: this.from.get_value(),
			to_date: this.to.get_value(),
			warehouse: this.warehouse.get_value(),
		};
	}

	open(key) {
		frappe.call(PH + "order", this.args(key)).then((r) => new PharmacyOrderDialog(this, r.message));
	}

	counter_sale() {
		const d = new frappe.ui.Dialog({
			title: __("Counter Sale"),
			size: "large",
			fields: [
				{
					fieldtype: "Link",
					fieldname: "patient",
					label: __("Patient"),
					options: "Patient",
					description: __("A registered patient, or leave blank for a walk-in."),
				},
				{ fieldtype: "Column Break" },
				{
					fieldtype: "Data",
					fieldname: "walk_in_name",
					label: __("Walk-in name"),
					depends_on: "eval:!doc.patient",
				},
				{ fieldtype: "Section Break" },
				{
					fieldtype: "Table",
					fieldname: "items",
					label: __("Drugs"),
					in_place_edit: true,
					reqd: 1,
					data: [],
					fields: [
						{
							fieldtype: "Link",
							fieldname: "item_code",
							label: __("Drug"),
							options: "Item",
							in_list_view: 1,
							reqd: 1,
							columns: 4,
							get_query: () => ({ filters: { is_stock_item: 1, disabled: 0, is_sales_item: 1 } }),
						},
						{ fieldtype: "Float", fieldname: "qty", label: __("Quantity"), in_list_view: 1, reqd: 1, columns: 2 },
						{
							fieldtype: "Data",
							fieldname: "instructions",
							label: __("Instructions"),
							in_list_view: 1,
							columns: 4,
						},
					],
				},
				{ fieldtype: "Float", fieldname: "discount_percentage", label: __("Discount %") },
			],
			primary_action_label: __("Send Bill to Cashier"),
			primary_action: (v) => {
				const items = (v.items || []).filter((i) => i.item_code && i.qty > 0);
				if (!items.length) {
					frappe.msgprint(__("Add the drugs and their quantities."));
					return;
				}
				frappe
					.call({
						method: PH + "counter_sale",
						args: {
							items,
							patient: v.patient,
							walk_in_name: v.walk_in_name,
							discount_percentage: v.discount_percentage,
						},
						freeze: true,
					})
					.then((r) => {
						d.hide();
						frappe.msgprint({
							title: __("Bill sent to the Cashier"),
							message: __(
								"Bill {0} ({1}) is waiting at the Cashier. Dispense from the worklist once it is paid.",
								[r.message.invoice, format_currency(r.message.total)],
							),
							indicator: "green",
						});
						this.tab = "waiting";
						this.refresh();
					});
			},
		});
		d.show();
	}
}

class PharmacyOrderDialog {
	constructor(list, order) {
		this.list = list;
		this.order = order;
		this.d = new frappe.ui.Dialog({
			title: `${order.patient_name || ""}${order.sex ? " · " + order.sex : ""}`,
			size: "extra-large",
			fields: [{ fieldtype: "HTML", fieldname: "body" }],
		});
		this.render();
		this.d.show();
	}

	render() {
		const o = this.order;
		const rows = o.lines
			.map((l, i) => {
				const waiting = l.stage === "Waiting";
				const can_dispense = waiting && !l.blocked;
				const qty_default = waiting
					? Math.max(0, Math.min(l.remaining, l.available == null ? l.remaining : l.available))
					: l.returnable || 0;
				const stock =
					l.available == null
						? ""
						: l.available < l.remaining && waiting
							? ph_pill(ph_num(l.available), "red")
							: ph_num(l.available);
				return `<tr>
					<td><input type="checkbox" data-idx="${i}" ${can_dispense ? "checked" : ""}></td>
					<td><b>${ph_esc(l.drug)}</b>${l.note ? `<div class="small text-muted">${ph_esc(l.note)}</div>` : ""}</td>
					<td><input class="form-control input-xs" data-instr="${i}" value="${ph_esc(l.instructions)}"></td>
					<td>${ph_num(l.qty)} ${ph_esc(l.uom || "")}</td>
					<td>${ph_num(l.dispensed)}</td>
					<td style="width:90px"><input type="number" min="0" step="any" class="form-control input-xs" data-qty="${i}" value="${ph_num(
						qty_default,
					)}"></td>
					<td>${stock}</td>
					<td>${waiting ? ph_pill(l.pay_label, l.blocked ? "red" : l.pay === "paid" ? "green" : "blue") : ""}</td>
					<td>${ph_pill(PH_STAGE[l.stage][1] + (l.partly ? " (" + __("part") + ")" : ""), PH_STAGE[l.stage][0])}</td>
				</tr>`;
			})
			.join("");
		const $b = this.d.fields_dict.body.$wrapper.html(`
			<div class="small text-muted" style="margin-bottom:8px">${ph_esc(o.patient || "")}${
				o.visit ? " · " + ph_esc(o.visit) : ""
			}${this.list.warehouse.get_value() ? " · " + __("Store") + ": " + ph_esc(this.list.warehouse.get_value()) : ""}</div>
			<table class="table table-bordered table-sm">
				<thead><tr><th></th><th>${__("Drug")}</th><th>${__("Instructions (label)")}</th><th>${__("Prescribed")}</th>
				<th>${__("Dispensed")}</th><th>${__("Quantity")}</th><th>${__("In store")}</th><th>${__("Payment")}</th>
				<th>${__("Status")}</th></tr></thead>
				<tbody>${rows}</tbody>
			</table>
			<div class="ph-actions" style="display:flex;gap:8px;flex-wrap:wrap"></div>
			<p class="small text-muted" style="margin-top:8px">${__(
				"Tick the drugs, check the quantity, then choose what to do. Quantity is what you dispense now, or what the patient brings back for a return.",
			)}</p>`);
		const $a = $b.find(".ph-actions");
		const btn = (label, cls, fn) => $(`<button class="btn ${cls} btn-sm">${label}</button>`).appendTo($a).on("click", fn);
		if (o.lines.some((l) => l.stage === "Waiting" && !l.blocked)) btn(__("Dispense"), "btn-primary", () => this.dispense());
		if (o.can_bill) btn(__("Bill Drugs"), "btn-default", () => this.bill());
		if (o.lines.some((l) => l.kind === "mr" && l.stage === "Waiting" && !l.dispensed && l.pay === "not_billed")) {
			btn(__("Buy Outside"), "btn-default", () => this.mark("buy_outside"));
			btn(__("Send Back to Doctor"), "btn-default", () => this.mark("send_back"));
		}
		if (o.lines.some((l) => l.stage === "Buy Outside" || l.stage === "Sent Back")) {
			btn(__("Back to Waiting"), "btn-default", () => this.mark("back_to_waiting"));
		}
		if (o.lines.some((l) => l.returnable > 0)) btn(__("Return"), "btn-default", () => this.return_());
		(o.encounters || []).forEach((enc) =>
			$(`<a class="btn btn-default btn-sm" target="_blank" href="/printview?doctype=Patient%20Encounter&name=${encodeURIComponent(
				enc,
			)}&format=Prescription">${__("Print Prescription")}</a>`).appendTo($a),
		);
		if (o.visit) {
			$(`<a class="btn btn-default btn-sm" target="_blank" href="/app/patient-visit/${encodeURIComponent(
				o.visit,
			)}">${__("Open Visit")}</a>`).appendTo($a);
		}
	}

	picked(filter) {
		const $b = this.d.fields_dict.body.$wrapper;
		const out = [];
		$b.find("input[type=checkbox]:checked").each((_, el) => {
			const i = $(el).data("idx");
			const l = this.order.lines[i];
			if (filter && !filter(l)) return;
			out.push({
				kind: l.kind,
				ref: l.ref,
				drug: l.drug,
				qty: parseFloat($b.find(`[data-qty=${i}]`).val()) || 0,
				instructions: $b.find(`[data-instr=${i}]`).val(),
			});
		});
		return out;
	}

	reload() {
		frappe.call(PH + "order", this.list.args(this.order.key)).then((r) => {
			this.order = r.message;
			this.render();
			this.list.refresh();
		});
	}

	dispense() {
		const lines = this.picked((l) => l.stage === "Waiting" && !l.blocked);
		if (!lines.length) return frappe.msgprint(__("Tick the drugs to dispense."));
		frappe
			.call({ method: PH + "dispense", args: { lines, warehouse: this.list.warehouse.get_value() }, freeze: true })
			.then((r) => {
				frappe.show_alert({ message: __("Dispensed"), indicator: "green" });
				(r.message || []).forEach((dn) =>
					window.open(
						`/printview?doctype=Delivery%20Note&name=${encodeURIComponent(dn)}&format=Medicine%20Labels&trigger_print=1`,
					),
				);
				this.reload();
			});
	}

	bill() {
		frappe.call({ method: PH + "bill_drugs", args: { visit: this.order.visit }, freeze: true }).then((r) => {
			frappe.msgprint({
				title: __("Billed"),
				message: __("The drugs are on bill {0}. The patient pays at the Cashier, then you dispense.", [r.message]),
				indicator: "green",
			});
			this.reload();
		});
	}

	mark(action) {
		const lines = this.picked((l) => l.kind === "mr");
		if (!lines.length) return frappe.msgprint(__("Tick the prescribed drugs first."));
		const requests = lines.map((l) => l.ref);
		const go = (args) =>
			frappe.call({ method: PH + action, args: { requests, ...args }, freeze: true }).then(() => this.reload());
		if (action === "back_to_waiting") return go({});
		frappe.prompt(
			{
				fieldname: "text",
				fieldtype: "Small Text",
				reqd: action === "send_back" ? 1 : 0,
				label: action === "send_back" ? __("What should the doctor change?") : __("Reason (optional)"),
			},
			(v) => go(action === "send_back" ? { note: v.text } : { reason: v.text }),
			action === "send_back" ? __("Send back to the doctor") : __("Patient buys outside"),
		);
	}

	return_() {
		const lines = this.picked((l) => l.returnable > 0);
		if (!lines.length) return frappe.msgprint(__("Tick the dispensed drugs being returned."));
		frappe.confirm(
			__("Return {0} to the store? Any refund is a credit note at the Cashier.", [
				lines.map((l) => `${l.qty} × ${ph_esc(l.drug)}`).join(", "),
			]),
			() =>
				frappe.call({ method: PH + "return_lines", args: { lines }, freeze: true }).then(() => {
					frappe.show_alert({ message: __("Returned to stock"), indicator: "green" });
					this.reload();
				}),
		);
	}
}
