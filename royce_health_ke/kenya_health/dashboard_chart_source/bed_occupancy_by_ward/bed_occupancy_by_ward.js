// Copyright (c) 2026, Royce Technologies LTD and contributors
// For license information, please see license.txt

frappe.provide("frappe.dashboards.chart_sources");

frappe.dashboards.chart_sources["Bed Occupancy by Ward"] = {
	method: "royce_health_ke.dashboards.bed_occupancy_by_ward",
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			reqd: 1,
		},
	],
};
