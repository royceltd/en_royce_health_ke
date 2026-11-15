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
			fieldname: "period",
			label: __("Period"),
			fieldtype: "Select",
			options: [
				{ value: "Month", label: __("Month") },
				{ value: "Quarter", label: __("Quarter (sum of its months)") },
				{ value: "Year", label: __("Year (sum of its months)") },
			],
			default: "Month",
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
			depends_on: "eval:doc.period == 'Month'",
			mandatory_depends_on: "eval:doc.period == 'Month'",
		},
		{
			fieldname: "quarter",
			label: __("Quarter"),
			fieldtype: "Select",
			options: [
				{ value: 1, label: __("Q1 (Jan-Mar)") },
				{ value: 2, label: __("Q2 (Apr-Jun)") },
				{ value: 3, label: __("Q3 (Jul-Sep)") },
				{ value: 4, label: __("Q4 (Oct-Dec)") },
			],
			default: Math.ceil((moment().subtract(1, "month").month() + 1) / 3),
			depends_on: "eval:doc.period == 'Quarter'",
			mandatory_depends_on: "eval:doc.period == 'Quarter'",
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
