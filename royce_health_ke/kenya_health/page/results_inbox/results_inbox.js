// Copyright (c) 2026, Royce Technologies LTD and contributors
// For license information, please see license.txt

// A consultant's results: completed lab tests and reported imaging exams,
// unread until opened from here. Server side: royce_health_ke/lab.py.

frappe.pages["results-inbox"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Results Inbox"),
		single_column: true,
	});
	wrapper.inbox = new ResultsInbox(page);
};

frappe.pages["results-inbox"].on_page_show = function (wrapper) {
	wrapper.inbox && wrapper.inbox.refresh();
};

class ResultsInbox {
	constructor(page) {
		this.page = page;
		this.first = true;
		this.page.set_secondary_action(__("Refresh"), () => this.refresh(), "refresh");
		this.practitioner = page.add_field({
			fieldtype: "Link",
			fieldname: "practitioner",
			label: __("Consultant (blank = all)"),
			options: "Healthcare Practitioner",
			change: () => this.refresh(),
		});
		this.unread = page.add_field({
			fieldtype: "Check",
			fieldname: "unread_only",
			label: __("Unread only"),
			default: 1,
			change: () => this.refresh(),
		});
		this.from = page.add_field({
			fieldtype: "Date",
			fieldname: "from_date",
			label: __("From"),
			default: frappe.datetime.add_days(frappe.datetime.get_today(), -13),
			change: () => this.refresh(),
		});
		this.to = page.add_field({
			fieldtype: "Date",
			fieldname: "to_date",
			label: __("To"),
			default: frappe.datetime.get_today(),
			change: () => this.refresh(),
		});
		this.$body = $(`<div class="ke-results-inbox"></div>`).appendTo(page.main);
	}

	refresh() {
		frappe
			.call("royce_health_ke.lab.results_inbox", {
				practitioner: this.practitioner.get_value(),
				unread_only: this.unread.get_value() ? 1 : 0,
				from_date: this.from.get_value(),
				to_date: this.to.get_value(),
			})
			.then((r) => {
				const m = r.message;
				// First visit: a consultant linked to this user sees their own results.
				if (this.first && m.mine && !this.practitioner.get_value()) {
					this.first = false;
					this.practitioner.set_value(m.mine);
					return;
				}
				this.first = false;
				this.render(m.rows);
			});
	}

	render(rows) {
		const esc = (v) => frappe.utils.escape_html(v == null ? "" : String(v));
		if (!rows.length) {
			this.$body.html(`<div class="text-muted text-center" style="padding:40px">${__(
				"No results to read.",
			)}</div>`);
			return;
		}
		const body = rows
			.map(
				(r, i) => `
			<tr data-idx="${i}" style="cursor:pointer;${r.seen_at ? "" : "font-weight:600"}">
				<td>${r.seen_at ? "" : '<span class="indicator-pill blue no-indicator-dot">' + __("New") + "</span>"}</td>
				<td title="${esc(r.result_at)}">${esc(frappe.datetime.prettyDate(r.result_at))}</td>
				<td>${esc(r.patient_name)}<div class="text-muted small" style="font-weight:400">${esc(
					r.patient,
				)}</div></td>
				<td>${esc(r.test)}</td>
				<td>${esc(r.department)}</td>
				<td>${r.abnormal ? '<span class="indicator-pill red no-indicator-dot">' + __("Abnormal") + "</span>" : ""}</td>
				<td>${esc(r.practitioner_name || "")}</td>
				<td class="small text-muted" style="font-weight:400">${
					r.seen_at ? esc(r.seen_by_name) + " · " + esc(frappe.datetime.prettyDate(r.seen_at)) : ""
				}</td>
			</tr>`,
			)
			.join("");
		this.$body.html(`
			<div class="table-responsive">
			<table class="table table-hover table-bordered" style="background:var(--card-bg)">
				<thead><tr><th></th><th>${__("Result")}</th><th>${__("Patient")}</th><th>${__("Test")}</th>
				<th>${__("Department")}</th><th>${__("Flag")}</th><th>${__("Requested by")}</th><th>${__(
					"Seen",
				)}</th></tr></thead>
				<tbody>${body}</tbody>
			</table></div>`);
		this.$body.find("tbody tr").on("click", (e) => {
			const r = rows[$(e.currentTarget).data("idx")];
			frappe
				.call("royce_health_ke.lab.mark_seen", { doctype: r.doctype, name: r.name })
				.then(() => frappe.set_route("Form", r.doctype, r.name));
		});
	}
}
