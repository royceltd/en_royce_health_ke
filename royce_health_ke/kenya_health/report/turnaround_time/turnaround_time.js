// Copyright (c) 2026, Royce Technologies LTD and contributors
// For license information, please see license.txt

frappe.query_reports["Turnaround Time"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date", default: frappe.datetime.add_days(frappe.datetime.get_today(), -7), reqd: 1 },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
		{ fieldname: "department", label: __("Department"), fieldtype: "Select", options: "\nLaboratory\nRadiology" },
		{ fieldname: "template", label: __("Test or Exam"), fieldtype: "Data" },
		{ fieldname: "each_request", label: __("Each Request"), fieldtype: "Check", description: __("One row per test instead of the summary per test type") },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "within_target" && data && data.within_target === "No") return `<span class="text-danger">${value}</span>`;
		if (column.fieldname === "within_target_pct" && data && data.within_target_pct !== null && data.within_target_pct < 80) return `<span class="text-danger">${value}</span>`;
		return value;
	},
};
