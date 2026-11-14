// Copyright (c) 2026, Royce Technologies LTD and contributors
// For license information, please see license.txt

// The laboratory's worklist: one row per patient order, tests inside.
// Server side: royce_health_ke/lab.py.

const LAB = "royce_health_ke.lab.";

frappe.pages["lab-worklist"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Lab Worklist"),
		single_column: true,
	});
	wrapper.lab_worklist = new LabWorklist(page, wrapper);
};

frappe.pages["lab-worklist"].on_page_show = function (wrapper) {
	wrapper.lab_worklist && wrapper.lab_worklist.refresh();
};

const TAB_LABELS = {
	requests: __("Requests"),
	entry: __("Results Entry"),
	validate: __("Validate Results"),
	completed: __("Completed"),
	register: __("Lab Register"),
};
const STAGE_COLOURS = {
	Requested: "orange",
	Collected: "blue",
	Entered: "purple",
	Completed: "green",
};
const STAGE_LABELS = {
	Requested: __("Requested"),
	Collected: __("Sample collected"),
	Entered: __("Results entered"),
	Completed: __("Validated"),
};
const PRIORITY_COLOURS = { STAT: "red", ASAP: "red", Urgent: "orange", Routine: "gray" };

function esc(v) {
	return frappe.utils.escape_html(v == null ? "" : String(v));
}

function pill(text, colour) {
	return `<span class="indicator-pill ${colour} no-indicator-dot" style="white-space:nowrap">${esc(
		text,
	)}</span>`;
}

function when(dt) {
	return dt ? frappe.datetime.prettyDate(dt) : "";
}

class LabWorklist {
	constructor(page, wrapper) {
		this.page = page;
		this.tab = "requests";
		this.page.set_primary_action(__("Walk-in Request"), () => this.walk_in(), "add");
		this.page.set_secondary_action(__("Refresh"), () => this.refresh(), "refresh");
		this.from = this.page.add_field({
			fieldtype: "Date",
			fieldname: "from_date",
			label: __("From"),
			default: frappe.datetime.add_days(frappe.datetime.get_today(), -6),
			change: () => this.refresh(),
		});
		this.to = this.page.add_field({
			fieldtype: "Date",
			fieldname: "to_date",
			label: __("To"),
			default: frappe.datetime.get_today(),
			change: () => this.refresh(),
		});
		this.search = this.page.add_field({
			fieldtype: "Data",
			fieldname: "search",
			label: __("Search patient or visit"),
			change: () => this.refresh(),
		});
		this.$body = $(`
			<div class="ke-lab-worklist">
				<ul class="nav nav-tabs ke-lab-tabs" style="margin-bottom:12px"></ul>
				<div class="ke-lab-table"></div>
			</div>`).appendTo(this.page.main);
		this.render_tabs({});
		// Keep the list fresh while the page is open.
		this.timer = setInterval(() => {
			if (frappe.get_route_str() === "lab-worklist" && !document.hidden) this.refresh(true);
		}, 60000);
	}

	args() {
		return {
			tab: this.tab,
			from_date: this.from.get_value(),
			to_date: this.to.get_value(),
			search: this.search.get_value(),
		};
	}

