// Copyright (c) 2026, Royce Technologies LTD and contributors
// For license information, please see license.txt

frappe.query_reports["MOH 705 Outpatient Summary"] = {
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
			default: moment().subtract(1, "month").year(),
			reqd: 1,
		},
		{
			fieldname: "month",
			label: __("Month"),
			fieldtype: "Select",
			options: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12].map((m) => ({
				value: m,
				label: moment().month(m - 1).format("MMMM"),
			})),
			default: moment().subtract(1, "month").month() + 1,
			reqd: 1,
		},
		{
			fieldname: "form",
			label: __("Form"),
			fieldtype: "Select",
			options: [
				{ value: "705A", label: __("705A - under 5 years") },
				{ value: "705B", label: __("705B - 5 years and over") },
			],
			default: "705A",
			reqd: 1,
		},
	],
};
