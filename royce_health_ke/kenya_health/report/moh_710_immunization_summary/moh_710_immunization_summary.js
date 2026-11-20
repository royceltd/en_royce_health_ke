// Copyright (c) 2026, Royce Technologies LTD and contributors
// For license information, please see license.txt

// [first day, last day] of last month (frappe.datetime.month_start takes no date)
function ke_last_month() {
	const start = frappe.datetime.add_months(frappe.datetime.get_today(), -1).slice(0, 8) + "01";
	return [start, frappe.datetime.add_days(frappe.datetime.add_months(start, 1), -1)];
}

frappe.query_reports["MOH 710 Immunization Summary"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("From"),
			fieldtype: "Date",
			default: ke_last_month()[0],
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To"),
			fieldtype: "Date",
			default: ke_last_month()[1],
			reqd: 1,
		},
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
	],
	formatter(value, row, column, data, default_formatter) {
		const out = default_formatter(value, row, column, data);
		return data && data.bold ? `<b>${out}</b>` : out;
	},
};
