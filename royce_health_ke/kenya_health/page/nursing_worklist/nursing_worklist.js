// Copyright (c) 2026, Royce Technologies LTD and contributors
// For license information, please see license.txt

// The nursing station's worklist: requests the doctor's Request Type routes to
// Nursing (injections, dressings, nebulisation ...). Server side:
// royce_health_ke/routing.py.

const NW = "royce_health_ke.routing.";

frappe.pages["nursing-worklist"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Nursing Worklist"),
		single_column: true,
	});
	wrapper.nursing_worklist = new NursingWorklist(page);
};

frappe.pages["nursing-worklist"].on_page_show = function (wrapper) {
	wrapper.nursing_worklist && wrapper.nursing_worklist.refresh();
};

function nw_esc(v) {
	return frappe.utils.escape_html(v == null ? "" : String(v));
}

class NursingWorklist {
	constructor(page) {
		this.page = page;
		this.tab = "waiting";
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
		page.set_secondary_action(__("Refresh"), () => this.refresh(), "refresh");
		this.$tabs = $(`<div class="mb-3">
			<button class="btn btn-sm btn-default mr-2" data-tab="waiting">${__("To Do")}</button>
			<button class="btn btn-sm btn-default" data-tab="done">${__("Done")}</button></div>`).appendTo(
			page.main
		);
		this.$tabs.on("click", "button", (e) => {
			this.tab = $(e.currentTarget).data("tab");
			this.refresh();
		});
		this.$body = $("<div></div>").appendTo(page.main);
		this.refresh();
	}

	refresh() {
		this.$tabs.find("button").removeClass("btn-primary");
		this.$tabs.find(`[data-tab="${this.tab}"]`).addClass("btn-primary");
		frappe
			.xcall(NW + "nursing_worklist", {
				tab: this.tab,
				from_date: this.from.get_value(),
				to_date: this.to.get_value(),
			})
			.then((rows) => this.render(rows || []));
	}

	render(rows) {
		if (!rows.length) {
			this.$body.html(
				`<p class="text-muted">${
					this.tab === "done"
						? __("Nothing done in this period.")
						: __(
								"No nursing requests waiting. Requests whose Request Type goes to Nursing show here."
						  )
				}</p>`
			);
			return;
		}
		const html = rows
			.map((r) => {
				const pay = r.awaiting_payment
					? `<span class="indicator-pill orange">${__("Not paid: Cashier first")}</span>`
					: `<span class="indicator-pill green">${nw_esc(
							__(r.payment_status || "Ready")
					  )}</span>`;
				const action =
					this.tab === "done"
						? `<div class="small text-muted">${__("Done {0} by {1}", [
								nw_esc(frappe.datetime.str_to_user(r.ke_done_at)),
								nw_esc(r.ke_done_by),
						  ])}${r.ke_done_note ? "<br>" + nw_esc(r.ke_done_note) : ""}</div>`
						: `<button class="btn btn-xs btn-primary nw-done" data-name="${nw_esc(
								r.name
						  )}" data-test="${nw_esc(r.template_dn)}">${__("Mark Done")}</button>`;
				return `<tr>
					<td><b>${nw_esc(r.patient_name)}</b><div class="small text-muted">${nw_esc(r.patient)}</div></td>
					<td><b>${nw_esc(r.template_dn)}</b>${r.quantity > 1 ? " × " + nw_esc(r.quantity) : ""}
						<div class="small text-muted">${nw_esc(r.ke_request_category || "")}</div>
						${r.comment ? `<div class="small">${nw_esc(r.comment)}</div>` : ""}</td>
					<td>${nw_esc(r.practitioner_name || "")}<div class="small text-muted">${nw_esc(
					frappe.datetime.str_to_user(r.order_date)
				)} ${nw_esc((r.order_time || "").slice(0, 5))}</div></td>
					<td>${
						r.ke_patient_visit
							? `<a href="/desk/patient-visit/${encodeURIComponent(
									r.ke_patient_visit
							  )}">${nw_esc(r.ke_patient_visit)}</a>`
							: ""
					}</td>
					<td>${this.tab === "done" ? "" : pay}</td>
					<td>${action}</td></tr>`;
			})
			.join("");
		this.$body
			.html(`<div class="table-responsive"><table class="table table-bordered" style="font-size:13px">
			<thead><tr><th>${__("Patient")}</th><th>${__("Request")}</th><th>${__("Ordered by")}</th><th>${__(
			"Visit"
		)}</th><th>${__(
			"Payment"
		)}</th><th></th></tr></thead><tbody>${html}</tbody></table></div>`);
		this.$body.find(".nw-done").on("click", (e) => {
			const $b = $(e.currentTarget);
			frappe.prompt(
				{
					fieldname: "note",
					fieldtype: "Small Text",
					label: __("Note (what was given or done)"),
				},
				(v) =>
					frappe
						.xcall(NW + "mark_done", { request: $b.data("name"), note: v.note })
						.then(() => {
							frappe.show_alert({ message: __("Done"), indicator: "green" });
							this.refresh();
						}),
				__("Mark {0} done", [$b.data("test")]),
				__("Done")
			);
		});
	}
}