	render_tabs(counts) {
		const $tabs = this.$body.find(".ke-lab-tabs").empty();
		Object.entries(TAB_LABELS).forEach(([key, label]) => {
			const n = counts[key];
			const badge = n ? ` <span class="badge badge-pill" style="background:var(--bg-light-gray)">${n}</span>` : "";
			$(`<li class="nav-item"><a class="nav-link ${key === this.tab ? "active" : ""}" href="#">${esc(
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

	refresh(quiet) {
		frappe
			.call({ method: LAB + "worklist", args: this.args(), freeze: false })
			.then((r) => {
				const data = r.message || { rows: [], tab_counts: {} };
				this.render_tabs(data.tab_counts);
				this.render(data.rows);
			});
	}

	render(rows) {
		const $t = this.$body.find(".ke-lab-table").empty();
		if (!rows.length) {
			$t.html(`<div class="text-muted text-center" style="padding:40px">${__(
				"Nothing here for these dates.",
			)}</div>`);
			return;
		}
		const stage_cells = (c) =>
			Object.entries(c)
				.filter(([, n]) => n)
				.map(([s, n]) => pill(`${n} ${STAGE_LABELS[s]}`, STAGE_COLOURS[s]))
				.join(" ");
		const body = rows
			.map(
				(g, i) => `
				<tr data-idx="${i}" style="cursor:pointer">
					<td>${esc(g.visit || "")}</td>
					<td><b>${esc(g.patient_name)}</b><div class="text-muted small">${esc(g.patient)}</div></td>
					<td>${esc([g.age, g.sex].filter(Boolean).join(", "))}</td>
					<td>${esc(g.practitioner_name || "")}</td>
					<td title="${esc(g.requested_at)}">${esc(when(g.requested_at))}</td>
					<td><span class="badge badge-pill" style="background:var(--bg-blue);color:var(--text-on-blue)">${
						g.count
					}</span> <span class="small text-muted">${esc(g.tests.join(", "))}</span></td>
					<td>${pill(__(g.priority), PRIORITY_COLOURS[g.priority] || "gray")}</td>
					<td>${pill(g.payment_method, g.payment_method === "Cash" ? "gray" : "blue")}${
						g.unpaid ? " " + pill(__("{0} not paid", [g.unpaid]), "red") : ""
					}</td>
					<td>${stage_cells(g.counts)}</td>
				</tr>`,
			)
			.join("");
		$t.html(`
			<div class="table-responsive">
			<table class="table table-hover table-bordered" style="background:var(--card-bg)">
				<thead><tr>
					<th>${__("Visit")}</th><th>${__("Patient")}</th><th>${__("Age, sex")}</th>
					<th>${__("Requested by")}</th><th>${__("Requested")}</th><th>${__("Tests")}</th>
					<th>${__("Urgency")}</th><th>${__("Payment")}</th><th>${__("Progress")}</th>
				</tr></thead>
				<tbody>${body}</tbody>
			</table></div>`);
		$t.find("tbody tr").on("click", (e) => {
			const g = rows[$(e.currentTarget).data("idx")];
			this.open_order(g.key);
		});
	}

	open_order(key) {
		frappe
			.call(LAB + "order", { key, from_date: this.from.get_value(), to_date: this.to.get_value() })
			.then((r) => new LabOrderDialog(this, r.message));
	}

	walk_in() {
		const d = new frappe.ui.Dialog({
			title: __("Walk-in Lab Request"),
			fields: [
				{
					fieldtype: "Link",
					fieldname: "patient",
					label: __("Patient"),
					options: "Patient",
					reqd: 1,
					description: __("Register a new patient first if they are not found."),
				},
				{
					fieldtype: "MultiSelectList",
					fieldname: "tests",
					label: __("Tests"),
					reqd: 1,
					get_data: (txt) =>
						frappe.db.get_link_options("Lab Test Template", txt, { disabled: 0 }),
				},
				{ fieldtype: "Column Break" },
				{
					fieldtype: "Link",
					fieldname: "practitioner",
					label: __("Requesting doctor"),
					options: "Healthcare Practitioner",
					description: __("Blank: the default in Kenya Health Settings > Laboratory."),
				},
				{
					fieldtype: "Data",
					fieldname: "referred_by",
					label: __("Referred by (outside doctor or clinic)"),
				},
				{
					fieldtype: "Select",
					fieldname: "priority",
					label: __("Urgency"),
					options: "Routine\nUrgent\nASAP\nSTAT",
					default: "Routine",
				},
			],
			primary_action_label: __("Create Requests"),
			primary_action: (v) => {
				const tests = (v.tests || []).filter(Boolean);
				if (!tests.length) {
					frappe.msgprint(__("Choose at least one test."));
					return;
				}
				frappe
					.call({
						method: LAB + "walk_in",
						args: {
							patient: v.patient,
							tests,
							practitioner: v.practitioner,
							referred_by: v.referred_by,
							priority: v.priority,
						},
						freeze: true,
					})
					.then((r) => {
						d.hide();
						frappe.show_alert({
							message: __("{0} requests on visit {1}. Cash patients pay at the Cashier first.", [
								r.message.requests.length,
								r.message.visit,
							]),
							indicator: "green",
						});
						this.tab = "requests";
						this.refresh();
						this.open_order(r.message.key);
					});
			},
		});
		d.show();
	}
}

class LabOrderDialog {
	constructor(list, order) {
		this.list = list;
		this.order = order;
		this.d = new frappe.ui.Dialog({
			title: `${order.patient_name || order.patient} · ${[order.age, order.sex].filter(Boolean).join(", ")}`,
			size: "extra-large",
			fields: [{ fieldtype: "HTML", fieldname: "tests" }],
		});
		this.render();
		this.d.show();
	}

	render() {
		const tests = this.order.tests;
		const rows = tests
			.map((t, i) => {
				const can_collect = t.stage === "Requested" && !t.blocked;
				const pay = t.stage === "Requested"
					? pill(t.pay_label, t.pay === "unpaid" ? (t.blocked ? "red" : "orange") : "green")
					: "";
				const link = t.lab_test
					? `<a href="/app/lab-test/${encodeURIComponent(t.lab_test)}" target="_blank">${esc(
							t.lab_test,
						)}</a>`
					: `<span class="text-muted">${esc(t.request || "")}</span>`;
				return `
				<tr>
					<td>${t.stage === "Requested" ? `<input type="checkbox" data-idx="${i}" ${
						can_collect ? "checked" : "disabled"
					}>` : ""}</td>
					<td><b>${esc(t.test)}</b></td>
					<td>${pill(STAGE_LABELS[t.stage], STAGE_COLOURS[t.stage])}</td>
					<td>${pill(__(t.priority), PRIORITY_COLOURS[t.priority] || "gray")}</td>
					<td>${pay}</td>
					<td class="small">${esc(when(t.ordered_at))}</td>
					<td class="small">${esc(when(t.collected_at))}</td>
					<td>${link}</td>
				</tr>`;
			})
			.join("");
		const html = `
			<div class="small text-muted" style="margin-bottom:8px">${esc(this.order.patient)}${
				this.order.visit ? " · " + esc(this.order.visit) : ""
			}</div>
			<table class="table table-bordered">
				<thead><tr>
					<th></th><th>${__("Test")}</th><th>${__("Stage")}</th><th>${__("Urgency")}</th>
					<th>${__("Payment")}</th><th>${__("Requested")}</th><th>${__("Sample")}</th><th>${__("Record")}</th>
				</tr></thead>
				<tbody>${rows}</tbody>
			</table>
			<div class="ke-lab-actions" style="display:flex;gap:8px;flex-wrap:wrap"></div>
			${
				tests.some((t) => t.blocked)
					? `<p class="text-muted small" style="margin-top:8px">${__(
							"Tests marked Not paid are collected once the Cashier has taken payment, or a manager approves credit on the visit.",
						)}</p>`
					: ""
			}`;
		const $w = this.d.fields_dict.tests.$wrapper.html(html);
		const $a = $w.find(".ke-lab-actions");
		if (tests.some((t) => t.stage === "Requested" && !t.blocked)) {
			$(`<button class="btn btn-primary btn-sm">${__("Collect Samples")}</button>`)
				.appendTo($a)
				.on("click", () => this.collect());
		}
		const pending = tests.filter((t) => t.lab_test && (t.stage === "Collected" || t.stage === "Entered"));
		if (pending.length) {
			$(`<button class="btn btn-default btn-sm">${__("Enter Results")} (${pending.length})</button>`)
				.appendTo($a)
				.on("click", () => {
					this.d.hide();
					new ResultsDialog(this.list, this.order, pending.map((t) => t.lab_test));
				});
		}
		if (this.order.visit) {
			$(`<a class="btn btn-default btn-sm" href="/app/patient-visit/${encodeURIComponent(
				this.order.visit,
			)}" target="_blank">${__("Open Visit")}</a>`).appendTo($a);
		}
	}

