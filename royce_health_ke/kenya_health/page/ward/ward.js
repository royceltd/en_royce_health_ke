// Copyright (c) 2026, Royce Technologies LTD and contributors
// For license information, please see license.txt

// The ward: patients waiting for a bed (admitted from the consultation) and
// those on the ward. Server side: royce_health_ke/inpatient.py.

const WD = "royce_health_ke.inpatient.";

frappe.pages["ward"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Ward"),
		single_column: true,
	});
	wrapper.ward_page = new WardPage(page);
};

frappe.pages["ward"].on_page_show = function (wrapper) {
	wrapper.ward_page && wrapper.ward_page.refresh();
};

function wd_esc(v) {
	return frappe.utils.escape_html(v == null ? "" : String(v));
}

const WD_URGENCY = { Emergency: "red", Urgent: "orange", Routine: "gray" };

class WardPage {
	constructor(page) {
		this.page = page;
		this.ward = page.add_field({
			fieldtype: "Select",
			fieldname: "ward",
			label: __("Ward"),
			options: "",
			change: () => this.refresh(),
		});
		page.set_secondary_action(__("Refresh"), () => this.refresh(), "refresh");
		this.$body = $("<div></div>").appendTo(page.main);
	}

	refresh() {
		frappe.xcall(WD + "admission_list", { ward: this.ward.get_value() || null }).then((r) => {
			const current = this.ward.get_value();
			this.ward.df.options = ["", ...(r.wards || [])].join("\n");
			this.ward.refresh();
			this.ward.set_input(current);
			this.render(r);
		});
	}

	render(r) {
		const waiting = (r.waiting || [])
			.map(
				(p) => `<tr>
				<td><b>${wd_esc(p.patient_name)}</b><div class="small text-muted">${wd_esc(p.patient)} · ${wd_esc(
					p.name
				)}</div></td>
				<td><span class="indicator-pill ${WD_URGENCY[p.ke_urgency] || "gray"}">${wd_esc(
					__(p.ke_urgency || "Routine")
				)}</span></td>
				<td>${wd_esc(p.ke_ward || "")}</td>
				<td class="small">${wd_esc(p.ke_admission_reason || "")}</td>
				<td>${wd_esc(frappe.datetime.str_to_user(p.admission_ordered_for || p.scheduled_date))}</td>
				<td>${
					p.ke_preauth_status === "Pending"
						? `<span class="indicator-pill orange">${__("Pre-auth pending")}</span>`
						: ""
				}</td>
				<td><button class="btn btn-xs btn-primary wd-admit" data-ip="${wd_esc(
					p.name
				)}" data-ward="${wd_esc(p.ke_ward || "")}">${__("Give Bed")}</button></td></tr>`
			)
			.join("");
		const on_ward = (r.on_ward || [])
			.map(
				(p) => `<tr class="wd-open" data-ip="${wd_esc(p.name)}" style="cursor:pointer">
				<td><b>${wd_esc(p.patient_name)}</b><div class="small text-muted">${wd_esc(p.patient)} · ${wd_esc(
					p.name
				)}</div></td>
				<td>${wd_esc(p.bed || "")}<div class="small text-muted">${wd_esc(p.ward || "")}</div></td>
				<td>${wd_esc(p.days)} ${__("day(s)")}</td>
				<td>${wd_esc(p.primary_practitioner || "")}</td>
				<td>${
					p.doses_due
						? `<span class="indicator-pill red">${__("{0} dose(s) due", [
								p.doses_due,
						  ])}</span>`
						: ""
				}
					${
						p.status === "Discharge Scheduled"
							? `<span class="indicator-pill blue">${__("Discharge planned")}</span>`
							: ""
					}
					${
						p.ke_preauth_status === "Pending"
							? `<span class="indicator-pill orange">${__(
									"Pre-auth pending"
							  )}</span>`
							: ""
					}</td></tr>`
			)
			.join("");
		this.$body.html(`
			<h5 class="mt-2">${__("Waiting for a bed")} <span class="text-muted">(${
			(r.waiting || []).length
		})</span></h5>
			${
				waiting
					? `<div class="table-responsive"><table class="table table-bordered" style="font-size:13px"><thead><tr><th>${__(
							"Patient"
					  )}</th><th>${__("Urgency")}</th><th>${__("Ward")}</th><th>${__(
							"Reason"
					  )}</th><th>${__(
							"For"
					  )}</th><th></th><th></th></tr></thead><tbody>${waiting}</tbody></table></div>`
					: `<p class="text-muted">${__(
							"Nobody waiting. Doctors admit from the consultation: Admit to Ward."
					  )}</p>`
			}
			<h5 class="mt-4">${__("On the ward")} <span class="text-muted">(${
			(r.on_ward || []).length
		})</span></h5>
			${
				on_ward
					? `<div class="table-responsive"><table class="table table-bordered table-hover" style="font-size:13px"><thead><tr><th>${__(
							"Patient"
					  )}</th><th>${__("Bed")}</th><th>${__("Stay")}</th><th>${__(
							"Doctor"
					  )}</th><th></th></tr></thead><tbody>${on_ward}</tbody></table></div>`
					: `<p class="text-muted">${__("No patients on this ward.")}</p>`
			}`);
		this.$body
			.find(".wd-open")
			.on("click", (e) =>
				frappe.set_route("inpatient-workspace", $(e.currentTarget).data("ip"))
			);
		this.$body
			.find(".wd-admit")
			.on("click", (e) =>
				this.give_bed($(e.currentTarget).data("ip"), $(e.currentTarget).data("ward"))
			);
	}

	async give_bed(ip, ward) {
		const beds = (await frappe.xcall(WD + "vacant_beds", { ward })) || [];
		if (!beds.length) {
			frappe.msgprint(__("No vacant bed on {0}.", [wd_esc(ward)]));
			return;
		}
		frappe.prompt(
			{
				fieldname: "bed",
				fieldtype: "Select",
				label: __("Bed"),
				options: beds.map((b) => b.name).join("\n"),
				reqd: 1,
			},
			(v) =>
				frappe.xcall(WD + "admit", { inpatient_record: ip, bed: v.bed }).then(() => {
					frappe.show_alert({
						message: __("Admitted to {0}", [v.bed]),
						indicator: "green",
					});
					frappe.set_route("inpatient-workspace", ip);
				}),
			__("Give a bed on {0}", [ward]),
			__("Admit")
		);
	}
}
