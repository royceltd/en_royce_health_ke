// Copyright (c) 2026, Royce Technologies LTD and contributors
// For license information, please see license.txt

// Last complete epidemiological week (Monday to Sunday).
const last_week = moment().subtract(1, "week");

frappe.query_reports["IDSR Weekly Report"] = {
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
			fieldname: "year",
			label: __("Year"),
			fieldtype: "Int",
			default: last_week.isoWeekYear(),
			reqd: 1,
		},
		{
			fieldname: "week",
			label: __("Epidemiological Week"),
			fieldtype: "Int",
			default: last_week.isoWeek(),
			reqd: 1,
		},
	],
};
