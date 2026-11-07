// Copyright (c) 2026, Royce Technologies LTD and contributors
// For license information, please see license.txt

frappe.query_reports["Ward Diet List"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company"), reqd: 1 },
		{ fieldname: "date", label: __("Date"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
		{ fieldname: "ward", label: __("Ward"), fieldtype: "Link", options: "Healthcare Service Unit", get_query: () => ({ filters: { is_group: 1 } }) },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && !data.diet_order && column.fieldname === "instructions") return `<span class="text-danger">${value}</span>`;
		if (data && data.allergies && column.fieldname === "allergies") return `<b class="text-danger">${value}</b>`;
		return value;
	},
};
