// Copyright (c) 2026, Royce Technologies LTD and contributors
// For license information, please see license.txt

frappe.provide("frappe.dashboards.chart_sources");

frappe.dashboards.chart_sources["Insurance Claims by Payor"] = {
	method: "royce_health_ke.dashboards.claims_by_payor",
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
			fieldname: "period",
			label: __("Period"),
			fieldtype: "Select",
			options: ["Today", "This Week", "This Month", "Last Month", "This Quarter", "This Year", "Last 30 Days", "Last 12 Months"],
			default: "This Year",
		},
	],
};