	collect() {
		const $w = this.d.fields_dict.tests.$wrapper;
		const requests = [];
		$w.find("input[type=checkbox]:checked").each((_, el) => {
			const t = this.order.tests[$(el).data("idx")];
			if (t.request) requests.push(t.request);
		});
		if (!requests.length) {
			frappe.msgprint(__("Tick the tests whose samples you collected."));
			return;
		}
		frappe
			.call({ method: LAB + "collect", args: { requests }, freeze: true })
			.then((r) => {
				const m = r.message;
				if (m.refused.length) {
					frappe.msgprint({
						title: __("Not collected"),
						message: m.refused.map((x) => `<b>${esc(x.test)}</b>: ${esc(x.message)}`).join("<br>"),
						indicator: "orange",
					});
				}
				if (m.done.length) {
					frappe.show_alert({ message: __("{0} samples collected", [m.done.length]), indicator: "green" });
				}
				this.reload();
			});
	}

	reload() {
		frappe
			.call(LAB + "order", {
				key: this.order.key,
				from_date: this.list.from.get_value(),
				to_date: this.list.to.get_value(),
			})
			.then((r) => {
				this.order = r.message;
				this.render();
				this.list.refresh(true);
			});
	}
}

class ResultsDialog {
	constructor(list, order, lab_tests) {
		this.list = list;
		this.order = order;
		frappe.call(LAB + "results_sheet", { lab_tests }).then((r) => {
			this.sheet = r.message;
			this.make();
		});
	}

