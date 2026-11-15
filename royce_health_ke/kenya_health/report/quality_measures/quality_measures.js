// Copyright (c) 2026, Royce Technologies LTD and contributors
// For license information, please see license.txt

frappe.query_reports["Quality Measures"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			reqd: 1,
		},
		{
			fieldname: "from_date",
			label: __("From"),
			fieldtype: "Date",
			default: moment().subtract(1, "month").startOf("month").format("YYYY-MM-DD"),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To"),
			fieldtype: "Date",
			default: moment().subtract(1, "month").endOf("month").format("YYYY-MM-DD"),
			reqd: 1,
		},
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "met" && data && data.met) {
			return `<span class="indicator-pill ${data.met === "Yes" ? "green" : "red"}">${__(
				data.met
			)}</span>`;
		}
		return value;
	},
	onload(report) {
		const args = () => report.get_values();
		report.page.add_inner_button(__("Save Results"), () =>
			frappe.call({
				method: "royce_health_ke.quality.save_results",
				args: args(),
				freeze: true,
				callback: (r) =>
					frappe.show_alert({
						message: __("{0} results saved", [(r.message || []).length]),
						indicator: "green",
					}),
			})
		);
		const download = (fmt) => {
			const v = args();
			window.open(
				"/api/method/royce_health_ke.quality.export?" +
					$.param({
						company: v.company,
						from_date: v.from_date,
						to_date: v.to_date,
						fmt,
					})
			);
		};
		report.page.add_inner_button(
			__("FHIR MeasureReport (JSON)"),
			() => download("fhir"),
			__("Export")
		);
		report.page.add_inner_button(__("CSV"), () => download("csv"), __("Export"));
		report.page.add_inner_button(__("Import Results"), () => {
			new frappe.ui.FileUploader({
				allow_multiple: false,
				restrictions: { allowed_file_types: [".csv", ".json"] },
				on_success: (file) =>
					frappe.call({
						method: "royce_health_ke.quality.import_results",
						args: { company: args().company, file_url: file.file_url },
						freeze: true,
						callback: (r) => {
							const m = r.message || {};
							frappe.msgprint(
								__("{0} results imported.", [m.imported || 0]) +
									(m.unknown && m.unknown.length
										? "<br>" +
										  __("Unknown measure codes: {0}", [m.unknown.join(", ")])
										: "")
							);
							report.refresh();
						},
					}),
			});
		});
	},
};
