// Copyright (c) 2026, Royce Technologies LTD and contributors
// For license information, please see license.txt

frappe.query_reports["Visits to Close"] = {
	filters: [
		{
			fieldname: "show",
			label: __("Show"),
			fieldtype: "Select",
			options: ["Open more than a day", "Completed with open items"].join("\n"),
			default: "Open more than a day",
		},
	],
};
