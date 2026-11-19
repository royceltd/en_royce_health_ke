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
		if (frappe.model.can_create("Lab Test Template")) {
			this.page.add_menu_item(__("Standard Tests"), () => this.library());
		}
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
				this.render_awaiting(data.awaiting_payment || 0);
			});
	}

	// Cash requests not paid yet are not listed: just how many wait at the Cashier.
	render_awaiting(n) {
		const $t = this.$body.find(".ke-lab-table");
		$t.find(".ke-lab-awaiting").remove();
		if (!n) return;
		$(`<div class="ke-lab-awaiting text-muted small" style="margin-top:8px">${__(
			"{0} more patient(s) have tests requested and are paying at the Cashier. They appear here once paid.",
			[n],
		)}</div>`).appendTo($t);
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
		const completed = this.tab === "completed";
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
					${completed ? `<td>${this.actions_cell(g, i)}</td>` : ""}
				</tr>`,
			)
			.join("");
		// the Actions menu must not be clipped by a scrolling table
		$t.html(`
			<div class="table-responsive" ${completed ? 'style="overflow:visible"' : ""}>
			<table class="table table-hover table-bordered" style="background:var(--card-bg)">
				<thead><tr>
					<th>${__("Visit")}</th><th>${__("Patient")}</th><th>${__("Age, sex")}</th>
					<th>${__("Requested by")}</th><th>${__("Requested")}</th><th>${__("Tests")}</th>
					<th>${__("Urgency")}</th><th>${__("Payment")}</th><th>${__("Progress")}</th>
					${completed ? `<th>${__("Actions")}</th>` : ""}
				</tr></thead>
				<tbody>${body}</tbody>
			</table></div>`);
		$t.find("tbody tr").on("click", (e) => {
			if ($(e.target).closest(".ke-lab-row-actions").length) return;
			const g = rows[$(e.currentTarget).data("idx")];
			this.open_order(g.key);
		});
		$t.find(".ke-lab-row-actions [data-action]").on("click", (e) => {
			e.preventDefault();
			const $a = $(e.currentTarget);
			this.action(rows[$a.data("idx")], $a.data("action"));
		});
	}

	open_order(key) {
		frappe
			.call(LAB + "order", { key, from_date: this.from.get_value(), to_date: this.to.get_value() })
			.then((r) => new LabOrderDialog(this, r.message));
	}

	walk_in() {
		royce_health_ke.lab_walk_in({
			on_done: (m) => {
				this.tab = "requests";
				this.refresh();
				this.open_order(m.key);
			},
		});
	}

	// Standard tests (lab.LIBRARY): add one with the hospital's price.
	library() {
		frappe.call(LAB + "lab_library").then((r) => {
			const tests = r.message || [];
			const d = new frappe.ui.Dialog({
				title: __("Standard Tests"),
				fields: [
					{ fieldtype: "HTML", fieldname: "list" },
					{
						fieldtype: "Select",
						fieldname: "test",
						label: __("Add"),
						options: tests.filter((t) => !t.exists).map((t) => t.name),
					},
					{ fieldtype: "Currency", fieldname: "rate", label: __("Cash price") },
					{
						fieldtype: "Data",
						fieldname: "code",
						label: __("Item code"),
						description: __("Blank: the standard code."),
					},
				],
				primary_action_label: __("Add Test"),
				primary_action: (v) => {
					if (!v.test) return;
					frappe
						.call({
							method: LAB + "add_from_library",
							args: { name: v.test, rate: v.rate, code: v.code },
							freeze: true,
						})
						.then((res) => {
							d.hide();
							frappe.show_alert({
								message: res.message.priced
									? __("{0} added", [res.message.name])
									: __("{0} added without a price: set it on the test.", [res.message.name]),
								indicator: res.message.priced ? "green" : "orange",
							});
							frappe.set_route("Form", "Lab Test Template", res.message.name);
						});
				},
			});
			d.fields_dict.list.$wrapper.html(
				`<table class="table table-bordered table-sm"><tbody>${tests
					.map(
						(t) => `<tr><td><b>${esc(t.name)}</b><div class="small text-muted">${esc(
							t.note || "",
						)} ${__("{0} parameters", [t.parameters])}</div></td><td>${
							t.exists ? pill(__("Set up"), "green") : pill(__("Not added"), "gray")
						}</td></tr>`,
					)
					.join("")}</tbody></table>`,
			);
			if (!tests.some((t) => !t.exists)) {
				d.get_primary_btn().hide();
				d.set_df_property("test", "hidden", 1);
				d.set_df_property("rate", "hidden", 1);
				d.set_df_property("code", "hidden", 1);
			}
			d.show();
		});
	}

	// The Completed tab's per-visit actions: the visit's validated tests in
	// one report. No Word copy: validated results are not edited.
	report_url(g, format, extra = "") {
		const [first, ...rest] = g.validated;
		return (
			`/printview?doctype=Lab%20Test&name=${encodeURIComponent(first)}` +
			`&format=${encodeURIComponent(format)}&no_letterhead=0` +
			(rest.length ? `&tests=${encodeURIComponent(g.validated.join(","))}` : "") +
			extra
		);
	}

	action(g, what) {
		if (!g.validated.length) return;
		const tests = g.validated.join(",");
		if (what === "view") window.open(this.report_url(g, "Laboratory Report"), "_blank");
		if (what === "print") window.open(this.report_url(g, "Laboratory Report", "&trigger_print=1"), "_blank");
		if (what === "request") {
			// every test of the order, validated or not
			const all = { ...g, validated: g.lab_tests.length ? g.lab_tests : g.validated };
			window.open(this.report_url(all, "Lab Request", "&trigger_print=1"), "_blank");
		}
		if (what === "pdf") {
			window.open(
				`/api/method/frappe.utils.print_format.download_pdf?doctype=Lab%20Test&name=${encodeURIComponent(
					g.validated[0],
				)}&format=${encodeURIComponent("Laboratory Report")}&tests=${encodeURIComponent(tests)}`,
				"_blank",
			);
		}
		if (what === "email") this.email(g);
	}

	email(g) {
		frappe.call(LAB + "patient_email", { patient: g.patient }).then((r) => {
			const d = new frappe.ui.Dialog({
				title: __("Send Results to {0}", [g.patient_name || g.patient]),
				fields: [
					{
						fieldtype: "Data",
						fieldname: "recipient",
						label: __("Email"),
						options: "Email",
						reqd: 1,
						default: r.message || "",
						description: r.message
							? __("The email on the patient's record.")
							: __("No email on the patient's record: type the one the patient gives."),
					},
					{
						fieldtype: "Small Text",
						fieldname: "message",
						label: __("Message"),
						description: __("Blank: a short standard note. The results go as a PDF."),
					},
					{
						fieldtype: "HTML",
						options: `<div class="small text-muted">${esc(
							__("{0} validated test(s): {1}", [g.validated.length, g.tests.join(", ")]),
						)}</div>`,
					},
				],
				primary_action_label: __("Send"),
				primary_action: (v) => {
					frappe
						.call({
							method: LAB + "email_results",
							args: { lab_tests: g.validated, recipient: v.recipient, message: v.message },
							freeze: true,
							freeze_message: __("Sending..."),
						})
						.then((res) => {
							d.hide();
							frappe.show_alert({
								message: __("Results sent to {0}", [res.message.to]),
								indicator: "green",
							});
						});
				},
			});
			d.show();
		});
	}

	actions_cell(g, i) {
		if (!g.validated || !g.validated.length) return "";
		const items = [
			["view", __("View")],
			["print", __("Print")],
			["pdf", __("Download PDF")],
			["email", __("Send to Patient")],
			["request", __("Print Request")],
		]
			.map(
				([key, label]) =>
					`<li><a class="dropdown-item" href="#" data-action="${key}" data-idx="${i}">${label}</a></li>`,
			)
			.join("");
		return `<div class="dropdown ke-lab-row-actions">
			<button class="btn btn-default btn-xs dropdown-toggle" data-toggle="dropdown">${__("Actions")}</button>
			<ul class="dropdown-menu dropdown-menu-right">${items}</ul></div>`;
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
		// Enter moves to the next result, as on the analyser's sheet; Enter
		// on the last result stays there: saving is always a button press.
		this.d.fields_dict.sheet.$wrapper.on("keydown", "input[data-kind]", (e) => {
			if (e.key !== "Enter" || e.shiftKey || e.ctrlKey || e.metaKey || e.altKey) return;
			e.preventDefault();
			e.stopPropagation();
			const $inputs = this.d.fields_dict.sheet.$wrapper.find("input[data-kind]:visible:not([disabled])");
			const next = $inputs.get($inputs.index(e.currentTarget) + 1);
			if (next) {
				next.focus();
				next.select();
			}
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
