// Copyright (c) 2026, Royce Technologies LTD and contributors
// For license information, please see license.txt

frappe.query_reports["Theatre List"] = {
	filters: [
		{ fieldname: "date", label: __("Date"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "theatre", label: __("Theatre"), fieldtype: "Link", options: "Healthcare Service Unit" },
		{ fieldname: "surgeon", label: __("Surgeon"), fieldtype: "Link", options: "Healthcare Practitioner" },
	],
};
