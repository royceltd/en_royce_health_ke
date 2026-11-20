// Copyright (c) 2026, Royce Technologies LTD and contributors
// For license information, please see license.txt

frappe.query_reports["Theatre List"] = {
	filters: [
		{
			fieldname: "date",
			label: __("Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "theatre",
			label: __("Theatre"),
			fieldtype: "Link",
			options: "Healthcare Service Unit",
		},
		{
			fieldname: "surgeon",
			label: __("Surgeon"),
			fieldtype: "Link",
			options: "Healthcare Practitioner",
		},
	],
	// The patient's name opens their theatre screen: the ward's patient screen
	// with the theatre's tabs (Drug Administration, Theatre Doctor Notes).
	formatter(value, row, column, data, default_formatter) {
		const out = default_formatter(value, row, column, data);
		if (column.fieldname !== "patient_name" || !data || !data.name) return out;
		const arg = (v) => frappe.utils.escape_html(JSON.stringify(v));
		const route = data.admission
			? `"inpatient-workspace", ${arg(data.admission)}, ${arg(data.name)}`
			: `"Form", "Theatre Booking", ${arg(data.name)}`;
		return `<a href="#" onclick='frappe.set_route(${route}); return false;'>${out}</a>${
			data.admission ? "" : ` <span class="text-muted small">${__("(not admitted)")}</span>`
		}`;
	},
};