	make() {
		this.d = new frappe.ui.Dialog({
			title: __("Results: {0}", [this.order.patient_name || this.order.patient]),
			size: "extra-large",
			fields: [{ fieldtype: "HTML", fieldname: "sheet" }],
			primary_action_label: __("Save and Validate"),
			primary_action: () => this.save(1),
			secondary_action_label: __("Save"),
			secondary_action: () => this.save(0),
		});
		const html = this.sheet.map((t, ti) => this.test_html(t, ti)).join("");
		this.d.fields_dict.sheet.$wrapper.html(html);
		this.d.fields_dict.sheet.$wrapper.on("input", "input[data-range]", (e) => {
			// Show H / L as the value is typed, like the printed report.
			const $i = $(e.currentTarget);
			const f = this.flag($i.val(), $i.data("range"), this.sheet[$i.data("test")].sex);
			$i.closest("tr").find(".ke-flag").html(f ? pill(f, "red") : "");
		});
		this.d.show();
	}

	range_for_sex(text, sex) {
		// "F 12.0 - 15.5 / M 13.5 - 17.5": the patient's part (same rule as the printed report)
		const key = String(sex || "").trim().charAt(0).toUpperCase();
		if (key !== "M" && key !== "F") return text;
		const re = /(?:^|(?<=[\s/;,|(]))(male|female|men|women|m|f)\b\s*:?/gi;
		const labels = [...text.matchAll(re)];
		if (labels.length < 2) return text;
		for (let i = 0; i < labels.length; i++) {
			const word = labels[i][1].toLowerCase();
			const label = ["f", "female", "women"].includes(word) ? "F" : "M";
			if (label === key) {
				const end = i + 1 < labels.length ? labels[i + 1].index : text.length;
				return text.slice(labels[i].index + labels[i][0].length, end);
			}
		}
		return text;
	}

	flag(value, range, sex) {
		const v = parseFloat(String(value).replace(/,/g, ""));
		if (isNaN(v) || String(value).trim() === "" || !/^[-\d.,\s]+$/.test(String(value))) return "";
		const text = this.range_for_sex(String(range || "").replace(/<[^>]+>/g, " "), sex);
		let m = text.match(/(-?\d+(?:\.\d+)?)\s*(?:-|–|to)\s*(-?\d+(?:\.\d+)?)/);
		if (m) return v < parseFloat(m[1]) ? "L" : v > parseFloat(m[2]) ? "H" : "";
		m = text.match(/(<=|>=|<|>|≤|≥)\s*(-?\d+(?:\.\d+)?)/);
		if (m) {
			const lim = parseFloat(m[2]);
			if (["<", "<=", "≤"].includes(m[1]) && v > lim) return "H";
			if ([">", ">=", "≥"].includes(m[1]) && v < lim) return "L";
		}
		return "";
	}

	test_html(t, ti) {
		const open = `<a href="/app/lab-test/${encodeURIComponent(t.lab_test)}" target="_blank" class="small">${__(
			"Open full form",
		)}</a>`;
		if (t.full_form_only) {
			return `<div class="frappe-card" style="padding:12px;margin-bottom:12px">
				<b>${esc(t.test)}</b> · ${open}
				<div class="text-muted small">${__(
					"This test has sensitivity, organism or free-text results: enter them on the full form.",
				)}</div></div>`;
		}
		const normal = t.normal
			.map((r) =>
				r.heading
					? `<tr><td colspan="5"><b>${esc(r.label)}</b></td></tr>`
					: `<tr>
					<td>${esc(r.label)}${r.required ? ' <span class="text-danger">*</span>' : ""}</td>
					<td style="width:160px"><input class="form-control input-sm" data-test="${ti}" data-kind="normal"
						data-row="${esc(r.name)}" data-range="${esc(r.range)}" value="${esc(r.value)}"></td>
					<td>${esc(r.uom)}</td>
					<td class="small text-muted">${esc(String(r.range).replace(/<[^>]+>/g, " "))}</td>
					<td class="ke-flag">${r.flag ? pill(r.flag, "red") : ""}</td>
				</tr>`,
			)
			.join("");
		const descriptive = t.descriptive
			.map(
				(r) => `<tr>
					<td>${esc(r.label)}${r.required ? ' <span class="text-danger">*</span>' : ""}</td>
					<td colspan="4"><textarea class="form-control input-sm" rows="2" data-test="${ti}"
						data-kind="descriptive" data-row="${esc(r.name)}">${esc(r.value)}</textarea></td>
				</tr>`,
			)
			.join("");
		return `<div class="frappe-card" style="padding:12px;margin-bottom:12px">
			<div style="display:flex;justify-content:space-between"><b>${esc(t.test)}</b>${open}</div>
			<table class="table table-sm" style="margin:8px 0">
				<thead><tr><th>${__("Parameter")}</th><th>${__("Result")}</th><th>${__("Unit")}</th>
				<th>${__("Normal range")}</th><th></th></tr></thead>
				<tbody>${normal}${descriptive}</tbody>
			</table>
			<textarea class="form-control input-sm" rows="1" style="min-height:0;height:36px" data-test="${ti}" data-kind="comment"
				placeholder="${__("Comment")}">${esc(t.comment)}</textarea>
		</div>`;
	}

	collect_values() {
		const out = this.sheet
			.filter((t) => !t.full_form_only)
			.map((t) => ({ lab_test: t.lab_test, normal: {}, descriptive: {}, comment: t.comment }));
		const by_idx = {};
		this.sheet.forEach((t, i) => {
			const entry = out.find((o) => o.lab_test === t.lab_test);
			if (entry) by_idx[i] = entry;
		});
		this.d.fields_dict.sheet.$wrapper.find("[data-test]").each((_, el) => {
			const $el = $(el);
			const entry = by_idx[$el.data("test")];
			if (!entry) return;
			const kind = $el.data("kind");
			if (kind === "comment") entry.comment = $el.val();
			else entry[kind][$el.data("row")] = $el.val();
		});
		return out;
	}

	save(validate) {
		const results = this.collect_values();
		if (!results.length) {
			this.d.hide();
			return;
		}
		const go = () =>
			frappe
				.call({ method: LAB + "save_results", args: { results, validate }, freeze: true })
				.then((r) => {
					const m = r.message;
					if (m.errors.length) {
						frappe.msgprint({
							title: __("Not saved"),
							message: m.errors.map((x) => `<b>${esc(x.test)}</b>: ${esc(x.message)}`).join("<br>"),
							indicator: "orange",
						});
					}
					frappe.show_alert({
						message: validate
							? __("{0} validated", [m.validated.length])
							: __("{0} saved", [m.saved.length]),
						indicator: "green",
					});
					if (!m.errors.length) this.d.hide();
					this.list.refresh(true);
				});
		if (validate) {
			frappe.confirm(
				__("Validate these results? They are released to the doctor and can no longer be edited."),
				go,
			);
		} else {
			go();
		}
	}
}
