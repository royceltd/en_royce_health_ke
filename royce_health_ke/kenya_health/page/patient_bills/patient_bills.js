// Copyright (c) 2026, Royce Technologies LTD and contributors
// For license information, please see license.txt

// Patient Bills: one row per visit, billed / paid / discount / insurance /
// balance, cash and insurance on their own tabs. Server: royce_health_ke/bills.py.

frappe.pages["patient-bills"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Patient Bills"), single_column: true });
	wrapper.bills = new PatientBills(page);
};

frappe.pages["patient-bills"].on_page_show = function (wrapper) {
	wrapper.bills && wrapper.bills.refresh();
};

class PatientBills {
	constructor(page) {
		this.page = page;
		this.tab = "Cash";
		page.set_secondary_action(__("Refresh"), () => this.refresh(), "refresh");
		this.approvals_btn = page.add_inner_button(__("Approvals"), () =>
			frappe.set_route("List", "Bill Approval Request", { status: "Pending" }),
		);
		const field = (df) => page.add_field({ ...df, change: () => this.refresh() });
		this.from = field({ fieldtype: "Date", fieldname: "from_date", label: __("From"), default: frappe.datetime.add_days(frappe.datetime.get_today(), -6) });
		this.to = field({ fieldtype: "Date", fieldname: "to_date", label: __("To"), default: frappe.datetime.get_today() });
		this.balance = field({ fieldtype: "Select", fieldname: "balance", label: __("Balance"), options: ["", "Has balance", "Cleared"].join("\n") });
		this.search = field({ fieldtype: "Data", fieldname: "search", label: __("Search patient or visit") });
		this.$body = $(`<div><ul class="nav nav-tabs pb-tabs" style="margin-bottom:12px"></ul><div class="pb-table"></div></div>`).appendTo(page.main);
		this.render_tabs();
	}

	render_tabs() {
		const $t = this.$body.find(".pb-tabs").empty();
		[["Cash", __("Cash bills")], ["Insurance", __("Insurance bills")]].forEach(([key, label]) => {
			$(`<li class="nav-item"><a class="nav-link ${key === this.tab ? "active" : ""}" href="#">${label}</a></li>`)
				.appendTo($t)
				.on("click", (e) => {
					e.preventDefault();
					this.tab = key;
					this.render_tabs();
					this.refresh();
				});
		});
	}

	refresh() {
		frappe
			.call("royce_health_ke.bills.board", {
				payment_method: this.tab,
				from_date: this.from.get_value(),
				to_date: this.to.get_value(),
				balance: this.balance.get_value(),
				search: this.search.get_value(),
			})
			.then(({ message: m }) => {
				this.approvals_btn.text(__("Approvals waiting: {0}", [m.approvals_waiting]));
				this.approvals_btn.toggleClass("btn-warning", m.approvals_waiting > 0);
				this.render(m);
			});
	}

	render(m) {
		const esc = (v) => frappe.utils.escape_html(v == null ? "" : String(v));
		const money = (v) => format_currency(v || 0);
		const $t = this.$body.find(".pb-table").empty();
		if (!m.rows.length) {
			$t.html(`<div class="text-muted text-center" style="padding:40px">${__("No visits for these filters.")}</div>`);
			return;
		}
		const pill = (text, colour) => `<span class="indicator-pill ${colour} no-indicator-dot">${esc(text)}</span>`;
		const bill_colour = { "To Bill": "orange", Unpaid: "red", Paid: "green" };
		const insured = this.tab === "Insurance";
		const rows = m.rows
			.map(
				(r) => `<tr>
				<td><a href="/app/patient-visit/${encodeURIComponent(r.name)}">${esc(r.name)}</a></td>
				<td>${esc(frappe.datetime.str_to_user(r.visit_date))}</td>
				<td><b>${esc(r.patient_name)}</b></td>
				<td>${esc(__(r.visit_type))}${r.status !== "Open" ? " · " + esc(__(r.status)) : ""}</td>
				${insured ? `<td>${esc(r.insurance_payor || "")}</td>` : ""}
				<td class="text-right">${money(r.billed)}${r.draft ? `<div class="small text-muted">${__("+ {0} draft", [money(r.draft)])}</div>` : ""}</td>
				${insured ? `<td class="text-right">${money(r.insurance)}</td>` : ""}
				<td class="text-right">${money(r.paid)}</td>
				<td class="text-right">${r.discount ? money(r.discount) : ""}</td>
				<td class="text-right ${r.balance > 0.005 ? "text-danger" : ""}"><b>${money(r.balance)}</b></td>
				<td>${r.bill_status ? pill(__(r.bill_status), bill_colour[r.bill_status] || "gray") : ""}
					${r.allow_credit ? pill(__("Pay later"), "blue") : ""}
					${r.pending_approvals ? pill(__("{0} approval waiting", [r.pending_approvals]), "orange") : ""}</td>
			</tr>`,
			)
			.join("");
		const t = m.totals;
		$t.html(`<div class="table-responsive"><table class="table table-bordered table-hover" style="background:var(--card-bg)">
			<thead><tr><th>${__("Visit")}</th><th>${__("Date")}</th><th>${__("Patient")}</th><th>${__("Visit type")}</th>
			${insured ? `<th>${__("Payer")}</th>` : ""}
			<th class="text-right">${__("Billed")}</th>${insured ? `<th class="text-right">${__("Insurance")}</th>` : ""}
			<th class="text-right">${__("Paid")}</th><th class="text-right">${__("Discount / waived")}</th>
			<th class="text-right">${__("Balance")}</th><th>${__("Status")}</th></tr></thead>
			<tbody>${rows}</tbody>
			<tfoot><tr style="font-weight:600"><td colspan="${insured ? 5 : 4}">${__("Total ({0} visits)", [m.rows.length])}</td>
			<td class="text-right">${money(t.billed)}</td>${insured ? `<td class="text-right">${money(t.insurance)}</td>` : ""}
			<td class="text-right">${money(t.paid)}</td><td class="text-right">${money(t.discount)}</td>
			<td class="text-right">${money(t.balance)}</td><td></td></tr></tfoot>
			</table></div>`);
	}
}
