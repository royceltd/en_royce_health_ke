// Copyright (c) 2026, Royce Technologies LTD and contributors
// For license information, please see license.txt

frappe.query_reports["Patients by Residence"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date", default: frappe.datetime.add_months(frappe.datetime.get_today(), -1), reqd: 1 },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
		{ fieldname: "county", label: __("County"), fieldtype: "Data" },
		{ fieldname: "residence_type", label: __("Type"), fieldtype: "Select", options: "\nEstate\nTown\nVillage" },
	],
};
